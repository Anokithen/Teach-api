from flask import Blueprint
from app.controllers import admin_controller as ctrl
from app.middleware import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# --- Parents -----------------------------------------------------------

@admin_bp.route("/parents", methods=["GET"])
@admin_required
def list_parents():
    return ctrl.list_parents()


@admin_bp.route("/parents", methods=["POST"])
@admin_required
def register_parent():
    return ctrl.register_parent()


@admin_bp.route("/parents/<int:parent_id>", methods=["GET"])
@admin_required
def get_parent(parent_id):
    return ctrl.get_parent(parent_id)


@admin_bp.route("/parents/<int:parent_id>/ban", methods=["PATCH"])
@admin_required
def ban_parent(parent_id):
    return ctrl.ban_account(parent_id)


@admin_bp.route("/parents/<int:parent_id>/unban", methods=["PATCH"])
@admin_required
def unban_parent(parent_id):
    return ctrl.unban_account(parent_id)


@admin_bp.route("/parents/<int:parent_id>", methods=["DELETE"])
@admin_required
def delete_parent(parent_id):
    return ctrl.delete_account(parent_id)


# --- Teachers ------------------------------------------------------------

@admin_bp.route("/teachers", methods=["GET"])
@admin_required
def list_teachers():
    return ctrl.list_teachers()


@admin_bp.route("/teachers", methods=["POST"])
@admin_required
def register_teacher():
    return ctrl.register_teacher()


@admin_bp.route("/teachers/<int:teacher_id>/ban", methods=["PATCH"])
@admin_required
def ban_teacher(teacher_id):
    return ctrl.ban_account(teacher_id)


@admin_bp.route("/teachers/<int:teacher_id>/unban", methods=["PATCH"])
@admin_required
def unban_teacher(teacher_id):
    return ctrl.unban_account(teacher_id)


@admin_bp.route("/teachers/<int:teacher_id>", methods=["DELETE"])
@admin_required
def delete_teacher(teacher_id):
    return ctrl.delete_account(teacher_id)


# --- Other admins (bootstrap additional admin accounts) -------------------

@admin_bp.route("/admins", methods=["POST"])
@admin_required
def register_admin():
    return ctrl.register_admin()


# --- Books --------------------------------------------------------------

@admin_bp.route("/books", methods=["POST"])
@admin_required
def create_book():
    return ctrl.create_book()
