from flask import current_app, jsonify, request
from flask_jwt_extended import current_user
from email_validator import validate_email, EmailNotValidError

from app.extensions import db
from app.models.parent_model import Parent
from app.services.cloudinary_service import delete_profile_image, upload_profile_image, validate_uploaded_file


def get_me():
    return jsonify({"parent": current_user.to_dict()}), 200


def update_me():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required."}), 400

    errors = []
    parent = current_user

    if "name" in data:
        name = data.get("name")
        if not name or str(name).strip() == "":
            errors.append("name cannot be empty.")

    if "email" in data:
        email = data.get("email")
        if not email or str(email).strip() == "":
            errors.append("email cannot be empty.")
        else:
            try:
                emailinfo = validate_email(str(email).strip(), check_deliverability=False)
                data["email"] = emailinfo.normalized
                existing = Parent.query.filter_by(email=data["email"]).first()
                if existing and existing.id != parent.id:
                    errors.append("An account with this email already exists.")
            except EmailNotValidError as e:
                errors.append(str(e))

    if "password" in data:
        password = data.get("password")
        if not password or len(str(password)) < 6:
            errors.append("password must be at least 6 characters.")

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
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


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
    image_ids = [parent.profile_image_public_id]
    image_ids.extend(child.profile_image_public_id for child in parent.children)
    try:
        db.session.delete(parent)  # cascades to children & voice_profiles
        db.session.commit()
        for public_id in image_ids:
            if public_id:
                try:
                    delete_profile_image(public_id, current_app.config)
                except Exception:
                    current_app.logger.exception("Could not delete a profile image during account removal")
        return jsonify({"message": "Account and all associated data deleted successfully."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500
