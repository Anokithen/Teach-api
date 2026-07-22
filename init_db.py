"""Initialize the TeachAlike schema before the web server starts.

Railway runs this as a one-time process before Gunicorn. Keeping initialization
outside ``run:app`` prevents every Gunicorn worker from racing to create the
same tables and makes database configuration failures visible in deployment
logs.
"""
import logging
import os
import time
from urllib.parse import urlsplit

from app import create_app
from app.extensions import db


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def initialize_database(app=None):
    app = app or create_app()
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    parsed = urlsplit(uri)
    logger.info(
        "Connecting to database at %s:%s (db=%s)",
        parsed.hostname,
        parsed.port,
        (parsed.path or "").lstrip("/"),
    )

    max_attempts = int(os.getenv("DB_INIT_MAX_ATTEMPTS", "10"))
    retry_delay = int(os.getenv("DB_INIT_RETRY_SECONDS", "3"))

    with app.app_context():
        for attempt in range(1, max_attempts + 1):
            try:
                db.create_all()
                logger.info("Database tables ready.")
                return
            except Exception:
                db.session.rollback()
                if attempt == max_attempts:
                    logger.exception(
                        "Could not create database tables after %s attempts. "
                        "Check the API service's MYSQL_URL/MYSQL_* variables "
                        "or the DB_* fallback values.",
                        max_attempts,
                    )
                    raise
                logger.warning(
                    "Database not reachable yet (attempt %s/%s), retrying in %ss...",
                    attempt,
                    max_attempts,
                    retry_delay,
                )
                time.sleep(retry_delay)


if __name__ == "__main__":
    initialize_database()
