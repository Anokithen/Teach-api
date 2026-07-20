from flask import jsonify, request
from flask_jwt_extended import current_user

from app.extensions import db
from app.models.child_model import Child
from app.models.parent_model import Parent, ROLE_PARENT
from app.middleware import can_access_child


def _validate_child_payload(data, partial=False):
    errors = []
    if not data:
        return ["Request body is required."]

    if "name" in data or not partial:
        name = data.get("name")
        if name is None or str(name).strip() == "":
            errors.append("name is required.")

    if "age" in data or not partial:
        age = data.get("age")
        if age is None:
            errors.append("age is required.")
        else:
            try:
                age_int = int(age)
                if age_int <= 0 or age_int > 18:
                    errors.append("age must be a realistic value between 1 and 18.")
            except (TypeError, ValueError):
                errors.append("age must be a whole number.")

    if "reading_level" in data and data.get("reading_level") is not None:
        if str(data.get("reading_level")).strip() == "":
            errors.append("reading_level cannot be empty.")

    return errors


def _resolve_owning_parent(data):
    """Figures out which parent account a new child should belong to.

    - A parent account always creates children for themself.
    - A teacher account must supply `parent_id`, referencing an existing,
      non-banned parent account.
    Returns (parent_id, errors).
    """
    if current_user.role == ROLE_PARENT:
        return current_user.id, []

    # Teacher (or any other non-parent role permitted to reach this function)
    parent_id = data.get("parent_id") if data else None
    if not parent_id:
        return None, ["parent_id is required when a teacher adds a child."]

    owning_parent = db.session.get(Parent, parent_id)
    if not owning_parent or owning_parent.role != ROLE_PARENT:
        return None, ["parent_id must reference an existing parent account."]
    if owning_parent.is_banned:
        return None, ["This parent account has been banned and cannot have children added."]

    return owning_parent.id, []


def create_child():
    data = request.get_json(silent=True)
    errors = _validate_child_payload(data)

    parent_id, owner_errors = _resolve_owning_parent(data or {})
    errors.extend(owner_errors)

    if errors:
        return jsonify({"errors": errors}), 400

    try:
        child = Child(
            parent_id=parent_id,
            created_by_id=current_user.id,
            name=str(data.get("name")).strip(),
            age=int(data.get("age")),
            reading_level=str(data.get("reading_level")).strip()
            if data.get("reading_level")
            else "beginner",
        )
        db.session.add(child)
        db.session.commit()
        return jsonify({"message": "Child profile created successfully.", "child": child.to_dict()}), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def list_children():
    """GET /api/children

    - Parent: only their own children.
    - Teacher: only the children they personally added.
    - Admin: every child in the system (also available via /api/admin/children).
    """
    if current_user.is_admin:
        children = Child.query.order_by(Child.id.desc()).all()
    elif current_user.is_teacher:
        children = (
            Child.query.filter_by(created_by_id=current_user.id)
            .order_by(Child.id.desc())
            .all()
        )
    else:
        children = Child.query.filter_by(parent_id=current_user.id).order_by(Child.id.desc()).all()

    return jsonify({"children": [c.to_dict() for c in children]}), 200


def get_child(child_id):
    child = db.session.get(Child, child_id)
    if not can_access_child(child):
        return jsonify({"error": "Child not found."}), 404

    stats = {
        "total_sessions": len(child.reading_sessions),
        "total_game_results": len(child.game_results),
    }
    data = child.to_dict()
    data["stats"] = stats
    return jsonify({"child": data}), 200


def update_child(child_id):
    child = db.session.get(Child, child_id)
    if not can_access_child(child):
        return jsonify({"error": "Child not found."}), 404

    data = request.get_json(silent=True)
    errors = _validate_child_payload(data, partial=True)
    if errors:
        return jsonify({"errors": errors}), 400

    try:
        if "name" in data:
            child.name = str(data.get("name")).strip()
        if "age" in data:
            child.age = int(data.get("age"))
        if "reading_level" in data:
            child.reading_level = str(data.get("reading_level")).strip()

        db.session.commit()
        return jsonify({"message": "Child profile updated successfully.", "child": child.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def delete_child(child_id):
    child = db.session.get(Child, child_id)
    if not can_access_child(child):
        return jsonify({"error": "Child not found."}), 404

    try:
        db.session.delete(child)
        db.session.commit()
        return jsonify({"message": "Child profile removed successfully."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500
