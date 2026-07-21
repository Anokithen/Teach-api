"""Keep a child's reading level aligned with their lifetime earned points."""

from sqlalchemy import func

from app.extensions import db
from app.models.child_model import Child
from app.models.leaderboard_model import LeaderboardEntry


BEGINNER_MIN_POINTS = 0
INTERMEDIATE_MIN_POINTS = 500
ADVANCED_MIN_POINTS = 1000


def level_for_points(points):
    if points >= ADVANCED_MIN_POINTS:
        return "advanced"
    if points >= INTERMEDIATE_MIN_POINTS:
        return "intermediate"
    return "beginner"


def sync_child_reading_level(child_id):
    """Update and return a child's level from all leaderboard points earned."""
    child = db.session.get(Child, child_id)
    if not child:
        return None, 0, False

    total_points = db.session.query(
        func.coalesce(func.sum(LeaderboardEntry.points), 0)
    ).filter(LeaderboardEntry.child_id == child_id).scalar()
    new_level = level_for_points(int(total_points))
    changed = child.reading_level != new_level
    if changed:
        child.reading_level = new_level
    return child, int(total_points), changed
