from flask import jsonify, request
from flask_jwt_extended import current_user

from app.extensions import db
from app.utils import utc_now
from app.models.child_model import Child
from app.models.book_model import Book
from app.models.voice_profile_model import VoiceProfile
from app.models.reading_session_model import ReadingSession
from app.middleware import child_belongs_to_current_parent, voice_profile_belongs_to_current_parent


def _session_belongs_to_current_parent(session):
    if session is None:
        return False
    child = db.session.get(Child, session.child_id)
    return child_belongs_to_current_parent(child)


def create_reading_session():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required."}), 400

    errors = []
    child_id = data.get("child_id")
    book_id = data.get("book_id")
    voice_profile_id = data.get("voice_profile_id")

    child = db.session.get(Child, child_id) if child_id else None
    if not child_id or not child_belongs_to_current_parent(child):
        errors.append("A valid child_id belonging to this account is required.")

    book = db.session.get(Book, book_id) if book_id else None
    if not book_id or not book:
        errors.append("A valid book_id is required.")

    voice_profile = None
    if voice_profile_id is not None:
        voice_profile = db.session.get(VoiceProfile, voice_profile_id)
        if not voice_profile_belongs_to_current_parent(voice_profile):
            errors.append("voice_profile_id must reference a voice profile owned by this account.")
        elif voice_profile.status != "ready":
            errors.append("The selected voice profile is not ready yet.")

    if errors:
        return jsonify({"errors": errors}), 400

    try:
        session = ReadingSession(
            child_id=child_id,
            book_id=book_id,
            voice_profile_id=voice_profile_id,
            started_at=utc_now(),
        )
        db.session.add(session)
        db.session.commit()
        return jsonify(
            {"message": "Reading session started.", "reading_session": session.to_dict()}
        ), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def update_reading_session(session_id):
    session = db.session.get(ReadingSession, session_id)
    if not _session_belongs_to_current_parent(session):
        return jsonify({"error": "Reading session not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required."}), 400

    try:
        if "progress_entry" in data:
            entry = data.get("progress_entry")
            log = list(session.progress_log or [])
            log.append(entry)
            session.progress_log = log

        if "accuracy_score" in data and data.get("accuracy_score") is not None:
            session.accuracy_score = float(data.get("accuracy_score"))

        if data.get("mark_complete"):
            session.completed_at = utc_now()

        db.session.commit()
        return jsonify(
            {"message": "Reading session updated.", "reading_session": session.to_dict()}
        ), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def get_reading_session(session_id):
    session = db.session.get(ReadingSession, session_id)
    if not _session_belongs_to_current_parent(session):
        return jsonify({"error": "Reading session not found."}), 404
    return jsonify({"reading_session": session.to_dict()}), 200


def list_child_reading_sessions(child_id):
    child = db.session.get(Child, child_id)
    if not child_belongs_to_current_parent(child):
        return jsonify({"error": "Child not found."}), 404

    sessions = (
        ReadingSession.query.filter_by(child_id=child_id)
        .order_by(ReadingSession.started_at.desc())
        .all()
    )
    return jsonify({"reading_sessions": [s.to_dict() for s in sessions]}), 200
