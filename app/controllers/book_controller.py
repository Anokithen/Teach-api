from flask import jsonify, request

from app.extensions import db
from app.models.book_model import Book
from app.services.book_games import create_default_mini_games


def list_books():
    # Keep catalog entries created before mini-games were introduced complete.
    # New books are populated at creation time; this only changes legacy rows.
    games_added = 0
    for book in Book.query.all():
        games_added += len(create_default_mini_games(book))
    if games_added:
        db.session.commit()

    query = Book.query

    age_group = request.args.get("age_group")
    if age_group:
        query = query.filter_by(age_group=age_group)

    reading_level = request.args.get("reading_level")
    if reading_level:
        query = query.filter_by(reading_level=reading_level)

    books = query.order_by(Book.id.asc()).all()
    return jsonify({"books": [b.to_dict() for b in books]}), 200


def get_book(book_id):
    book = db.session.get(Book, book_id)
    if not book:
        return jsonify({"error": "Book not found."}), 404
    if create_default_mini_games(book):
        db.session.commit()
    return jsonify({"book": book.to_dict(include_content=True)}), 200


def download_book(book_id):
    book = db.session.get(Book, book_id)
    if not book:
        return jsonify({"error": "Book not found."}), 404

    package = {
        "book": book.to_dict(include_content=True),
        "assets": {
            "content_url": book.content_url,
        },
    }
    return jsonify(package), 200
