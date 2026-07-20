from flask import jsonify, request
from flask_jwt_extended import current_user

from app.extensions import db
from app.utils import utc_now
from app.models.child_model import Child
from app.models.reading_session_model import ReadingSession
from app.models.feedback_model import Feedback
from app.models.game_result_model import GameResult
from app.middleware import child_belongs_to_current_parent
from app.controllers.game_result_controller import _award_leaderboard_points


def sync_offline_activity():
    """POST /api/sync

    Batch-uploads reading sessions, feedback, and game results recorded while
    offline, and reconciles them in one transaction.

    Expected payload shape:
    {
      "reading_sessions": [
        {"client_id": "local-1", "child_id": 1, "book_id": 3, "voice_profile_id": 2,
         "started_at": "...", "completed_at": "...", "accuracy_score": 92,
         "progress_log": [...] }
      ],
      "feedback": [
        {"session_client_id": "local-1", "feedback_text": "...", "feedback_type": "praise"}
      ],
      "game_results": [
        {"child_id": 1, "game_id": 5, "score": 40, "completed_at": "..."}
      ]
    }

    `client_id` / `session_client_id` let the mobile app reference a session
    created earlier in the same batch, since it won't have a server-side id yet.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required."}), 400

    reading_sessions_in = data.get("reading_sessions", []) or []
    feedback_in = data.get("feedback", []) or []
    game_results_in = data.get("game_results", []) or []

    client_id_to_session = {}
    created_sessions, created_feedback, created_results = [], [], []
    errors = []

    try:
        # 1. Reading sessions first, so feedback can reference them by client_id.
        for item in reading_sessions_in:
            child_id = item.get("child_id")
            child = db.session.get(Child, child_id) if child_id else None
            if not child_id or not child_belongs_to_current_parent(child):
                errors.append(f"reading_session with client_id={item.get('client_id')}: invalid or unauthorized child_id.")
                continue

            session = ReadingSession(
                child_id=child_id,
                book_id=item.get("book_id"),
                voice_profile_id=item.get("voice_profile_id"),
                started_at=item.get("started_at") or utc_now(),
                completed_at=item.get("completed_at"),
                accuracy_score=item.get("accuracy_score"),
                progress_log=item.get("progress_log"),
            )
            db.session.add(session)
            db.session.flush()  # assign session.id without committing
            created_sessions.append(session)
            if item.get("client_id"):
                client_id_to_session[item["client_id"]] = session.id

        # 2. Feedback, resolved against either a synced session_id or a client_id.
        for item in feedback_in:
            session_id = item.get("session_id") or client_id_to_session.get(item.get("session_client_id"))
            if not session_id:
                errors.append("feedback entry: could not resolve its reading session.")
                continue

            feedback = Feedback(
                session_id=session_id,
                feedback_text=item.get("feedback_text", ""),
                feedback_type=item.get("feedback_type", "tip"),
            )
            db.session.add(feedback)
            created_feedback.append(feedback)

        # 3. Game results, awarding leaderboard points as usual.
        for item in game_results_in:
            child_id = item.get("child_id")
            child = db.session.get(Child, child_id) if child_id else None
            if not child_id or not child_belongs_to_current_parent(child):
                errors.append("game_result entry: invalid or unauthorized child_id.")
                continue

            score = int(item.get("score", 0))
            result = GameResult(
                child_id=child_id,
                game_id=item.get("game_id"),
                score=score,
                completed_at=item.get("completed_at") or utc_now(),
            )
            db.session.add(result)
            _award_leaderboard_points(child_id, score)
            created_results.append(result)

        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred while syncing."}), 500

    return jsonify(
        {
            "message": "Sync complete.",
            "synced": {
                "reading_sessions": len(created_sessions),
                "feedback": len(created_feedback),
                "game_results": len(created_results),
            },
            "reading_session_ids": {cid: sid for cid, sid in client_id_to_session.items()},
            "errors": errors,
        }
    ), 200
