from datetime import timedelta
import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


def _env_value(*names, default=""):
    """Read the first usable environment value and strip accidental quotes."""
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1].strip()
       
        if value and "${{" not in value and "}}" not in value:
            return value
    return default


def _build_database_uri():
    """Build the SQLAlchemy MySQL URI from whatever Railway (or local .env)
    variables are actually available.

    Priority:
    1. A full connection URL: MYSQL_URL / MYSQL_PUBLIC_URL / DATABASE_URL.
       Railway's MySQL plugin exposes ``MYSQL_URL`` as a service reference,
       e.g. ``MYSQL_URL=${{MySQL.MYSQL_URL}}`` on the API service.
    2. Railway's individual MYSQL* variables (MYSQLHOST, MYSQLPORT, ...).
    3. The generic DB_* variables (used for local development).
    """

    railway_url = _env_value("MYSQL_URL", "MYSQL_PUBLIC_URL", "DATABASE_URL")
    if railway_url:
        scheme, separator, remainder = railway_url.partition("://")
        if not separator or scheme.lower() not in {"mysql", "mysql+pymysql"}:
            raise ValueError(
                "Only MySQL connection URLs are supported. Configure MYSQL_URL "
                "or a mysql:// DATABASE_URL."
            )
        return f"mysql+pymysql://{remainder}"

    db_user = _env_value("MYSQLUSER", "DB_USER", default="root")
    db_password = _env_value(
        "MYSQLPASSWORD", "MYSQL_ROOT_PASSWORD", "DB_PASSWORD", default="root123"
    )
    db_host = _env_value("MYSQLHOST", "DB_HOST", default="localhost")
    db_port = _env_value("MYSQLPORT", "DB_PORT", default="3306")
    db_name = _env_value(
        "MYSQLDATABASE", "MYSQL_DATABASE", "DB_NAME", default="teachalike_db"
    )

    return (
        f"mysql+pymysql://{quote_plus(db_user)}:{quote_plus(db_password)}"
        f"@{db_host}:{db_port}/{quote_plus(db_name)}"
    )


class Config:
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("DB_HOST")
    DB_NAME = os.getenv("DB_NAME")
    DB_PORT = os.getenv("DB_PORT")

    SQLALCHEMY_DATABASE_URI = _build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {

        "pool_pre_ping": True,
        "pool_recycle": 280,
        "connect_args": {"connect_timeout": 5},
    }
    JWT_SECRET_KEY = _env_value("JWT_SECRET_KEY", default="super-secret-key-change-me")
    
    _access_token_minutes = _env_value("JWT_ACCESS_TOKEN_EXPIRES_MINUTES")
    JWT_ACCESS_TOKEN_EXPIRES = (
        timedelta(minutes=int(_access_token_minutes))
        if _access_token_minutes
        else timedelta(days=int(_env_value("JWT_TIMEOUT", default="15")))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "30"))
    )
    _frontend_origins = _env_value("FRONTEND_ORIGINS")
    _frontend_origin_values = (_frontend_origins or "*").split(",")
    FRONTEND_ORIGINS = [
        origin.strip().rstrip("/")
        for origin in _frontend_origin_values
        if origin.strip()
    ] or ["*"]
    
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

    # Keep this server-side. Never expose the ElevenLabs key through Next.js
    # public environment variables or return it from an API response.
    ELEVENLABS_API_KEY = _env_value("ELEVENLABS_API_KEY")
    ELEVENLABS_MODEL_ID = _env_value("ELEVENLABS_MODEL_ID", default="eleven_multilingual_v2")
    ELEVENLABS_OUTPUT_FORMAT = _env_value("ELEVENLABS_OUTPUT_FORMAT", default="mp3_44100_128")
    ELEVENLABS_LANGUAGE_CODE = _env_value("ELEVENLABS_LANGUAGE_CODE")
    ELEVENLABS_MAX_CHARS_PER_CHUNK = int(_env_value("ELEVENLABS_MAX_CHARS_PER_CHUNK", default="4500"))
    ELEVENLABS_REQUEST_TIMEOUT = int(_env_value("ELEVENLABS_REQUEST_TIMEOUT", default="120"))
    FFMPEG_BINARY = _env_value("FFMPEG_BINARY")

    GEMINI_API_KEY = _env_value("GEMINI_API_KEY", "GOOGLE_API_KEY")
    GEMINI_MODEL = _env_value("GEMINI_MODEL", default="gemini-2.5-flash")
    GEMINI_REQUEST_TIMEOUT = int(_env_value("GEMINI_REQUEST_TIMEOUT", default="45"))

    # Groq model discovery and chat calls stay server-side. NVIDIA/Gemini remain
    # available as legacy provider overrides for existing deployments.
    BOOK_GENERATION_PROVIDER = _env_value("BOOK_GENERATION_PROVIDER", default="groq").lower()
    GROQ_API_KEY = _env_value("GROQ_API_KEY")
    GROQ_API_URL = _env_value("GROQ_API_URL", default="https://api.groq.com/openai/v1")
    GROQ_MODEL = _env_value("GROQ_MODEL", default="openai/gpt-oss-120b")
    GROQ_REQUEST_TIMEOUT = int(_env_value("GROQ_REQUEST_TIMEOUT", default="60"))
    NVIDIA_API_KEY = _env_value("NVIDIA_API_KEY", "NVAPI_KEY")
    NVIDIA_API_URL = _env_value(
        "NVIDIA_API_URL",
        default="https://integrate.api.nvidia.com/v1/chat/completions",
    )
    NVIDIA_MODEL = _env_value("NVIDIA_MODEL", default="openai/gpt-oss-120b")
    # Keep the upstream AI call below the Gunicorn/platform request window so
    # clients receive a useful error instead of waiting until the connection
    # is terminated by the deployment proxy.
    NVIDIA_REQUEST_TIMEOUT = int(_env_value("NVIDIA_REQUEST_TIMEOUT", default="120"))

    # NVIDIA ASR is used server-side for pronunciation recordings. Keep this
    # separate so the hosted ASR endpoint can differ from chat completions.
    NVIDIA_ASR_API_KEY = _env_value("NVIDIA_ASR_API_KEY", "NVIDIA_API_KEY", "NVAPI_KEY")
    NVIDIA_ASR_API_URL = _env_value(
        "NVIDIA_ASR_API_URL",
        default="https://1598d209-5e27-4d3c-8079-4751568b1081.invocation.api.nvcf.nvidia.com/v1/audio/transcriptions",
    )
    NVIDIA_ASR_LANGUAGE = _env_value("NVIDIA_ASR_LANGUAGE", default="en-US")
    NVIDIA_ASR_REQUEST_TIMEOUT = int(_env_value("NVIDIA_ASR_REQUEST_TIMEOUT", default="45"))
    NVIDIA_PRONUNCIATION_API_KEY = _env_value(
        "NVIDIA_PRONUNCIATION_API_KEY",
        "NVIDIA_ASR_API_KEY",
        "NVIDIA_API_KEY",
        "NVAPI_KEY",
    )
    NVIDIA_PRONUNCIATION_REQUEST_TIMEOUT = int(
        _env_value("NVIDIA_PRONUNCIATION_REQUEST_TIMEOUT", default="20")
    )

    VOSK_MODEL_PATH = os.getenv(
        "VOSK_MODEL_PATH",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "vosk-model-small-en-us-0.15"),
    )
  
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024
