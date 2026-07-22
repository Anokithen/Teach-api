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

The browser records audio, uploads it to the authenticated `/api/reading-sessions/:id/pronunciation-transcript` endpoint, and then sends the returned transcript to the existing pronunciation scoring endpoint. Recordings are deleted from the server immediately after transcription.

## Voice-cloned book narration (XTTS-v2)

Book preview narrations are generated separately from reading sessions. A parent selects one of their ready voice profiles and requests a cached narration for that `(book, voice profile)` pair. Generated audio and source recordings are private authenticated Cloudinary resources; the API only redirects to a signed URL after an ownership check.

Set these server environment variables (the defaults are also in `.env.example`):

```env
XTTS_MODEL_NAME=tts_models/multilingual/multi-dataset/xtts_v2
XTTS_DEVICE=cpu
XTTS_CACHE_DIR=/app/models/xtts
XTTS_LANGUAGE=en
XTTS_MAX_CHARS_PER_CHUNK=280
# Optional: FFMPEG_BINARY=/usr/bin/ffmpeg
```

XTTS downloads its weights into `XTTS_CACHE_DIR` on first use. The API uses the maintained `coqui-tts` package (which provides `TTS.api` and supports Python 3.12). Plan for several GB of persistent disk and several GB of RAM; CPU generation can take minutes for a book. A CUDA GPU makes synthesis substantially faster but needs compatible PyTorch/CUDA runtime and enough GPU memory. This is commonly too heavy for a small Railway container, so use a persistent volume and a GPU-capable worker service for production.

This code intentionally uses a one-worker in-process thread pool per Gunicorn process because the current deployment has no queue service. Jobs are lost when a web process restarts and are not coordinated across replicas. For production/scale, move `app.controllers.book_narration_controller._generate_narration` to a durable Celery or RQ worker backed by Redis, while retaining the same `BookNarration` status polling API.

For CPU-only development environments, install the PyTorch runtime from its CPU wheel index after installing requirements:

```bash
python -m pip install torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cpu
```

After changing dependencies, restart the Flask process. The first actual narration then downloads the XTTS-v2 model weights into `XTTS_CACHE_DIR`; this is separate from installing the Python package.
