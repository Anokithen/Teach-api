"""Create a complete, repeatable TeachAlike demo dataset.

Run from the API directory after configuring the database connection:

    python seed.py

The script is idempotent: it creates missing demo records but never deletes or
overwrites existing data. For an existing database, apply SQL files in
``migrations/`` before running this script.
"""
import os
from datetime import date, datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models.book_model import Book
from app.models.child_model import Child
from app.models.feedback_model import Feedback
from app.models.game_result_model import GameResult
from app.models.leaderboard_model import LeaderboardEntry
from app.models.mini_game_model import MiniGame
from app.models.parent_model import Parent, ROLE_ADMIN, ROLE_PARENT, ROLE_TEACHER
from app.models.reading_session_model import ReadingSession
from app.models.voice_profile_model import STATUS_READY, VoiceProfile
from app.services.book_games import create_default_mini_games


BOOKS = (
    {
        "title": "The Curious Fox",
        "age_group": "4-6",
        "reading_level": "beginner",
        "content_url": "https://cdn.teachalike.app/books/curious-fox.json",
        "text_content": "Fiona the curious fox explored the sunny forest. She found a bright butterfly beside a sleepy rabbit. Together they followed a sparkling stream home before sunset.",
    },
    {
        "title": "Adventures in Space",
        "age_group": "7-9",
        "reading_level": "intermediate",
        "content_url": "https://cdn.teachalike.app/books/adventures-in-space.json",
        "text_content": "Captain Mia climbed into her rocket ship and visited the moon. She watched silver stars, met a friendly robot, and safely returned home.",
    },
    {
        "title": "Milo's Rainy Day Garden",
        "age_group": "4-6",
        "reading_level": "beginner",
        "content_url": "https://cdn.teachalike.app/books/milos-rainy-day-garden.json",
        "text_content": "Milo planted tiny seeds in his garden before the rain arrived. The next morning, colourful flowers opened and welcomed every buzzing bee.",
    },
)


def get_setting(name, default):
    return os.getenv(name, default)


def ensure_account(name, email, password, role):
    account = Parent.query.filter_by(email=email).first()
    if account:
        return account, False
    account = Parent(name=name, email=email, role=role)
    account.set_password(password)
    db.session.add(account)
    db.session.flush()
    return account, True


def ensure_child(parent, name, age, gender, reading_level, pin):
    child = Child.query.filter_by(parent_id=parent.id, name=name).first()
    if child:
        return child, False
    child = Child(
        parent_id=parent.id,
        created_by_id=parent.id,
        name=name,
        age=age,
        gender=gender,
        reading_level=reading_level,
        pin_hash=generate_password_hash(pin),
    )
    db.session.add(child)
    db.session.flush()
    return child, True


def ensure_book(book_data):
    book = Book.query.filter_by(title=book_data["title"]).first()
    if book:
        return book, False
    book = Book(**book_data)
    db.session.add(book)
    db.session.flush()
    return book, True


def ensure_voice_profile(parent):
    profile = VoiceProfile.query.filter_by(parent_id=parent.id, label="Demo parent voice").first()
    if profile:
        return profile, False
    profile = VoiceProfile(
        parent_id=parent.id,
        label="Demo parent voice",
        voice_sample_url="https://example.com/demo-parent-voice.mp3",
        status=STATUS_READY,
    )
    db.session.add(profile)
    db.session.flush()
    return profile, True


def ensure_reading_session(child, book, voice_profile):
    session = ReadingSession.query.filter_by(child_id=child.id, book_id=book.id).first()
    if session:
        return session, False
    session = ReadingSession(
        child_id=child.id,
        book_id=book.id,
        voice_profile_id=voice_profile.id if voice_profile else None,
        started_at=datetime.now(timezone.utc) - timedelta(days=1),
        completed_at=datetime.now(timezone.utc),
        accuracy_score=91.5,
        progress_log=[
            {"sentence_index": 0, "accuracy": 96, "points_awarded": 10},
            {"sentence_index": 1, "accuracy": 87, "points_awarded": 10},
        ],
    )
    db.session.add(session)
    db.session.flush()
    return session, True


def ensure_feedback(session):
    if Feedback.query.filter_by(session_id=session.id).first():
        return 0
    db.session.add_all([
        Feedback(session_id=session.id, feedback_type="praise", feedback_text="Amazing reading! You said the sentence very clearly."),
        Feedback(session_id=session.id, feedback_type="tip", feedback_text="Great effort. Take your time and listen for every word."),
    ])
    return 2


def ensure_game_results(child, books):
    added = 0
    games = MiniGame.query.filter(MiniGame.book_id.in_([book.id for book in books])).order_by(MiniGame.id).all()
    for index, game in enumerate(games[:3]):
        if not GameResult.query.filter_by(child_id=child.id, game_id=game.id).first():
            db.session.add(GameResult(child_id=child.id, game_id=game.id, score=30 - (index * 5)))
            added += 1
    return added


def week_start(today):
    return today - timedelta(days=today.weekday())


def ensure_leaderboard_entry(child, points, streak):
    current_week = week_start(date.today())
    entry = LeaderboardEntry.query.filter_by(child_id=child.id, week_start=current_week).first()
    if entry:
        return False
    db.session.add(LeaderboardEntry(child_id=child.id, week_start=current_week, points=points, streak_count=streak))
    return True


def main():
    app = create_app()
    with app.app_context():
        db.create_all()

        password = get_setting("SEED_PASSWORD", "ChangeMe123!")
        maya_pin = get_setting("SEED_MAYA_PIN", "123456")
        liam_pin = get_setting("SEED_LIAM_PIN", "654321")
        if any(not value.isdigit() or len(value) != 6 for value in (maya_pin, liam_pin)):
            raise ValueError("SEED_MAYA_PIN and SEED_LIAM_PIN must each be exactly 6 digits.")

        _, admin_created = ensure_account("Site Admin", get_setting("SEED_ADMIN_EMAIL", "admin@teachalike.app"), password, ROLE_ADMIN)
        parent, parent_created = ensure_account("Demo Parent", get_setting("SEED_PARENT_EMAIL", "parent@teachalike.app"), password, ROLE_PARENT)
        _, teacher_created = ensure_account("Demo Teacher", get_setting("SEED_TEACHER_EMAIL", "teacher@teachalike.app"), password, ROLE_TEACHER)

        maya, maya_created = ensure_child(parent, "Maya", 7, "female", "beginner", maya_pin)
        liam, liam_created = ensure_child(parent, "Liam", 9, "male", "beginner", liam_pin)
        voice_profile, voice_created = ensure_voice_profile(parent)

        books = []
        books_created = 0
        for book_data in BOOKS:
            book, created = ensure_book(book_data)
            books.append(book)
            books_created += int(created)

        db.session.commit()

        games_added = 0
        for book in books:
            games_added += len(create_default_mini_games(book))
        db.session.commit()

        session, session_created = ensure_reading_session(maya, books[0], voice_profile)
        feedback_added = ensure_feedback(session)
        results_added = ensure_game_results(maya, books)
        results_added += ensure_game_results(liam, books)
        leaderboard_added = ensure_leaderboard_entry(maya, 120, 4)
        leaderboard_added |= ensure_leaderboard_entry(liam, 85, 2)
        db.session.commit()

        print("Seed complete")
        print(f"Accounts: admin={'created' if admin_created else 'present'}, parent={'created' if parent_created else 'present'}, teacher={'created' if teacher_created else 'present'}")
        print(f"Children: Maya={'created' if maya_created else 'present'}, Liam={'created' if liam_created else 'present'}")
        print(f"Books added: {books_created}; mini-games added: {games_added}")
        print(f"Voice profiles added: {int(voice_created)}; reading sessions added: {int(session_created)}; feedback added: {feedback_added}; game results added: {results_added}; leaderboard entries added: {int(leaderboard_added)}")
        print("Demo credentials use SEED_PASSWORD (default: ChangeMe123!). Child PINs use SEED_MAYA_PIN and SEED_LIAM_PIN (defaults: 123456 and 654321). Change them outside local development.")


if __name__ == "__main__":
    main()
