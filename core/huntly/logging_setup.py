"""Structured JSON logging with secret redaction.

Logs are written only to the local data directory and stderr. Every record passes
through a redaction filter so tokens and keys never reach disk even by accident.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path

from huntly.security.redact import redact_text


class RedactingJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_text(record.getMessage()),
        }
        extra = getattr(record, "data", None)
        if isinstance(extra, dict):
            payload["data"] = json.loads(redact_text(json.dumps(extra, default=str)))
        if record.exc_info:
            payload["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(log_dir: Path, level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    fmt = RedactingJsonFormatter()

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "core.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)

    # Third-party clients can log full URLs/headers at DEBUG; keep them quiet.
    for noisy in ("httpx", "httpcore", "googleapiclient", "google_auth_oauthlib", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
