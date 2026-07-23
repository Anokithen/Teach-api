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


def _database_config_source():
    if _env_value("MYSQL_URL", "MYSQL_PUBLIC_URL", "DATABASE_URL"):
        return "MYSQL_URL/DATABASE_URL"
    if _env_value(
        "MYSQLHOST",
        "MYSQLPORT",
        "MYSQLUSER",
        "MYSQLPASSWORD",
        "MYSQL_ROOT_PASSWORD",
        "MYSQLDATABASE",
        "MYSQL_DATABASE",
    ):
        return "MYSQL_*"
    if _env_value("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"):
        return "DB_*"
    return "defaults"


class Config:
   
    SQLALCHEMY_DATABASE_URI = _build_database_uri()
    DATABASE_CONFIG_SOURCE = _database_config_source()
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
   
    FRONTEND_ORIGINS = [
        origin.strip()
        for origin in (_frontend_origins or "*").split(",")
        if origin.strip()
    ]
    
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

    VOSK_MODEL_PATH = os.getenv(
        "VOSK_MODEL_PATH",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "vosk-model-small-en-us-0.15"),
    )
  
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
