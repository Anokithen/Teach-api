from datetime import timedelta
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


class Config:
    # Railway's MySQL plugin exposes MYSQL_* variables (and, depending on
    # the service setup, MYSQL_URL). Keep the DB_* names for local/custom
    # deployments, and allow a standard DATABASE_URL as a final option.
    DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("MYSQL_URL")
    DB_USER = os.getenv("DB_USER") or os.getenv("MYSQLUSER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("MYSQLPASSWORD", "")
    DB_HOST = os.getenv("DB_HOST") or os.getenv("MYSQLHOST", "localhost")
    DB_NAME = os.getenv("DB_NAME") or os.getenv("MYSQLDATABASE", "teachalike_db")
    DB_PORT = os.getenv("DB_PORT") or os.getenv("MYSQLPORT", "3306")

    if DATABASE_URL:
        # SQLAlchemy's MySQL dialect needs the PyMySQL driver explicitly.
        SQLALCHEMY_DATABASE_URI = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)
    else:
        # Quote credentials and the database name so Railway-generated values
        # containing punctuation do not produce an invalid connection URL.
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}"
            f"@{DB_HOST}:{DB_PORT}/{quote_plus(DB_NAME)}"
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secret-key-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "15"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "30"))
    )
    FRONTEND_ORIGINS = [
        origin.strip()
        for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ]
    # Voice recordings are sent to Cloudinary through the API, never from the
    # browser. Keep these values in the server's .env file.
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
    # Path to a locally downloaded Vosk speech-recognition model. This keeps
    # children's microphone recordings on this server and avoids cloud AI APIs.
    VOSK_MODEL_PATH = os.getenv(
        "VOSK_MODEL_PATH",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "vosk-model-small-en-us-0.15"),
    )
    # Coqui model configuration.  ``native`` uses a voice-cloning model such
    # as XTTS-v2 directly; ``vc`` first speaks with any compatible TTS model
    # and then runs Coqui's voice-conversion model using the uploaded sample.
    # The XTTS names remain supported for existing deployments.
    TTS_MODEL_NAME = os.getenv(
        "TTS_MODEL_NAME",
        os.getenv("XTTS_MODEL_NAME", "tts_models/multilingual/multi-dataset/xtts_v2"),
    )
    TTS_VOICE_CLONING_METHOD = os.getenv("TTS_VOICE_CLONING_METHOD", "native").lower()
    TTS_DEVICE = os.getenv("TTS_DEVICE", os.getenv("XTTS_DEVICE", "cpu"))
    TTS_CACHE_DIR = os.getenv(
        "TTS_CACHE_DIR",
        os.getenv("XTTS_CACHE_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "tts")),
    )
    TTS_LANGUAGE = os.getenv("TTS_LANGUAGE", os.getenv("XTTS_LANGUAGE", "en"))
    TTS_MAX_CHARS_PER_CHUNK = int(os.getenv("TTS_MAX_CHARS_PER_CHUNK", os.getenv("XTTS_MAX_CHARS_PER_CHUNK", "280")))
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024
