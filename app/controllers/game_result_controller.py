from datetime import timedelta

from flask import jsonify, request

from app.extensions import db
from app.utils import utc_now
from app.models.child_model import Child
from app.models.mini_game_model import MiniGame
from app.models.game_result_model import GameResult
from app.models.leaderboard_model import LeaderboardEntry
from app.middleware import child_belongs_to_current_parent


def _current_week_start():
    today = utc_now().date()
    return today - timedelta(days=today.weekday())  # Monday of the current week


def _award_leaderboard_points(child_id, points):
    week_start = _current_week_start()
    entry = LeaderboardEntry.query.filter_by(child_id=child_id, week_start=week_start).first()
    if not entry:
        entry = LeaderboardEntry(child_id=child_id, week_start=week_start, points=0, streak_count=0)
        db.session.add(entry)
    entry.points += points
    return entry


def submit_game_result(game_id):
    game = db.session.get(MiniGame, game_id)
    if not game:
        return jsonify({"error": "Mini-game not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required."}), 400

    errors = []
    child_id = data.get("child_id")
    child = db.session.get(Child, child_id) if child_id else None
    if not child_id or not child_belongs_to_current_parent(child):
        errors.append("A valid child_id belonging to this account is required.")

    score = data.get("score")
    if score is None:
        errors.append("score is required.")
    else:
        try:
            score = int(score)
            if score < 0:
                errors.append("score cannot be negative.")
        except (TypeError, ValueError):
            errors.append("score must be a whole number.")

    if errors:
        return jsonify({"errors": errors}), 400

    try:
        result = GameResult(
            child_id=child_id,
            game_id=game_id,
            score=score,
            completed_at=utc_now(),
        )
        db.session.add(result)
        _award_leaderboard_points(child_id, score)
        db.session.commit()
        return jsonify(
            {"message": "Game result submitted.", "game_result": result.to_dict()}
        ), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def list_child_game_results(child_id):
    child = db.session.get(Child, child_id)
    if not child_belongs_to_current_parent(child):
        return jsonify({"error": "Child not found."}), 404

    results = (
        GameResult.query.filter_by(child_id=child_id)
        .order_by(GameResult.completed_at.desc())
        .all()
    )
    return jsonify({"game_results": [r.to_dict() for r in results]}), 200
