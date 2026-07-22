# TeachAlike API

## Offline pronunciation recognition

Reading-session microphone recordings are transcribed locally with Python, Vosk, and ffmpeg. No OpenAI or other cloud speech API is used.

1. Install API dependencies: `pip install -r requirements.txt`.
2. Install `ffmpeg` and ensure `ffmpeg` is available on the server PATH.
3. The included development setup uses `models/vosk-model-small-en-us-0.15`. For a different model, download one from https://alphacephei.com/vosk/models and set the directory in the API `.env` file, for example:

   ```env
   VOSK_MODEL_PATH=/absolute/path/to/vosk-model-small-en-us-0.15
   ```

4. Start the Flask API with `python run.py`.

## Railway deployment

The included `railway.toml`, `Dockerfile`, and `Procfile` are ready for a
Railway web service. Deploy this directory as the service root. The container
listens on Railway's `PORT`, installs `ffmpeg`, and downloads the Vosk model
during the image build.

Set `JWT_SECRET_KEY`, `FRONTEND_ORIGINS`, and the Cloudinary variables in
Railway. A Railway MySQL service can be connected by referencing its native
`MYSQL_URL` (or its `MYSQL*` variables); the API also accepts the existing
`DB_*` variables. The `/api/health` endpoint does not require the database, so
Railway can complete its health check while the database is starting.

The service defaults to one Gunicorn worker because each worker can load a
separate copy of the optional TTS model. Set `WEB_CONCURRENCY` higher only if
the Railway service has enough memory.

Create the database tables once after the database is available:

```bash
python seed.py
```

Run this command from a Railway service shell after the MySQL service is
available, or run it locally with the Railway database variables loaded.

`seed.py` calls `db.create_all()` before inserting its sample data. For a
production database, apply the SQL files in `migrations/` after the initial
table creation.

The browser records audio, uploads it to the authenticated `/api/reading-sessions/:id/pronunciation-transcript` endpoint, and then sends the returned transcript to the existing pronunciation scoring endpoint. Recordings are deleted from the server immediately after transcription.

## Voice-cloned book narration (Coqui TTS)

Book preview narrations are generated separately from reading sessions. A parent selects one of their ready voice profiles and requests a cached narration for that `(book, voice profile)` pair. Generated audio and source recordings are private authenticated Cloudinary resources; the API only redirects to a signed URL after an ownership check.

Set these server environment variables (the defaults are also in `.env.example`):

```env
TTS_MODEL_NAME=tts_models/multilingual/multi-dataset/xtts_v2
TTS_VOICE_CLONING_METHOD=native
TTS_DEVICE=cpu
TTS_CACHE_DIR=/app/models/tts
TTS_LANGUAGE=en
TTS_MAX_CHARS_PER_CHUNK=280
# Optional: FFMPEG_BINARY=/usr/bin/ffmpeg
```

The API downloads the authenticated Cloudinary voice sample to a temporary WAV and passes it to Coqui as `speaker_wav`; Cloudinary credentials are never exposed to the browser. By default it uses XTTS-v2's native cloning. To use the voice-conversion API shown in the question with a compatible base TTS model, configure:

```
TTS_MODEL_NAME=tts_models/de/thorsten/tacotron2-DDC
TTS_VOICE_CLONING_METHOD=vc
```

This executes Coqui's `tts_with_vc_to_file(text, speaker_wav=..., file_path=...)` for every book chunk. Coqui downloads model weights into `TTS_CACHE_DIR` on first use. Plan for several GB of persistent disk and several GB of RAM; CPU generation can take minutes for a book. A CUDA GPU makes synthesis substantially faster but needs compatible PyTorch/CUDA runtime and enough GPU memory. This is commonly too heavy for a small Railway container, so use a persistent volume and a GPU-capable worker service for production.

This code intentionally uses a one-worker in-process thread pool per Gunicorn process because the current deployment has no queue service. Jobs are lost when a web process restarts and are not coordinated across replicas. For production/scale, move `app.controllers.book_narration_controller._generate_narration` to a durable Celery or RQ worker backed by Redis, while retaining the same `BookNarration` status polling API.

For CPU-only development environments, install the PyTorch runtime from its CPU wheel index after installing requirements:

```bash
python -m pip install torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cpu
```

After changing dependencies, restart the Flask process. The first actual narration then downloads the selected Coqui model weights into `TTS_CACHE_DIR`; this is separate from installing the Python package.
