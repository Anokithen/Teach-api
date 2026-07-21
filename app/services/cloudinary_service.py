"""Server-side Cloudinary storage for private voice recordings."""
from uuid import uuid4

import cloudinary
import cloudinary.uploader
import cloudinary.utils


# Browsers commonly record as WebM, OGG, or M4A rather than MP3/WAV.
# Cloudinary stores all of these as authenticated video/audio resources.
ALLOWED_EXTENSIONS = {"mp3", "wav", "webm", "ogg", "m4a", "mp4"}
BOOK_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
BOOK_VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "m4v"}


def configure_cloudinary(config):
    values = {
        "cloud_name": config.get("CLOUDINARY_CLOUD_NAME"),
        "api_key": config.get("CLOUDINARY_API_KEY"),
        "api_secret": config.get("CLOUDINARY_API_SECRET"),
    }
    if not all(values.values()):
        raise RuntimeError("Cloudinary is not configured. Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET on the API server.")
    cloudinary.config(**values, secure=True)


def upload_voice_sample(file, owner_id, config):
    configure_cloudinary(config)
    extension = file.filename.rsplit(".", 1)[-1].lower()
    public_id = f"voice_profiles/{owner_id}/{uuid4().hex}"
    result = cloudinary.uploader.upload(
        file,
        resource_type="video",  # Cloudinary handles audio files as video resources.
        type="authenticated",
        public_id=public_id,
        format=extension,
        overwrite=False,
    )
    return result["secure_url"], result["public_id"]


def upload_book_media(file, media_type, config):
    """Store optional public book artwork or video without exposing credentials."""
    configure_cloudinary(config)
    extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    allowed = BOOK_IMAGE_EXTENSIONS if media_type == "image" else BOOK_VIDEO_EXTENSIONS
    if extension not in allowed:
        label = "JPG, JPEG, PNG, or WebP" if media_type == "image" else "MP4, WebM, MOV, or M4V"
        raise ValueError(f"Unsupported {media_type} file. Use {label}.")
    resource_type = "image" if media_type == "image" else "video"
    result = cloudinary.uploader.upload(
        file,
        resource_type=resource_type,
        folder=f"book_media/{media_type}s",
        public_id=uuid4().hex,
        overwrite=False,
    )
    return result["secure_url"]


def delete_voice_sample(public_id, config):
    if not public_id:
        return
    configure_cloudinary(config)
    cloudinary.uploader.destroy(public_id, resource_type="video", type="authenticated", invalidate=True)


def signed_voice_delivery_url(public_id, fallback_url, config):
    """Create a short signed authenticated-delivery URL after app authorization."""
    if not public_id:
        return fallback_url
    configure_cloudinary(config)
    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        resource_type="video",
        type="authenticated",
        sign_url=True,
        secure=True,
    )
    return url
