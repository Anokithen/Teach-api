import logging
import os
import time
from urllib.parse import urlsplit

from app import create_app


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = create_app()


def initialize_database():
    """Create missing tables without preventing the web process from booting."""
    from app.extensions import db

    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    parsed = urlsplit(uri)
    logger.info(
        "Connecting to database at %s:%s (db=%s)",
        parsed.hostname,
        parsed.port,
        (parsed.path or "").lstrip("/"),
    )

    max_attempts = int(os.getenv("DB_INIT_MAX_ATTEMPTS", "5"))
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
                    # Keep the HTTP process alive so Railway's health check
                    # can still pass. Database-backed endpoints will return
                    # the configured database error response until the DB is
                    # reachable or the service is redeployed.
                    logger.exception(
                        "Could not create database tables after %s attempts. "
                        "Check the Railway MYSQL_URL/MYSQL_* variables or the "
                        "DB_* fallback values.",
                        max_attempts,
                    )
                    return
                logger.warning(
                    "Database not reachable yet (attempt %s/%s), retrying in %ss...",
                    attempt,
                    max_attempts,
                    retry_delay,
                )
                time.sleep(retry_delay)


initialize_database()

if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
    )
