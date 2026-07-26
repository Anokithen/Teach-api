"""Cleanup of external assets owned by an account before account deletion."""

from flask import current_app

from app.services.cloudinary_service import (
    delete_authenticated_audio,
    delete_profile_image,
)
from app.services.elevenlabs_service import delete_voice


def delete_account_assets(account):
    """Delete all Cloudinary and ElevenLabs assets tied to an account.

    Cleanup is attempted for every asset even when one provider call fails. A
    failure prevents the database account deletion so an administrator can
    retry and finish cleanup instead of leaving orphaned assets behind.
    """
    failures = []
    seen_cloudinary_ids = set()
    seen_elevenlabs_ids = set()

    def delete_cloudinary(public_id, label, deleter):
        if not public_id or public_id in seen_cloudinary_ids:
            return
        seen_cloudinary_ids.add(public_id)
        try:
            deleter(public_id, current_app.config)
        except Exception as exc:
            current_app.logger.exception("Could not delete %s", label)
            failures.append(exc)

    def delete_elevenlabs(voice_id, label):
        if not voice_id or voice_id in seen_elevenlabs_ids:
            return
        seen_elevenlabs_ids.add(voice_id)
        try:
            delete_voice(voice_id, current_app.config)
        except Exception as exc:
            current_app.logger.exception("Could not delete %s", label)
            failures.append(exc)

    delete_cloudinary(
        account.profile_image_public_id,
        "the account profile image",
        delete_profile_image,
    )
    for child in list(account.children or []):
        delete_cloudinary(
            child.profile_image_public_id,
            f"child {child.id} profile image",
            delete_profile_image,
        )

    for profile in list(account.voice_profiles or []):
        delete_cloudinary(
            profile.cloudinary_public_id,
            f"voice profile {profile.id} recording",
            delete_authenticated_audio,
        )
        delete_elevenlabs(profile.elevenlabs_voice_id, f"voice profile {profile.id} clone")
        for narration in list(profile.narrations or []):
            delete_cloudinary(
                narration.cloudinary_public_id,
                f"book narration {narration.id} audio",
                delete_authenticated_audio,
            )

    if failures:
        raise RuntimeError(
            "Some external account assets could not be deleted. The account was not removed; please retry."
        )
