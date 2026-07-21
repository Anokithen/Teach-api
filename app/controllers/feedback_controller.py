from flask import jsonify

from app.extensions import db
from app.models.reading_session_model import ReadingSession
from app.models.feedback_model import Feedback
from app.controllers.reading_session_controller import _session_belongs_to_current_parent

def list_feedback(session_id):
    session = db.session.get(ReadingSession, session_id)
    if not _session_belongs_to_current_parent(session):
        return jsonify({"error": "Reading session not found."}), 404

    entries = (
        Feedback.query.filter_by(session_id=session_id)
        .order_by(Feedback.created_at.asc())
        .all()
    )
    return jsonify({"feedback": [f.to_dict() for f in entries]}), 200
