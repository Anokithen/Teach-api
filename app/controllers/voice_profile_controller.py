from flask import current_app, jsonify, request, redirect
from flask_jwt_extended import current_user

from app.extensions import db
from app.models.voice_profile_model import VoiceProfile, STATUS_PROCESSING
from app.middleware import can_access_voice_profile
from app.services.cloudinary_service import ALLOWED_EXTENSIONS, delete_voice_sample, signed_voice_delivery_url, upload_voice_sample


def create_voice_profile():
    """Accept a private MP3/WAV upload and store it in Cloudinary."""
    sample = request.files.get("audio")
    if not sample or not sample.filename:
        return jsonify({"errors": ["An MP3 or WAV audio file is required."]}), 400
    if "." not in sample.filename or sample.filename.rsplit(".", 1)[1].lower() not in ALLOWED_EXTENSIONS:
        return jsonify({"errors": ["Only .mp3 and .wav files are accepted."]}), 400

    data = request.form

    try:
        voice_sample_url, public_id = upload_voice_sample(sample, current_user.id, current_app.config)
        voice_profile = VoiceProfile(
            parent_id=current_user.id,
            label=str(data.get("label")).strip() if data.get("label") else None,
            voice_sample_url=voice_sample_url,
            cloudinary_public_id=public_id,
            status=STATUS_PROCESSING,
        )
        db.session.add(voice_profile)
        db.session.commit()

        return jsonify(
            {
                "message": "Voice recording uploaded securely.",
                "voice_profile": voice_profile.to_dict(),
            }
        ), 201
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def list_voice_profiles():
    query = VoiceProfile.query
    if not current_user.is_admin:
        query = query.filter_by(parent_id=current_user.id)
    profiles = query.order_by(VoiceProfile.id.desc()).all()
    return jsonify({"voice_profiles": [p.to_dict() for p in profiles]}), 200


def get_voice_profile_status(voice_profile_id):
    profile = db.session.get(VoiceProfile, voice_profile_id)
    if not can_access_voice_profile(profile):
        return jsonify({"error": "Voice profile not found."}), 404

    return jsonify({"id": profile.id, "status": profile.status}), 200


def get_voice_profile_audio(voice_profile_id):
    profile = db.session.get(VoiceProfile, voice_profile_id)
    if not can_access_voice_profile(profile):
        return jsonify({"error": "Voice profile not found."}), 404
    # A signed authenticated-delivery URL is generated only after our own
    # ownership check. The browser never receives Cloudinary credentials.
    try:
        return redirect(signed_voice_delivery_url(profile.cloudinary_public_id, profile.voice_sample_url, current_app.config))
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503


def update_voice_profile(voice_profile_id):
    profile = db.session.get(VoiceProfile, voice_profile_id)
    if not can_access_voice_profile(profile):
        return jsonify({"error": "Voice profile not found."}), 404
    data = request.get_json(silent=True) or {}
    if "label" not in data:
        return jsonify({"errors": ["label is required."]}), 400
    label = str(data["label"]).strip()
    if len(label) > 80:
        return jsonify({"errors": ["label must be 80 characters or fewer."]}), 400
    try:
        profile.label = label or None
        db.session.commit()
        return jsonify({"message": "Voice profile updated.", "voice_profile": profile.to_dict()}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500


def delete_voice_profile(voice_profile_id):
    profile = db.session.get(VoiceProfile, voice_profile_id)
    if not can_access_voice_profile(profile):
        return jsonify({"error": "Voice profile not found."}), 404

    try:
        delete_voice_sample(profile.cloudinary_public_id, current_app.config)
        db.session.delete(profile)
        db.session.commit()
        return jsonify({"message": "Voice profile and recording deleted successfully."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500
