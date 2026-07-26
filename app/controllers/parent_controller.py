from flask import current_app, jsonify, request
from flask_jwt_extended import current_user
from email_validator import validate_email, EmailNotValidError

from app.extensions import db
from app.models.parent_model import Parent
from app.services.account_cleanup_service import collect_account_asset_refs, schedule_account_asset_cleanup
from app.controllers import asset_controller
from app.models.asset_model import Asset, STATUS_DELETED, USER_PROFILE_IMAGE
from app.services.cloudinary_service import delete_asset, delete_profile_image
from app.utils import utc_now


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
    image, error = asset_controller._validated_file(USER_PROFILE_IMAGE, "image")
    if error:
        return error
    try:
        asset_controller._save_profile(
            image,
            USER_PROFILE_IMAGE,
            asset_controller.get_user_profile_folder(current_user.id),
            current_user.id,
        )
        return jsonify({"message": "Profile image updated successfully.", "parent": current_user.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Profile image upload failed."}), 500


def delete_profile_image_for_current_user():
    asset = Asset.query.filter_by(
        owner_user_id=current_user.id,
        asset_category=USER_PROFILE_IMAGE,
        deleted_at=None,
    ).first()
    try:
        if asset:
            delete_asset(
                asset.cloudinary_public_id,
                asset.cloudinary_resource_type,
                asset.cloudinary_delivery_type,
            )
            asset.status = STATUS_DELETED
            asset.deleted_at = utc_now()
            asset.active_slot = None
        elif current_user.profile_image_public_id:
            delete_profile_image(current_user.profile_image_public_id, current_app.config)
        current_user.profile_image_url = None
        current_user.profile_image_public_id = None
        db.session.commit()
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
