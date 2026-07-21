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
