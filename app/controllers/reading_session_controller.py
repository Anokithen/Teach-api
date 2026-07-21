import re
from difflib import SequenceMatcher

from flask import jsonify, request
from flask_jwt_extended import current_user

from app.extensions import db
from app.utils import utc_now
from app.models.child_model import Child
from app.models.book_model import Book
from app.models.voice_profile_model import VoiceProfile
from app.models.reading_session_model import ReadingSession
from app.middleware import child_belongs_to_current_parent, voice_profile_belongs_to_current_parent
from app.controllers.game_result_controller import _award_leaderboard_points
from app.services.speech_recognition import SpeechRecognitionError, transcribe_audio
from app.services.score_feedback import add_score_feedback


PRONUNCIATION_POINTS = 10
PRONUNCIATION_PASS_SCORE = 0.8


def _book_sentences(text):
    """Return readable sentence-sized snippets from a book's text."""
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n+", text or "") if sentence.strip()]


def _normalise_spoken_text(text):
    return " ".join(re.findall(r"[\w']+", text.lower()))


def _session_belongs_to_current_parent(session):
    if session is None:
        return False
    child = db.session.get(Child, session.child_id)
    return child_belongs_to_current_parent(child)


def create_reading_session():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required."}), 400

    errors = []
    child_id = data.get("child_id")
    book_id = data.get("book_id")
    voice_profile_id = data.get("voice_profile_id")

    child = db.session.get(Child, child_id) if child_id else None
    if not child_id or not child_belongs_to_current_parent(child):
        errors.append("A valid child_id belonging to this account is required.")

    book = db.session.get(Book, book_id) if book_id else None
    if not book_id or not book:
        errors.append("A valid book_id is required.")

    voice_profile = None
    if voice_profile_id is not None:
        voice_profile = db.session.get(VoiceProfile, voice_profile_id)
        if not voice_profile_belongs_to_current_parent(voice_profile):
            errors.append("voice_profile_id must reference a voice profile owned by this account.")
        elif voice_profile.status != "ready":
            errors.append("The selected voice profile is not ready yet.")

    if errors:
        return jsonify({"errors": errors}), 400

    try:
        session = ReadingSession(
            child_id=child_id,
            book_id=book_id,
            voice_profile_id=voice_profile_id,
            started_at=utc_now(),
        )
        db.session.add(session)
        db.session.commit()
        return jsonify(
            {"message": "Reading session started.", "reading_session": session.to_dict()}
        ), 201
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def update_reading_session(session_id):
    session = db.session.get(ReadingSession, session_id)
    if not _session_belongs_to_current_parent(session):
        return jsonify({"error": "Reading session not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body is required."}), 400

    try:
        if "progress_entry" in data:
            entry = data.get("progress_entry")
            log = list(session.progress_log or [])
            log.append(entry)
            session.progress_log = log

        if "accuracy_score" in data and data.get("accuracy_score") is not None:
            session.accuracy_score = float(data.get("accuracy_score"))

        if data.get("mark_complete"):
            session.completed_at = utc_now()

        db.session.commit()
        return jsonify(
            {"message": "Reading session updated.", "reading_session": session.to_dict()}
        ), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def get_reading_session(session_id):
    session = db.session.get(ReadingSession, session_id)
    if not _session_belongs_to_current_parent(session):
        return jsonify({"error": "Reading session not found."}), 404
    return jsonify({"reading_session": session.to_dict()}), 200


def transcribe_pronunciation(session_id):
    """Transcribe a microphone recording with the server's offline Python recogniser."""
    session = db.session.get(ReadingSession, session_id)
    if not _session_belongs_to_current_parent(session):
        return jsonify({"error": "Reading session not found."}), 404
    if session.completed_at:
        return jsonify({"error": "This reading session is already complete."}), 400
    recording = request.files.get("audio")
    if recording is None or not recording.filename:
        return jsonify({"error": "A microphone recording is required."}), 400
    sentence_index = request.form.get("sentence_index", type=int)
    sentences = _book_sentences(session.book.text_content if session.book else None)
    if sentence_index is None or sentence_index < 0 or sentence_index >= len(sentences):
        return jsonify({"error": "Choose a valid sentence before recording."}), 400
    try:
        transcript = transcribe_audio(recording, expected_text=sentences[sentence_index])
        if not transcript:
            return jsonify({"error": "No words were heard. Try again a little closer to the microphone."}), 422
        return jsonify({"transcript": transcript}), 200
    except SpeechRecognitionError as err:
        return jsonify({"error": str(err)}), 503


def check_pronunciation(session_id):
    """Compare browser speech-to-text with a book sentence and award 10 points once."""
    session = db.session.get(ReadingSession, session_id)
    if not _session_belongs_to_current_parent(session):
        return jsonify({"error": "Reading session not found."}), 404
    if session.completed_at:
        return jsonify({"error": "This reading session is already complete."}), 400

    data = request.get_json(silent=True) or {}
    sentence_index = data.get("sentence_index")
    transcript = data.get("transcript")
    if not isinstance(sentence_index, int) or sentence_index < 0:
        return jsonify({"error": "A valid sentence_index is required."}), 400
    if not isinstance(transcript, str) or not transcript.strip():
        return jsonify({"error": "A spoken transcript is required."}), 400
    if len(transcript) > 1000:
        return jsonify({"error": "The spoken transcript is too long."}), 400

    sentences = _book_sentences(session.book.text_content if session.book else None)
    if sentence_index >= len(sentences):
        return jsonify({"error": "That sentence does not exist in this book."}), 400

    expected = _normalise_spoken_text(sentences[sentence_index])
    spoken = _normalise_spoken_text(transcript)
    if not expected or not spoken:
        return jsonify({"error": "We could not compare that reading. Please try again."}), 400

    score = SequenceMatcher(None, expected, spoken).ratio()
    correct = score >= PRONUNCIATION_PASS_SCORE
    log = list(session.progress_log or [])
    already_awarded = any(
        entry.get("type") == "pronunciation_check"
        and entry.get("sentence_index") == sentence_index
        and entry.get("awarded_points") == PRONUNCIATION_POINTS
        for entry in log
        if isinstance(entry, dict)
    )
    points_awarded = PRONUNCIATION_POINTS if correct and not already_awarded else 0

    try:
        accuracy = round(score * 100)
        log.append(
            {
                "type": "pronunciation_check",
                "sentence_index": sentence_index,
                "transcript": transcript.strip(),
                "accuracy": accuracy,
                "awarded_points": points_awarded,
            }
        )
        session.progress_log = log
        session.accuracy_score = accuracy
        if points_awarded:
            _award_leaderboard_points(session.child_id, points_awarded)
        automatic_feedback = add_score_feedback(session, accuracy, points_awarded, already_awarded)
        db.session.commit()
        message = (
            "Great reading! 10 points have been added to the leaderboard."
            if points_awarded
            else "Great reading! This sentence was already rewarded."
            if correct
            else "Keep trying — read the sentence again a little more clearly."
        )
        return jsonify(
            {
                "correct": correct,
                "accuracy": accuracy,
                "points_awarded": points_awarded,
                "already_awarded": already_awarded,
                "message": message,
                "feedback": automatic_feedback.to_dict(),
            }
        ), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def list_child_reading_sessions(child_id):
    child = db.session.get(Child, child_id)
    if not child_belongs_to_current_parent(child):
        return jsonify({"error": "Child not found."}), 404

    sessions = (
        ReadingSession.query.filter_by(child_id=child_id)
        .order_by(ReadingSession.started_at.desc())
        .all()
    )
    return jsonify({"reading_sessions": [s.to_dict() for s in sessions]}), 200
