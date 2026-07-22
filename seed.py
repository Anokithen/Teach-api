"""Create a complete, repeatable TeachAlike demo dataset.

Run from the project root after configuring the database in ``.env``:

    python seed.py

The script never deletes data and can be run repeatedly. Existing records are
kept; only the missing demo records are created. Passwords can be overridden
with ``SEED_ADMIN_PASSWORD``, ``SEED_PARENT_PASSWORD``, and
``SEED_TEACHER_PASSWORD``.
"""
import os
from datetime import timedelta

from app import create_app
from app.controllers.game_result_controller import _current_week_start
from app.extensions import db
from app.models.book_model import Book
from app.models.child_model import Child
from app.models.feedback_model import Feedback
from app.models.game_result_model import GameResult
from app.models.leaderboard_model import LeaderboardEntry
from app.models.parent_model import ROLE_ADMIN, ROLE_PARENT, ROLE_TEACHER, Parent
from app.models.reading_session_model import ReadingSession
from app.models.voice_profile_model import STATUS_READY, VoiceProfile
from app.services.book_games import create_default_mini_games
from app.utils import utc_now


BOOKS = [
    {
        "title": "The Curious Fox",
        "age_group": "4-6",
        "reading_level": "beginner",
        "cover_image_url": "https://placehold.co/600x800/f97316/ffffff?text=The+Curious+Fox",
        "text_content": (
            "Fynn the fox woke up early. He saw a bright blue butterfly near the forest path. "
            "Fynn followed it gently and found a tiny garden. He smiled and walked home before sunset."
        ),
    },
    {
        "title": "Mia's Moon Picnic",
        "age_group": "4-6",
        "reading_level": "beginner",
        "cover_image_url": "https://placehold.co/600x800/7c3aed/ffffff?text=Mia%27s+Moon+Picnic",
        "text_content": (
            "Mia packed apples, bread, and a red blanket. She sat with her puppy under the moon. "
            "They counted five shiny stars. Then Mia wished everyone a good night."
        ),
    },
    {
        "title": "The Little Seed",
        "age_group": "4-6",
        "reading_level": "beginner",
        "cover_image_url": "https://placehold.co/600x800/16a34a/ffffff?text=The+Little+Seed",
        "text_content": (
            "A little seed slept in the warm soil. Rain gave the seed a drink. "
            "The sun gave it light. Soon a yellow flower waved in the breeze."
        ),
    },
    {
        "title": "Adventures in Space",
        "age_group": "7-9",
        "reading_level": "intermediate",
        "cover_image_url": "https://placehold.co/600x800/1d4ed8/ffffff?text=Adventures+in+Space",
        "text_content": (
            "Captain Mia checked every button in her small rocket ship. Beyond the window, planets glimmered like marbles. "
            "Her robot friend Atlas mapped a safe path through an asteroid field. Together they discovered a quiet purple moon."
        ),
    },
    {
        "title": "The Rainforest Rescue",
        "age_group": "7-9",
        "reading_level": "intermediate",
        "cover_image_url": "https://placehold.co/600x800/059669/ffffff?text=The+Rainforest+Rescue",
        "text_content": (
            "Nora heard a baby sloth calling from a tall rainforest tree. She and her guide built a gentle rope bridge. "
            "The sloth crossed safely to its mother. The whole forest seemed to cheer."
        ),
    },
    {
        "title": "The Inventor's Surprise",
        "age_group": "10-12",
        "reading_level": "advanced",
        "cover_image_url": "https://placehold.co/600x800/0f766e/ffffff?text=The+Inventor%27s+Surprise",
        "text_content": (
            "Arun carefully adjusted the gears inside his recycling machine. Instead of sorting paper, it began composing cheerful music. "
            "After testing each connection, Arun discovered that a loose copper wire had changed the program. He presented the musical invention at the school fair."
        ),
    },
]


def get_or_create_account(name, email, role, password):
    account = Parent.query.filter_by(email=email).first()
    if account:
        return account, False
    account = Parent(name=name, email=email, role=role)
    account.set_password(password)
    db.session.add(account)
    return account, True


def get_or_create_child(parent, teacher, name, age, gender, level, pin):
    child = Child.query.filter_by(parent_id=parent.id, name=name).first()
    if child:
        return child, False
    child = Child(
        parent_id=parent.id,
        created_by_id=teacher.id if teacher else parent.id,
        name=name,
        age=age,
        gender=gender,
        reading_level=level,
    )
    child.set_pin(pin)
    db.session.add(child)
    return child, True


def get_or_create_book(data):
    book = Book.query.filter_by(title=data["title"]).first()
    if book:
        return book, False
    book = Book(**data)
    db.session.add(book)
    return book, True


def seed_activity(child, books):
    """Add sample progress only when this demo child has no prior activity."""
    if ReadingSession.query.filter_by(child_id=child.id).first():
        return 0

    first_book, second_book = books[0], books[3]
    completed_at = utc_now() - timedelta(days=1)
    completed_session = ReadingSession(
        child_id=child.id,
        book_id=first_book.id,
        started_at=completed_at - timedelta(minutes=8),
        completed_at=completed_at,
        accuracy_score=92,
        progress_log=[
            {"type": "pronunciation_check", "sentence_index": 0, "accuracy": 96, "awarded_points": 10},
            {"type": "pronunciation_check", "sentence_index": 1, "accuracy": 92, "awarded_points": 10},
        ],
    )
    active_session = ReadingSession(
        child_id=child.id,
        book_id=second_book.id,
        started_at=utc_now() - timedelta(minutes=3),
        accuracy_score=84,
        progress_log=[{"type": "pronunciation_check", "sentence_index": 0, "accuracy": 84, "awarded_points": 0}],
    )
    db.session.add_all([completed_session, active_session])
    db.session.flush()
    db.session.add_all([
        Feedback(session_id=completed_session.id, feedback_type="praise", feedback_text="Wonderful reading! You used a clear, confident voice."),
        Feedback(session_id=completed_session.id, feedback_type="tip", feedback_text="Try pausing briefly at each full stop before you continue."),
    ])

    games = {game.book_id: game for book in books for game in book.mini_games if game.game_type == "quiz"}
    score_total = 0
    for book, score in ((first_book, 30), (second_book, 45)):
        game = games.get(book.id)
        if game:
            db.session.add(GameResult(child_id=child.id, game_id=game.id, score=score))
            score_total += score
    return score_total + 20  # Includes the two successful pronunciation checks.


def ensure_leaderboard_entry(child, points):
    week_start = _current_week_start()
    entry = LeaderboardEntry.query.filter_by(child_id=child.id, week_start=week_start).first()
    if not entry:
        db.session.add(LeaderboardEntry(child_id=child.id, week_start=week_start, points=points, streak_count=3))


def main():
    app = create_app()
    with app.app_context():
        db.create_all()

        admin, admin_created = get_or_create_account(
            "Site Admin",
            os.getenv("SEED_ADMIN_EMAIL", "admin@teachalike.app"),
            ROLE_ADMIN,
            os.getenv("SEED_ADMIN_PASSWORD", "ChangeMe123!"),
        )
        parent, parent_created = get_or_create_account(
            "Jamie Perera",
            os.getenv("SEED_PARENT_EMAIL", "jamie@teachalike.app"),
            ROLE_PARENT,
            os.getenv("SEED_PARENT_PASSWORD", "ParentDemo123!"),
        )
        teacher, teacher_created = get_or_create_account(
            "Alex Silva",
            os.getenv("SEED_TEACHER_EMAIL", "alex.teacher@teachalike.app"),
            ROLE_TEACHER,
            os.getenv("SEED_TEACHER_PASSWORD", "TeacherDemo123!"),
        )
        db.session.flush()

        children = [
            get_or_create_child(parent, None, "Ava", 6, "female", "beginner", "123456")[0],
            get_or_create_child(parent, teacher, "Noah", 8, "male", "intermediate", "234567")[0],
        ]
        db.session.flush()

        voice_profile = VoiceProfile.query.filter_by(parent_id=parent.id, label="Jamie's voice").first()
        if not voice_profile:
            db.session.add(VoiceProfile(
                parent_id=parent.id,
                label="Jamie's voice",
                voice_sample_url="https://example.com/demo-voice-sample.mp3",
                cloudinary_public_id="seed/jamie-demo-voice",
                status=STATUS_READY,
            ))

        books = [get_or_create_book(book_data)[0] for book_data in BOOKS]
        db.session.flush()
        games_added = sum(len(create_default_mini_games(book)) for book in books)
        db.session.flush()

        ava_points = seed_activity(children[0], books)
        noah_points = seed_activity(children[1], books)
        ensure_leaderboard_entry(children[0], ava_points or 65)
        ensure_leaderboard_entry(children[1], noah_points or 40)
        db.session.commit()

        created_accounts = sum((admin_created, parent_created, teacher_created))
        print("TeachAlike demo data is ready.")
        print(f"Accounts created: {created_accounts}; books available: {len(books)}; mini-games added: {games_added}.")
        print("Demo logins (only printed credentials should be changed in non-development environments):")
        print(f"  Admin:   {admin.email} / {os.getenv('SEED_ADMIN_PASSWORD', 'ChangeMe123!')}")
        print(f"  Parent:  {parent.email} / {os.getenv('SEED_PARENT_PASSWORD', 'ParentDemo123!')}")
        print(f"  Teacher: {teacher.email} / {os.getenv('SEED_TEACHER_PASSWORD', 'TeacherDemo123!')}")
        print("Child PINs: Ava 123456, Noah 234567")


if __name__ == "__main__":
    main()
