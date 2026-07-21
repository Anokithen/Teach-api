from app.extensions import db
from app.utils import utc_now


class Child(db.Model):
    __tablename__ = "children"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("parents.id"), nullable=False)
    # Who actually created the record: the parent themself, or a teacher
    # adding a child on the parent's behalf. Nullable for pre-existing rows.
    created_by_id = db.Column(db.Integer, db.ForeignKey("parents.id"), nullable=True)
    name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(30), nullable=False, default="prefer_not_to_say")
    reading_level = db.Column(db.String(50), nullable=False, default="beginner")
    pin_hash = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)

    reading_sessions = db.relationship(
        "ReadingSession", backref="child", cascade="all, delete-orphan", lazy=True
    )
    game_results = db.relationship(
        "GameResult", backref="child", cascade="all, delete-orphan", lazy=True
    )
    leaderboard_entries = db.relationship(
        "LeaderboardEntry", backref="child", cascade="all, delete-orphan", lazy=True
    )

    def to_dict(self):
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "created_by_id": self.created_by_id,
            "name": self.name,
            "age": self.age,
            "gender": self.gender,
            "reading_level": self.reading_level,
            "has_pin": bool(self.pin_hash),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
