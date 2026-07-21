from flask import jsonify, request
from flask_jwt_extended import current_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.child_model import Child
from app.models.parent_model import Parent, ROLE_PARENT
from app.middleware import can_access_child
from app.services.reading_level import sync_child_reading_level

VALID_GENDERS = ("male", "female", "other", "prefer_not_to_say")


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
        elif partial:
            errors.append("reading_level is calculated automatically from earned points.")

    if "gender" in data and data.get("gender") not in VALID_GENDERS:
        errors.append("gender must be male, female, other, or prefer_not_to_say.")

    if "child_pin" in data and data.get("child_pin") not in (None, ""):
        pin = str(data.get("child_pin"))
        if not pin.isdigit() or len(pin) != 6:
            errors.append("child_pin must be exactly 6 digits.")
        elif current_user.role != ROLE_PARENT:
            errors.append("Only the child's parent can set a profile PIN.")

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
            gender=data.get("gender", "prefer_not_to_say"),
            reading_level="beginner",
            pin_hash=generate_password_hash(str(data["child_pin"])) if data.get("child_pin") else None,
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

    level_changed = False
    for child in children:
        _, _, changed = sync_child_reading_level(child.id)
        level_changed = level_changed or changed
    if level_changed:
        db.session.commit()
    return jsonify({"children": [c.to_dict() for c in children]}), 200


def get_child(child_id):
    child = db.session.get(Child, child_id)
    if not can_access_child(child):
        return jsonify({"error": "Child not found."}), 404

    if sync_child_reading_level(child.id)[2]:
        db.session.commit()

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
        # Reading level is calculated from lifetime points and cannot be set manually.
        if data.get("child_pin"):
            child.pin_hash = generate_password_hash(str(data["child_pin"]))

        db.session.commit()
        return jsonify({"message": "Child profile updated successfully.", "child": child.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def verify_child_pin(child_id):
    """Verify the six-digit PIN before opening a protected child profile."""
    child = db.session.get(Child, child_id)
    if not can_access_child(child):
        return jsonify({"error": "Child not found."}), 404

    data = request.get_json(silent=True) or {}
    pin = str(data.get("pin", ""))
    if not child.pin_hash or not pin.isdigit() or len(pin) != 6 or not check_password_hash(child.pin_hash, pin):
        return jsonify({"error": "That PIN is not correct."}), 401

    return jsonify({"message": "PIN verified."}), 200


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
