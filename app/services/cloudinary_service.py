"""Server-side Cloudinary storage for private voice recordings."""
import re
from uuid import uuid4

# Browsers commonly record as WebM, OGG, or M4A rather than MP3/WAV.
# Cloudinary stores all of these as authenticated video/audio resources.
ALLOWED_EXTENSIONS = {"mp3", "wav", "webm", "ogg", "m4a", "mp4"}
BOOK_MEDIA_EXTENSIONS = {
    "image": {"jpg", "jpeg", "png", "webp"},
    "video": {"mp4", "webm", "mov"},
}


def _cloudinary_segment(value, fallback):
    """Turn a user-facing name into a safe, readable Cloudinary path segment."""
    segment = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "")).strip("_").lower()
    return segment or fallback


def _owner_folder(owner_id, owner_name=None):
    """Use the account name as the folder while retaining a safe fallback."""
    return _cloudinary_segment(owner_name, f"account_{owner_id}")


def book_narration_public_id(owner_id, owner_name, book_id, book_title, voice_profile_id):
    """Return the stable path for one book rendered with one voice profile.

    The voice-profile ID is part of the filename rather than another folder so
    every profile still gets its own audio while all versions remain grouped
    below the owner's book folder.
    """
    owner_folder = _owner_folder(owner_id, owner_name)
    book_folder = _cloudinary_segment(book_title, f"book_{book_id}")
    return (
        f"teachalike/generated_booksaudio/{owner_folder}/{book_folder}/"
        f"voice_profile_{voice_profile_id}"
    )


def _cloudinary_modules():
    """Load Cloudinary only when a Cloudinary-backed operation is used.

    Cloudinary is an optional integration for the API's core routes. Keeping
    the import here allows the application to boot (and serve books,
    accounts, and reading sessions) when that integration is not installed or
    configured.
    """
    try:
        import cloudinary
        import cloudinary.api
        import cloudinary.exceptions
        import cloudinary.uploader
        import cloudinary.utils
    except ImportError as exc:
        raise RuntimeError(
            "Cloudinary support is not installed. Install the cloudinary package."
        ) from exc
    return cloudinary


def configure_cloudinary(config):
    cloudinary = _cloudinary_modules()
    values = {
        "cloud_name": config.get("CLOUDINARY_CLOUD_NAME"),
        "api_key": config.get("CLOUDINARY_API_KEY"),
        "api_secret": config.get("CLOUDINARY_API_SECRET"),
    }
    if not all(values.values()):
        raise RuntimeError("Cloudinary is not configured. Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET on the API server.")
    cloudinary.config(**values, secure=True)


def upload_voice_sample(file, owner_id, config, owner_name=None):
    cloudinary = _cloudinary_modules()
    configure_cloudinary(config)
    extension = file.filename.rsplit(".", 1)[-1].lower()
    public_id = (
        f"teachalike/users_voiceprofiles/{_owner_folder(owner_id, owner_name)}/"
        f"{uuid4().hex}"
    )
    result = cloudinary.uploader.upload(
        file,
        resource_type="video",  # Cloudinary handles audio files as video resources.
        type="authenticated",
        public_id=public_id,
        format=extension,
        overwrite=False,
    )
    return result["secure_url"], result["public_id"]


def upload_book_narration(
    file,
    owner_id,
    owner_name,
    book_id,
    book_title,
    voice_profile_id,
    config,
):
    """Store generated narration as private authenticated Cloudinary audio."""
    cloudinary = _cloudinary_modules()
    configure_cloudinary(config)
    public_id = book_narration_public_id(
        owner_id,
        owner_name,
        book_id,
        book_title,
        voice_profile_id,
    )
    result = cloudinary.uploader.upload(
        file,
        resource_type="video",
        type="authenticated",
        public_id=public_id,
        format="mp3",
        overwrite=False,
    )
    return result["secure_url"], result["public_id"]


def find_book_narration(public_id, config):
    """Return an existing authenticated narration asset, if one exists.

    A missing/invalid Cloudinary setup is treated as "not found" here so the
    normal background job can report the configuration error through its
    existing status flow.
    """
    if not public_id:
        return None
    try:
        cloudinary = _cloudinary_modules()
    except RuntimeError:
        return None
    try:
        configure_cloudinary(config)
        return cloudinary.api.resource(
            public_id,
            resource_type="video",
            type="authenticated",
        )
    except cloudinary.exceptions.NotFound:
        return None
    except cloudinary.exceptions.GeneralError:
        # A transient Cloudinary API failure should not prevent the normal
        # narration job from being queued; the worker will report a clear
        # failure if storage is still unavailable.
        return None
    except RuntimeError:
        return None


def signed_narration_delivery_url(public_id, fallback_url, config):
    """Narrations use the same authenticated delivery policy as voice samples."""
    return signed_voice_delivery_url(public_id, fallback_url, config)


def delete_voice_sample(public_id, config):
    if not public_id:
        return
    cloudinary = _cloudinary_modules()
    configure_cloudinary(config)
    cloudinary.uploader.destroy(public_id, resource_type="video", type="authenticated", invalidate=True)


def signed_voice_delivery_url(public_id, fallback_url, config):
    """Create a short signed authenticated-delivery URL after app authorization."""
    if not public_id:
        return fallback_url
    cloudinary = _cloudinary_modules()
    configure_cloudinary(config)
    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        resource_type="video",
        type="authenticated",
        sign_url=True,
        secure=True,
    )
    return url


def upload_book_media(file, media_type, owner_id, config):
    """Store public catalog media separately from private voice recordings."""
    extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if extension not in BOOK_MEDIA_EXTENSIONS[media_type]:
        allowed = ", ".join(sorted(BOOK_MEDIA_EXTENSIONS[media_type]))
        raise ValueError(f"Unsupported {media_type} format. Allowed formats: {allowed}.")
    cloudinary = _cloudinary_modules()
    configure_cloudinary(config)
    result = cloudinary.uploader.upload(
        file,
        resource_type=media_type,
        folder=f"book_media/{owner_id}",
        public_id=uuid4().hex,
        overwrite=False,
    )
    return result["secure_url"]
