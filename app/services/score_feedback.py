"""Create child-friendly feedback directly from pronunciation scores."""

from app.models.feedback_model import Feedback


def feedback_for_score(accuracy, points_awarded, already_awarded):
    """Return an encouraging feedback type and message for one reading attempt."""
    if accuracy >= 95:
        message = "Amazing reading! You said the sentence very clearly."
        if points_awarded:
            message += " You earned 10 points!"
        return "praise", message
    if accuracy >= 80:
        message = "Great job! Your reading was clear and careful."
        if points_awarded:
            message += " Your 10 points are on the leaderboard."
        elif already_awarded:
            message += " You already earned the points for this sentence."
        return "praise", message
    if accuracy >= 60:
        return "tip", "Nice try! Read the sentence a little slower and listen for each word."
    return "correction", "Let’s practise this one together. Take your time and say each word clearly."


def add_score_feedback(session, accuracy, points_awarded, already_awarded):
    feedback_type, feedback_text = feedback_for_score(accuracy, points_awarded, already_awarded)
    feedback = Feedback(
        session_id=session.id,
        feedback_type=feedback_type,
        feedback_text=feedback_text,
    )
    from app.extensions import db
    db.session.add(feedback)
    return feedback
