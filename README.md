# TeachAlike API

## NVIDIA pronunciation recognition

Reading-session microphone recordings are converted to mono 16 kHz WAV with ffmpeg and transcribed server-side through NVIDIA's ASR endpoint. The returned transcript is then scored by the NVIDIA chat model against the target sentence. The NVIDIA key is never sent to the browser, and matching readings receive the existing leaderboard points. A local similarity fallback keeps scoring available during a temporary NVIDIA outage.

1. Install API dependencies: `pip install -r requirements.txt`.
2. Install `ffmpeg` and ensure `ffmpeg` is available on the server PATH.
3. Set these server-only variables:

   ```env
   NVIDIA_ASR_API_KEY=your-rotated-server-side-key
   NVIDIA_ASR_API_URL=https://1598d209-5e27-4d3c-8079-4751568b1081.invocation.api.nvcf.nvidia.com/v1/audio/transcriptions
   NVIDIA_ASR_LANGUAGE=en-US
   NVIDIA_ASR_REQUEST_TIMEOUT=45
   NVIDIA_PRONUNCIATION_API_KEY=your-rotated-server-side-key
   NVIDIA_PRONUNCIATION_REQUEST_TIMEOUT=20
   ```

4. Start the Flask API with `python run.py`.

## Railway deployment

The included `railway.toml`, `Dockerfile`, and `Procfile` are ready for a
Railway web service. Deploy this directory as the service root. The container
listens on Railway's `PORT` and installs `ffmpeg` for audio conversion.

Set `JWT_SECRET_KEY`, `FRONTEND_ORIGINS`, and the Cloudinary variables in
Railway. A Railway MySQL service can be connected by referencing its native
`MYSQL_URL` (or its `MYSQL*` variables); the API also accepts the existing
`DB_*` variables. Apply the SQL files in `migrations/` before serving traffic.
This includes `20260728_add_revoked_tokens.sql`, which is required for
persistent access/refresh-token revocation during logout, and
`20260728_add_exit_password.sql`, which adds the optional hashed in-app exit
password.

For a Vercel frontend, set `FRONTEND_ORIGINS` on the Railway API service to the
exact deployed frontend origin, for example
`https://your-project.vercel.app`. Multiple origins can be comma-separated;
custom domains and Vercel preview URLs may be listed separately. The API
accepts a trailing slash, but the value should not include an `/api` path.
Configure the frontend's API base URL to the public Railway API URL, including
the `/api` prefix only if the frontend's requests are built from that base.
The API process can be checked at `https://<railway-domain>/health`.

Important: MySQL service variables are not automatically visible to another
Railway service. On the API service, add `MYSQL_URL` with a Railway service
reference such as `${{MySQL.MYSQL_URL}}`, or add references for each `MYSQL*`
variable. The reference must resolve to a value; literal `${{...}}` text means
the variable was configured on the wrong service.

The service uses Gunicorn's one-worker default because each worker can load a
separate copy of the optional TTS model. Increase workers only by changing the
start command when the Railway service has enough memory.

To load the optional demo data after deployment:

```bash
python seed.py
```

Run this command from a Railway service shell after the MySQL service is
available, or run it locally with the Railway database variables loaded.

`seed.py` inserts sample data and is not required for the API to start. For a
production database, review the SQL files in `migrations/` before applying
schema changes.

The browser records audio, uploads it to the authenticated `/api/reading-sessions/:id/pronunciation-transcript` endpoint, and then sends the returned transcript to the existing pronunciation scoring endpoint. Recordings are deleted from the server immediately after transcription.

## Gemini story word quizzes

Every book gets a quiz grounded in its title, reading level, and full story text. Gemini creates child-friendly multiple-choice questions that mix word meaning, context, and story understanding. The API validates that each answer and target word are grounded in the book before saving the quiz JSON in the existing `mini_games.content` field.

Configure Gemini on the API server:

```env
GEMINI_API_KEY=your-server-side-key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_REQUEST_TIMEOUT=45
```

Legacy static quizzes are upgraded the next time the book's mini-games are opened. If Gemini is unavailable, a grounded deterministic fallback keeps the book playable and will be replaced by Gemini once the key is configured.

## NVIDIA book generation

Admins can generate a book draft with `POST /api/admin/book-draft`. The API sends the request server-side to NVIDIA NIM's OpenAI-compatible chat completions endpoint; the NVIDIA key is never sent to the browser.

Configure the API server:

```env
BOOK_GENERATION_PROVIDER=nvidia
NVIDIA_API_KEY=your-server-side-nvidia-key
NVIDIA_MODEL=openai/gpt-oss-120b
NVIDIA_API_URL=https://integrate.api.nvidia.com/v1/chat/completions
NVIDIA_REQUEST_TIMEOUT=60
```

Example request (with an admin JWT):

```json
POST /api/admin/book-draft
{
  "age_group": "6-8",
  "reading_level": "beginner",
  "idea": "A small cloud learns how to help a thirsty garden."
}
```

Set `BOOK_GENERATION_PROVIDER=gemini` to keep using the existing Gemini draft generator instead.

## Voice-cloned book narration (ElevenLabs)

Book preview narrations are generated separately from reading sessions. A parent selects one of their ready voice profiles and requests a cached narration for that `(book, voice profile)` pair. Generated audio and source recordings are private authenticated Cloudinary resources; the API only redirects to a signed URL after an ownership check.

Cloudinary storage is organized as follows:

```text
teachalike/
├── users_voiceprofiles/<parent-or-teacher-name>/<random-upload-id>
└── generated_booksaudio/<parent-or-teacher-name>/<book-name>/voice_profile_<id>
```

Voice-profile uploads use a random file ID, so every recording is retained and
the owning parent or teacher can delete only their own profile through the API.
Book narration files use a stable path based on the owner, book, and selected
voice-profile ID. The database also has a unique `(book_id, voice_profile_id)`
constraint. Reusing the same book with the same voice profile returns the
existing narration; choosing another voice profile creates a separate audio
file in the same book folder. The API also checks Cloudinary for the stable
file before generating, so an existing file can be recovered if its database
row is missing.

Set these server environment variables (the defaults are also in `.env.example`):

```env
ELEVENLABS_API_KEY=your-server-side-key
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
ELEVENLABS_MAX_CHARS_PER_CHUNK=4500
ELEVENLABS_REQUEST_TIMEOUT=120
```

When a user creates a voice profile, the API sends the private recording to ElevenLabs' Instant Voice Cloning endpoint and stores only the returned voice ID alongside the private Cloudinary sample. When a user requests a book narration, the API sends the book text to ElevenLabs in sentence-aware chunks, combines the returned MP3 files with ffmpeg, and stores the result as a private authenticated Cloudinary resource. The ElevenLabs key and Cloudinary credentials never reach the browser.

This code intentionally uses a one-worker in-process thread pool per Gunicorn process because the current deployment has no queue service. Jobs are lost when a web process restarts and are not coordinated across replicas. For production/scale, move `app.controllers.book_narration_controller._generate_narration` to a durable Celery or RQ worker backed by Redis, while retaining the same `BookNarration` status polling API.

After changing API environment variables, restart the Flask process. Existing voice profiles without an ElevenLabs ID are cloned lazily the first time their owner requests a narration.
