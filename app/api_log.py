"""File-based request logging for the Flask API."""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import g, request


LOGGER_NAME = "teachalike.api_requests"


def setup_api_request_logging(app):
    """Log every API request to ``Teach-api/logs.txt``.

    Only request metadata is recorded. Authorization headers, request bodies,
    passwords, tokens, and uploaded audio are deliberately excluded.
    """
    log_path = Path(app.root_path).parent / "logs.txt"
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not any(getattr(handler, "_teachalike_api_handler", False) for handler in logger.handlers):
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler._teachalike_api_handler = True
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

    def is_api_request():
        return request.path.startswith("/api/")

    def write_log(status_code, *, error_type=None):
        if not is_api_request() or getattr(g, "api_request_logged", False):
            return

        started_at = getattr(g, "api_request_started_at", time.perf_counter())
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": getattr(g, "api_request_id", None),
            "method": request.method,
            "path": request.path,
            "status": status_code,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            "remote_addr": request.remote_addr,
            "user_agent": request.user_agent.string[:300],
        }
        if error_type:
            record["error_type"] = error_type
        logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        g.api_request_logged = True

    @app.before_request
    def start_api_request_log():
        if is_api_request():
            g.api_request_started_at = time.perf_counter()
            g.api_request_id = f"{int(time.time() * 1000):x}-{id(g):x}"

    @app.after_request
    def finish_api_request_log(response):
        write_log(response.status_code)
        return response

    @app.teardown_request
    def log_unhandled_api_error(exception):
        if exception is not None:
            write_log(500, error_type=type(exception).__name__)
