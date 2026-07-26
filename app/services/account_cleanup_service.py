"""Background cleanup of external assets owned by deleted accounts."""

from concurrent.futures import ThreadPoolExecutor

from flask import current_app

from app.services.cloudinary_service import (
    delete_authenticated_audio,
    delete_profile_image,
)
from app.services.elevenlabs_service import delete_voice


ACCOUNT_CLEANUP_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="account-asset-cleanup",
)


def collect_account_asset_refs(account):
    """Snapshot external asset IDs before SQLAlchemy cascades remove records."""
    profile_images = [account.profile_image_public_id]
    audio = []
    elevenlabs = []
    for child in list(account.children or []):
        profile_images.append(child.profile_image_public_id)
    for profile in list(account.voice_profiles or []):
        audio.append(profile.cloudinary_public_id)
        elevenlabs.append(profile.elevenlabs_voice_id)
        audio.extend(narration.cloudinary_public_id for narration in list(profile.narrations or []))
    return {
        "profile_images": [item for item in profile_images if item],
        "audio": [item for item in audio if item],
        "elevenlabs": [item for item in elevenlabs if item],
    }


def delete_account_asset_refs(asset_refs, config, logger):
    """Delete a previously captured set of Cloudinary and ElevenLabs assets."""
    failures = []
    seen_cloudinary_ids = set()
    seen_elevenlabs_ids = set()

    def delete_cloudinary(public_id, label, deleter):
        if not public_id or public_id in seen_cloudinary_ids:
            return
        seen_cloudinary_ids.add(public_id)
        try:
            deleter(public_id, config)
        except Exception as exc:
            logger.exception("Could not delete %s", label)
            failures.append(exc)

    def delete_elevenlabs(voice_id, label):
        if not voice_id or voice_id in seen_elevenlabs_ids:
            return
        seen_elevenlabs_ids.add(voice_id)
        try:
            delete_voice(voice_id, config)
        except Exception as exc:
            logger.exception("Could not delete %s", label)
            failures.append(exc)

    for public_id in asset_refs.get("profile_images", []):
        delete_cloudinary(public_id, "a profile image", delete_profile_image)
    for public_id in asset_refs.get("audio", []):
        delete_cloudinary(public_id, "an audio asset", delete_authenticated_audio)
    for voice_id in asset_refs.get("elevenlabs", []):
        delete_elevenlabs(voice_id, "an ElevenLabs voice clone")

    if failures:
        raise RuntimeError(
            "Some external account assets could not be deleted. Cleanup will need to be retried."
        )


def _cleanup_in_background(app, asset_refs):
    with app.app_context():
        try:
            delete_account_asset_refs(asset_refs, current_app.config, current_app.logger)
        except RuntimeError:
            current_app.logger.exception("Background account asset cleanup did not finish")


def schedule_account_asset_cleanup(asset_refs):
    """Queue external cleanup without blocking the account deletion request."""
    if not any(asset_refs.values()):
        return
    app = current_app._get_current_object()
    try:
        ACCOUNT_CLEANUP_EXECUTOR.submit(_cleanup_in_background, app, asset_refs)
    except Exception:
        # The database deletion has already committed by the time this runs.
        # Never turn that successful deletion into a misleading 500 response.
        current_app.logger.exception("Could not queue background account asset cleanup")
