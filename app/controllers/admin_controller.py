from flask import current_app, jsonify, request
from flask_jwt_extended import current_user
from email_validator import validate_email, EmailNotValidError
from urllib.parse import urlparse

from app.extensions import db
from app.models.parent_model import Parent, ROLE_PARENT, ROLE_TEACHER, ROLE_ADMIN, VALID_ROLES
from app.models.child_model import Child
from app.models.book_model import Book
from app.services.book_games import create_default_mini_games
from app.services.cloudinary_service import upload_book_media


def _validate_new_account_payload(data):
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


def _create_account(role):
    data = request.get_json(silent=True)
    errors = _validate_new_account_payload(data)
    if errors:
        return jsonify({"errors": errors}), 400

    email = str(data.get("email")).strip()
    if Parent.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists."}), 409

    try:
        account = Parent(name=str(data.get("name")).strip(), email=email, role=role)
        account.set_password(str(data.get("password")))
        db.session.add(account)
        db.session.commit()
        return jsonify(
            {"message": f"{role.capitalize()} account created successfully.", "account": account.to_dict()}
        ), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def register_parent():
    """POST /api/admin/parents — admin creates a parent account directly."""
    return _create_account(ROLE_PARENT)


def register_teacher():
    """POST /api/admin/teachers — admin creates a teacher account."""
    return _create_account(ROLE_TEACHER)


def register_admin():
    """POST /api/admin/admins — an existing admin creates another admin account."""
    return _create_account(ROLE_ADMIN)


def create_book():
    """POST /api/admin/books — create a catalog book and its standard games."""
    data = request.get_json(silent=True) or {}
    errors = []
    title = str(data.get("title", "")).strip()
    age_group = str(data.get("age_group", "")).strip()
    reading_level = str(data.get("reading_level", "")).strip().lower()
    valid_levels = {"beginner", "intermediate", "advanced"}

    def optional_web_url(field_name):
        value = str(data.get(field_name, "")).strip()
        if not value:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"{field_name} must be a valid http or https URL.")
            return None
        return value

    cover_image_url = optional_web_url("cover_image_url")
    video_url = optional_web_url("video_url")

    if not title:
        errors.append("title is required.")
    if not age_group:
        errors.append("age_group is required.")
    if reading_level not in valid_levels:
        errors.append("reading_level must be beginner, intermediate, or advanced.")
    if errors:
        return jsonify({"errors": errors}), 400

    try:
        book = Book(
            title=title,
            age_group=age_group,
            reading_level=reading_level,
            text_content=str(data.get("text_content", "")).strip() or None,
            content_url=str(data.get("content_url", "")).strip() or None,
            cover_image_url=cover_image_url,
            video_url=video_url,
        )
        db.session.add(book)
        db.session.flush()
        create_default_mini_games(book)
        db.session.commit()
        return jsonify({
            "message": "Book created with word puzzle, spelling, and quiz games.",
            "book": book.to_dict(include_content=True),
            "mini_games": [game.to_dict(include_content=True) for game in book.mini_games],
        }), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def upload_book_media_file():
    """Admin-only upload endpoint used before a book is created."""
    media = request.files.get("file")
    media_type = str(request.form.get("media_type", "")).strip().lower()
    if not media or not media.filename:
        return jsonify({"errors": ["A media file is required."]}), 400
    if media_type not in {"image", "video"}:
        return jsonify({"errors": ["media_type must be image or video."]}), 400
    try:
        return jsonify({"url": upload_book_media(media, media_type, current_app.config)}), 201
    except ValueError as exc:
        return jsonify({"errors": [str(exc)]}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception:
        return jsonify({"error": "The media file could not be uploaded."}), 500


def _list_accounts_by_role(role):
    accounts = Parent.query.filter_by(role=role).order_by(Parent.id.desc()).all()
    results = []
    for account in accounts:
        item = account.to_dict()
        if role == ROLE_PARENT:
            item["children_count"] = Child.query.filter_by(parent_id=account.id).count()
        results.append(item)
    return results


def list_parents():
    """GET /api/admin/parents"""
    return jsonify({"parents": _list_accounts_by_role(ROLE_PARENT)}), 200


def list_teachers():
    """GET /api/admin/teachers"""
    return jsonify({"teachers": _list_accounts_by_role(ROLE_TEACHER)}), 200


def get_parent(parent_id):
    """GET /api/admin/parents/<id> — full detail including their children."""
    parent = db.session.get(Parent, parent_id)
    if not parent or parent.role != ROLE_PARENT:
        return jsonify({"error": "Parent not found."}), 404

    children = Child.query.filter_by(parent_id=parent.id).order_by(Child.id.desc()).all()
    data = parent.to_dict()
    data["children"] = [c.to_dict() for c in children]
    return jsonify({"parent": data}), 200


def _get_target_account(account_id):
    account = db.session.get(Parent, account_id)
    if not account:
        return None, (jsonify({"error": "Account not found."}), 404)
    if account.id == current_user.id:
        return None, (jsonify({"error": "You cannot perform this action on your own account."}), 400)
    if account.is_admin:
        return None, (jsonify({"error": "Admin accounts cannot be managed through this endpoint."}), 403)
    return account, None


def ban_account(account_id):
    """PATCH /api/admin/parents/<id>/ban or /api/admin/teachers/<id>/ban"""
    account, error_response = _get_target_account(account_id)
    if error_response:
        return error_response

    try:
        account.is_banned = True
        db.session.commit()
        return jsonify({"message": "Account banned successfully.", "account": account.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def unban_account(account_id):
    """PATCH /api/admin/parents/<id>/unban or /api/admin/teachers/<id>/unban"""
    account, error_response = _get_target_account(account_id)
    if error_response:
        return error_response

    try:
        account.is_banned = False
        db.session.commit()
        return jsonify({"message": "Account unbanned successfully.", "account": account.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def delete_account(account_id):
    """DELETE /api/admin/parents/<id> or /api/admin/teachers/<id>

    Deleting a parent cascades to their children and voice profiles, same as
    a parent deleting their own account.
    """
    account, error_response = _get_target_account(account_id)
    if error_response:
        return error_response

    try:
        db.session.delete(account)
        db.session.commit()
        return jsonify({"message": "Account deleted successfully."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500
