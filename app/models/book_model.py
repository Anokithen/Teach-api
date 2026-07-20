from app.extensions import db
from app.utils import utc_now


class Book(db.Model):
    __tablename__ = "books"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(200), nullable=False)
    age_group = db.Column(db.String(50), nullable=False)
    reading_level = db.Column(db.String(50), nullable=True)
    content_url = db.Column(db.String(500), nullable=True)
    text_content = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)

    mini_games = db.relationship(
        "MiniGame", backref="book", cascade="all, delete-orphan", lazy=True
    )
    reading_sessions = db.relationship("ReadingSession", backref="book", lazy=True)

    def to_dict(self, include_content=False):
        data = {
            "id": self.id,
            "title": self.title,
            "age_group": self.age_group,
            "reading_level": self.reading_level,
            "content_url": self.content_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_content:
            data["text_content"] = self.text_content
        return data
