import os

from flask import Flask, jsonify
from flask_cors import CORS
from werkzeug.exceptions import RequestEntityTooLarge
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.config import Config
from app.extensions import db, jwt
from app.routes import register_blueprints


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["FRONTEND_ORIGINS"]}},
        allow_headers=["Authorization", "Content-Type"],
        methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    )
    db.init_app(app)
    jwt.init_app(app)

    from app.models import Parent  # noqa: F401  (this import loads app/models/__init__.py,
    # which in turn imports every model class so they register with SQLAlchemy)

    if os.getenv("AUTO_CREATE_TABLES", "true").lower() == "true":
        with app.app_context():
            try:
                db.create_all()
            except Exception as exc:  # pragma: no cover - startup diagnostics only
                app.logger.error("Could not create database tables: %s", exc)

    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data["sub"]
        return db.session.get(Parent, int(identity))

    @jwt.user_identity_loader
    def user_identity_lookup(parent):
        # allows create_access_token(identity=parent) or identity=parent.id
        return str(parent.id) if hasattr(parent, "id") else str(parent)

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(_jwt_header, jwt_payload):
        from app.controllers.auth_controller import BLOCKLIST
        if jwt_payload["jti"] in BLOCKLIST:
            return True

        # A banned account's outstanding tokens are treated as revoked too,
        # so a ban takes effect immediately instead of waiting for expiry.
        identity = jwt_payload.get("sub")
        if identity is not None:
            parent = db.session.get(Parent, int(identity))
            if parent is None or parent.is_banned:
                return True
        return False

    register_blueprints(app)

    @app.errorhandler(OperationalError)
    def handle_operational_error(err):
        db.session.rollback()
        orig = getattr(err, "orig", None)
        code = orig.args[0] if orig and orig.args else None
        if code == 1049:
            return jsonify({"error": "Invalid database name configured."}), 500
        if code in (2003, 2002):
            return jsonify({"error": "MySQL server is not running or not reachable."}), 503
        return jsonify({"error": "Database connection failed."}), 500

    @app.errorhandler(ProgrammingError)
    def handle_programming_error(err):
        db.session.rollback()
        return jsonify({"error": "Invalid database name configured."}), 500

    @app.errorhandler(404)
    def handle_not_found(err):
        return jsonify({"error": "Resource not found."}), 404

    @app.errorhandler(500)
    def handle_internal_error(err):
        return jsonify({"error": "An internal server error occurred."}), 500

    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(err):
        return jsonify({"error": "The recording must be smaller than 25 MB."}), 413

    return app
