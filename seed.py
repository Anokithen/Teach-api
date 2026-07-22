"""Populate demo Books and MiniGames.

Books/mini-games have no create/update endpoints in the public API (they're
managed as catalog content), so seed them directly:

    python seed.py
"""
import os

from app import create_app
from app.extensions import db
from app.models.book_model import Book
from app.models.parent_model import Parent, ROLE_ADMIN
from app.services.book_games import create_default_mini_games

app = create_app()

with app.app_context():
    db.create_all()

    if Parent.query.filter_by(role=ROLE_ADMIN).count() == 0:
        admin_email = os.getenv("SEED_ADMIN_EMAIL", "admin@teachalike.app")
        admin_password = os.getenv("SEED_ADMIN_PASSWORD", "ChangeMe123!")
        admin = Parent(name="Site Admin", email=admin_email, role=ROLE_ADMIN)
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()
        print(f"Seeded default admin account: {admin_email} / {admin_password} (change this password immediately).")
    else:
        print("Admin account already exists, skipping.")

    if Book.query.count() == 0:
        b1 = Book(
            title="The Curious Fox",
            age_group="4-6",
            reading_level="beginner",
            content_url="https://cdn.teachalike.app/books/curious-fox.json",
            text_content="Once upon a time, a curious fox explored the forest...",
        )
        b2 = Book(
            title="Adventures in Space",
            age_group="7-9",
            reading_level="intermediate",
            content_url="https://cdn.teachalike.app/books/adventures-in-space.json",
            text_content="Captain Mia strapped into her rocket ship and looked at the stars...",
        )
        db.session.add_all([b1, b2])
        db.session.commit()

        print("Seeded books.")
    else:
        print("Books already exist, skipping seed.")

    games_added = 0
    for book in Book.query.all():
        games_added += len(create_default_mini_games(book))
    db.session.commit()
    if games_added:
        print(f"Added {games_added} missing standard mini-games.")
