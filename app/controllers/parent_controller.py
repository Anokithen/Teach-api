from flask import current_app, jsonify, request
from flask_jwt_extended import current_user
from app.extensions import db
from sqlalchemy.exc import IntegrityError
from app.models.parent_model import Parent
from app.security import exit_password_attempts
from app.services.account_cleanup_service import collect_account_asset_refs, schedule_account_asset_cleanup
from app.services.cloudinary_service import delete_profile_image, upload_profile_image, validate_uploaded_file
from app.validators import (
    MAX_EXIT_PASSWORD_LENGTH,
    MAX_PASSWORD_LENGTH,
    validate_account_email,
    validate_exit_password,
    validate_name,
    validate_password,
)


def _exit_configuration_limit_key():
    return f"exit-password-config:{current_user.id}"


def _check_exit_configuration_limit():
    limit = current_app.config["EXIT_PASSWORD_RATE_LIMIT_ATTEMPTS"]
    window = current_app.config["EXIT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS"]
    key = _exit_configuration_limit_key()
    blocked, retry_after = exit_password_attempts.blocked(key, limit, window)
    if not blocked:
        return key, window, None
    response = jsonify(
        {"error": "Too many incorrect password attempts. Please try again later."}
    )
    response.status_code = 429
    response.headers["Retry-After"] = str(retry_after)
    return key, window, response


def get_me():
    return jsonify({"parent": current_user.to_dict()}), 200


def update_me():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required."}), 400

    errors = []
    parent = current_user

    if "name" in data:
        name, error = validate_name(data.get("name"))
        if error:
            errors.append(error.replace("is required", "cannot be empty"))
        else:
            data["name"] = name

    if "email" in data:
        email, error = validate_account_email(data.get("email"))
        if error:
            errors.append(error.replace("is required", "cannot be empty"))
        else:
            data["email"] = email
            existing = Parent.query.filter_by(email=email).first()
            if existing and existing.id != parent.id:
                errors.append("An account with this email already exists.")

    if "password" in data:
        password, error = validate_password(data.get("password"))
        if error:
            errors.append(error)
        else:
            data["password"] = password

    if errors:
        return jsonify({"errors": errors}), 400

    try:
        if "name" in data:
            parent.name = str(data.get("name")).strip()
        if "email" in data:
            parent.email = data.get("email")
        if "password" in data:
            parent.set_password(str(data.get("password")))

        db.session.commit()
        return jsonify({"message": "Profile updated successfully.", "parent": parent.to_dict()}), 200
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "An account with this email already exists."}), 409
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def set_exit_password():
    data = request.get_json(silent=True) or {}
    current_password = str(data.get("current_password", ""))
    exit_password, exit_password_error = validate_exit_password(
        data.get("exit_password")
    )
    errors = []
    if not current_password:
        errors.append("current_password is required.")
    elif len(current_password) > MAX_PASSWORD_LENGTH:
        errors.append(
            f"current_password must be {MAX_PASSWORD_LENGTH} characters or fewer."
        )
    if exit_password_error:
        errors.append(exit_password_error)
    if errors:
        return jsonify({"errors": errors}), 400

    key, window, blocked_response = _check_exit_configuration_limit()
    if blocked_response:
        return blocked_response
    if not current_user.check_password(current_password):
        exit_password_attempts.record_failure(key, window)
        return jsonify({"error": "The current account password is incorrect."}), 401

    try:
        current_user.set_exit_password(exit_password)
        db.session.commit()
        exit_password_attempts.reset(key)
        exit_password_attempts.reset(f"exit-password:{current_user.id}")
        return jsonify(
            {
                "message": "Exit password saved successfully.",
                "parent": current_user.to_dict(),
            }
        ), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Exit password could not be saved."}), 500


def remove_exit_password():
    data = request.get_json(silent=True) or {}
    current_password = str(data.get("current_password", ""))
    if not current_password:
        return jsonify({"errors": ["current_password is required."]}), 400
    if len(current_password) > MAX_PASSWORD_LENGTH:
        return jsonify(
            {
                "errors": [
                    f"current_password must be {MAX_PASSWORD_LENGTH} characters or fewer."
                ]
            }
        ), 400

    key, window, blocked_response = _check_exit_configuration_limit()
    if blocked_response:
        return blocked_response
    if not current_user.check_password(current_password):
        exit_password_attempts.record_failure(key, window)
        return jsonify({"error": "The current account password is incorrect."}), 401

    try:
        current_user.exit_password_hash = None
        db.session.commit()
        exit_password_attempts.reset(key)
        exit_password_attempts.reset(f"exit-password:{current_user.id}")
        return jsonify(
            {
                "message": "Exit password removed.",
                "parent": current_user.to_dict(),
            }
        ), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Exit password could not be removed."}), 500


def verify_exit_password():
    if not current_user.exit_password_hash:
        return jsonify({"error": "Exit protection is not enabled."}), 400

    data = request.get_json(silent=True) or {}
    exit_password = str(data.get("exit_password", ""))
    if not exit_password:
        return jsonify({"error": "Exit password is required."}), 400
    if len(exit_password) > MAX_EXIT_PASSWORD_LENGTH:
        return jsonify({"error": "The exit password is incorrect."}), 401

    key = f"exit-password:{current_user.id}"
    limit = current_app.config["EXIT_PASSWORD_RATE_LIMIT_ATTEMPTS"]
    window = current_app.config["EXIT_PASSWORD_RATE_LIMIT_WINDOW_SECONDS"]
    blocked, retry_after = exit_password_attempts.blocked(key, limit, window)
    if blocked:
        response = jsonify(
            {
                "error": (
                    "Too many incorrect exit password attempts. "
                    "Please try again later."
                )
            }
        )
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response
    if not current_user.check_exit_password(exit_password):
        exit_password_attempts.record_failure(key, window)
        return jsonify({"error": "The exit password is incorrect."}), 401

    exit_password_attempts.reset(key)
    return jsonify({"message": "Exit password verified."}), 200


def upload_profile_image_for_current_user():
    image = request.files.get("profile_image")
    if image is None or not image.filename:
        return jsonify({"error": "A profile image is required."}), 400
    try:
        validate_uploaded_file(image, "image")
        url, public_id = upload_profile_image(image, "accounts", current_user.id, current_app.config)
        old_public_id = current_user.profile_image_public_id
        current_user.profile_image_url = url
        current_user.profile_image_public_id = public_id
        db.session.commit()
        if old_public_id:
            try:
                delete_profile_image(old_public_id, current_app.config)
            except Exception:
                current_app.logger.exception("Could not delete the previous account profile image")
        return jsonify({"message": "Profile image updated successfully.", "parent": current_user.to_dict()}), 200
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Profile image upload failed."}), 500


def delete_profile_image_for_current_user():
    old_public_id = current_user.profile_image_public_id
    current_user.profile_image_url = None
    current_user.profile_image_public_id = None
    try:
        db.session.commit()
        if old_public_id:
            delete_profile_image(old_public_id, current_app.config)
        return jsonify({"message": "Profile image removed.", "parent": current_user.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Profile image removal failed."}), 500


def delete_me():
    parent = current_user
    try:
        asset_refs = collect_account_asset_refs(parent)
        db.session.delete(parent)  # cascades to children & voice_profiles
        db.session.commit()
        schedule_account_asset_cleanup(asset_refs)
        return jsonify({"message": "Account deleted successfully. External asset cleanup is in progress."}), 202
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500
