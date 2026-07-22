FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VOSK_MODEL_PATH=/app/models/vosk-model-small-en-us-0.15

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl unzip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Coqui keeps PyTorch optional. Explicit CPU wheels keep a CPU Railway service
# from pulling CUDA packages; use a separate GPU image/runtime when XTTS_DEVICE=cuda.
RUN pip install --no-cache-dir torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Keep the large offline language model out of Git while ensuring every Railway
# image has the recogniser it needs.
RUN mkdir -p /app/models \
    && curl -fsSL https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -o /tmp/vosk-model.zip \
    && unzip -q /tmp/vosk-model.zip -d /app/models \
    && rm /tmp/vosk-model.zip

COPY . .

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --threads 4 --timeout 120 run:app"]
