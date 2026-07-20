from flask import jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
)
from email_validator import validate_email, EmailNotValidError

from app.extensions import db
from app.models.parent_model import Parent

# In-memory blocklist for logout. Swap for Redis/DB in production.
BLOCKLIST = set()


def _validate_register_payload(data):
    errors = []

    if not data:
        return ["Request body is required."]

    name = data.get("name")
    if name is None or str(name).strip() == "":
        errors.append("name is required.")

    email = data.get("email")
    if email is None or str(email).strip() == "":
        errors.append("email is required.")
    else:
        try:
            emailinfo = validate_email(str(email).strip(), check_deliverability=False)
            data["email"] = emailinfo.normalized
        except EmailNotValidError as e:
            errors.append(str(e))

    password = data.get("password")
    if password is None or str(password).strip() == "":
        errors.append("password is required.")
    elif len(str(password)) < 6:
        errors.append("password must be at least 6 characters.")

    return errors


def _validate_login_payload(data):
    errors = []

    if not data:
        return ["Request body is required."]

    if not data.get("email"):
        errors.append("email is required.")
    if not data.get("password"):
        errors.append("password is required.")

    return errors


# def register():
#     data = request.get_json(silent=True)
#     errors = _validate_register_payload(data)
#     if errors:
#         return jsonify({"errors": errors}), 400

#     email = str(data.get("email")).strip()
#     if Parent.query.filter_by(email=email).first():
#         return jsonify({"error": "An account with this email already exists."}), 409
    

#     role = data.get("role")

    

#     try:
#         # Public self-registration always creates a "parent" account. Teacher
#         # and admin accounts can only be created by an existing admin, via
#         # the /api/admin endpoints — role is never taken from client input here.
#         parent = Parent(name=str(data.get("name")).strip(), email=email, role="parent")
#         parent.set_password(str(data.get("password")))

#         db.session.add(parent)
#         db.session.commit()
#         return jsonify(
#             {"message": "Parent account created successfully.", "parent": parent.to_dict()}
#         ), 201
#     except Exception:
#         db.session.rollback()
#         return jsonify({"error": "An internal server error occurred."}), 500


def register():
    data = request.get_json(silent=True)
    errors = _validate_register_payload(data)
    if errors:
        return jsonify({"errors": errors}), 400

    email = str(data.get("email")).strip().lower()

    if Parent.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists."}), 409

    # Get the requested role
    role = str(data.get("role", "parent")).strip().lower()

    # Only allow parent or teacher
    if role not in ["parent", "teacher"]:
        return jsonify({
            "error": "Invalid role. You can only register as a parent or teacher."
        }), 400

    try:
        parent = Parent(
            name=str(data.get("name")).strip(),
            email=email,
            role=role
        )

        parent.set_password(str(data.get("password")))

        db.session.add(parent)
        db.session.commit()

        return jsonify({
            "message": f"{role.capitalize()} account created successfully.",
            "parent": parent.to_dict()
        }), 201

    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def login():
    data = request.get_json(silent=True)
    errors = _validate_login_payload(data)
    if errors:
        return jsonify({"errors": errors}), 400

    try:
        email = str(data.get("email")).strip()
        parent = Parent.query.filter_by(email=email).first()

        if not parent or not parent.check_password(str(data.get("password"))):
            return jsonify({"error": "Invalid email or password."}), 401

        if parent.is_banned:
            return jsonify({"error": "This account has been banned. Contact an administrator."}), 403

        access_token = create_access_token(identity=parent)
        refresh_token = create_refresh_token(identity=parent)
        return jsonify(
            {
                "message": "Login successful.",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "parent": parent.to_dict(),
            }
        ), 200
    except Exception:
        return jsonify({"error": "An internal server error occurred."}), 500


@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    parent = db.session.get(Parent, int(identity))
    if not parent:
        return jsonify({"error": "Account not found."}), 404
    if parent.is_banned:
        return jsonify({"error": "This account has been banned. Contact an administrator."}), 403
    access_token = create_access_token(identity=parent)
    return jsonify({"access_token": access_token}), 200


@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    BLOCKLIST.add(jti)
    return jsonify({"message": "Logged out successfully."}), 200
