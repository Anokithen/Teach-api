from flask import jsonify, request
from flask_jwt_extended import current_user
from email_validator import validate_email, EmailNotValidError

from app.extensions import db
from app.models.parent_model import Parent


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


def delete_me():
    parent = current_user
    try:
        db.session.delete(parent)  # cascades to children & voice_profiles
        db.session.commit()
        return jsonify({"message": "Account and all associated data deleted successfully."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500
