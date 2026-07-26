from flask import current_app, jsonify, request, redirect
from flask_jwt_extended import current_user

from app.extensions import db
from app.controllers import asset_controller
from app.models.voice_profile_model import VoiceProfile, STATUS_READY
from app.models.asset_model import (
    Asset,
    STATUS_COMPLETED,
    STATUS_DELETED,
    VOICE_PROFILE,
)
from app.utils import utc_now
from app.middleware import can_access_voice_profile, owns_voice_profile
from app.services.cloudinary_path_service import get_voice_profile_folder
from app.services.cloudinary_service import (
    delete_asset,
    delete_voice_sample,
    signed_voice_delivery_url,
    upload_asset,
)
from app.services.elevenlabs_service import ElevenLabsError, clone_voice, delete_voice


def create_voice_profile():
    """Accept a private audio upload and store it in Cloudinary."""
    sample, error = asset_controller._validated_file(VOICE_PROFILE, "audio")
    if error:
        return error

    data = request.form
    label = str(data.get("label") or "").strip()
    if len(label) > 80:
        return jsonify({"errors": ["label must be 80 characters or fewer."]}), 400

    voice_profile = None
    elevenlabs_voice_id = None
    metadata = None
    try:
        voice_profile = VoiceProfile(
            parent_id=current_user.id,
            label=label or None,
            voice_sample_url="pending",
            status=STATUS_READY,
        )
        db.session.add(voice_profile)
        db.session.flush()
        metadata = upload_asset(
            sample,
            get_voice_profile_folder(current_user.id),
            resource_type="video",
            public_id=f"voice_profile_{voice_profile.id}",
            overwrite=False,
            delivery_type="authenticated",
        )
        # Cloudinary consumes the upload stream. Rewind it before sending the
        # same sample to ElevenLabs for Instant Voice Cloning.
        sample.stream.seek(0)
        elevenlabs_voice_id = clone_voice(
            sample.stream,
            sample.filename,
            sample.mimetype,
            current_app.config,
            profile_label=label,
            owner_name=current_user.name,
        )
        voice_profile.voice_sample_url = metadata["secure_url"]
        voice_profile.cloudinary_public_id = metadata["public_id"]
        voice_profile.elevenlabs_voice_id = elevenlabs_voice_id
        db.session.add(
            Asset(
                owner_user_id=current_user.id,
                voice_profile_id=voice_profile.id,
                asset_category=VOICE_PROFILE,
                cloudinary_asset_id=metadata["asset_id"],
                cloudinary_public_id=metadata["public_id"],
                cloudinary_secure_url=metadata["secure_url"],
                cloudinary_resource_type=metadata["resource_type"],
                cloudinary_delivery_type=metadata.get("delivery_type") or "upload",
                cloudinary_format=metadata.get("format"),
                cloudinary_asset_folder=metadata["asset_folder"],
                original_filename=metadata.get("original_filename"),
                file_size_bytes=metadata.get("bytes"),
                width=metadata.get("width"),
                height=metadata.get("height"),
                duration_seconds=metadata.get("duration"),
                status=STATUS_COMPLETED,
            )
        )
        db.session.commit()

        return jsonify(
            {
                "message": "Voice profile cloned securely and ready for book narration.",
                "voice_profile": voice_profile.to_dict(),
            }
        ), 201
    except (RuntimeError, ElevenLabsError) as exc:
        db.session.rollback()
        if metadata:
            try:
                delete_asset(
                    metadata["public_id"],
                    metadata["resource_type"],
                    metadata.get("delivery_type") or "upload",
                )
            except Exception:
                current_app.logger.exception("Could not clean up failed voice-profile upload")
        return jsonify({"error": str(exc)}), 503
    except Exception:
        db.session.rollback()
        if elevenlabs_voice_id:
            try:
                delete_voice(elevenlabs_voice_id, current_app.config)
            except Exception:
                current_app.logger.exception("Could not clean up failed ElevenLabs voice clone")
        if metadata:
            try:
                delete_asset(
                    metadata["public_id"],
                    metadata["resource_type"],
                    metadata.get("delivery_type") or "upload",
                )
            except Exception:
                current_app.logger.exception("Could not clean up failed voice-profile upload")
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
    if not owns_voice_profile(profile):
        return jsonify({"error": "Voice profile not found."}), 404
    if profile.narrations:
        return jsonify(
            {"error": "This voice profile is still referenced by generated narrations."}
        ), 422
    if profile.reading_sessions:
        return jsonify(
            {"error": "This voice profile is still referenced by reading sessions."}
        ), 422

    try:
        asset = Asset.query.filter_by(
            voice_profile_id=profile.id, asset_category=VOICE_PROFILE, deleted_at=None
        ).first()
        if asset:
            delete_asset(
                asset.cloudinary_public_id,
                asset.cloudinary_resource_type,
                asset.cloudinary_delivery_type,
            )
            asset.status = STATUS_DELETED
            asset.deleted_at = utc_now()
        else:
            delete_voice_sample(profile.cloudinary_public_id, current_app.config)
        delete_voice(profile.elevenlabs_voice_id, current_app.config)
        db.session.delete(profile)
        db.session.commit()
        return jsonify({"message": "Voice profile and recording deleted successfully."}), 200
    except Exception:
        db.session.rollback()
        return jsonify({"error": "An internal server error occurred."}), 500
