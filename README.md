# Teachalike-api
# TeachAlike API

## Private voice recordings

Voice-profile uploads accept MP3 and WAV files smaller than 25 MB. Install the
updated dependencies, copy `.env.example` to `.env`, and set the Cloudinary
cloud name, API key, and API secret on the API server. Do not place these
values in the Next.js application.

For an existing database, run
`migrations/001_add_voice_profile_cloudinary_public_id.sql` once before
deploying. New databases receive the column through `db.create_all()`.
