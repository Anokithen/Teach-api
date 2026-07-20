"""Default mini-games generated for each book in the catalog."""
import re

from app.extensions import db
from app.models.mini_game_model import MiniGame


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "the", "this", "that", "to", "was", "with",
}


def _keywords(book):
    """Return a small, predictable set of child-friendly words from a book."""
    source = f"{book.title} {book.text_content or ''}"
    words = re.findall(r"[A-Za-z]{3,}", source.lower())
    selected = []
    for word in words:
        if word not in STOP_WORDS and word not in selected:
            selected.append(word)
        if len(selected) == 4:
            break
    return selected or ["story", "book", "read"]


def _quiz_questions(words):
    questions = []
    fallback_options = ["story", "reading", "friend", "adventure"]
    for index, word in enumerate(words[:3]):
        options = [word]
        for choice in words + fallback_options:
            if choice not in options:
                options.append(choice)
            if len(options) == 4:
                break
        questions.append({
            "question": f"Which word was used in this book?",
            "options": options,
            "answer": word,
        })
    return questions


def create_default_mini_games(book):
    """Add each standard game once, without duplicating games already present."""
    words = _keywords(book)
    existing_types = {
        game.game_type for game in MiniGame.query.filter_by(book_id=book.id).all()
    }
    games = []
    defaults = [
        ("word_puzzle", "easy", {"time_limit_seconds": 60}, {"words": words}),
        ("spelling", "medium", {"lives": 3}, {"words": words}),
        (
            "quiz",
            "easy",
            {"questions_to_pass": min(2, len(_quiz_questions(words)))},
            {"questions": _quiz_questions(words)},
        ),
    ]
    for game_type, difficulty, rules, content in defaults:
        if game_type not in existing_types:
            game = MiniGame(
                book_id=book.id,
                game_type=game_type,
                difficulty=difficulty,
                rules=rules,
                content=content,
            )
            db.session.add(game)
            games.append(game)
    return games
