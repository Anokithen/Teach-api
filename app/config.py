from datetime import timedelta
import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "root123")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_NAME = os.getenv("DB_NAME", "teachalike_db")
    DB_PORT = os.getenv("DB_PORT","3306")
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "super-secret-key-change-me")
    JWT_TIMEOUT = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "15"))
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
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024
