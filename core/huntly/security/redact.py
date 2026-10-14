"""Redact anything that looks like a credential before it is logged or stored in audit trails."""

from __future__ import annotations

import re
import threading

_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"gsk_[A-Za-z0-9]{10,}"),  # Groq keys
    re.compile(r"ya29\.[A-Za-z0-9._-]{10,}"),  # Google access tokens
    re.compile(r"1//[A-Za-z0-9._-]{10,}"),  # Google refresh tokens
    re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}"),  # Google client secrets
    re.compile(r"AAAAAAAAAAAAAAAAAAAAA[A-Za-z0-9%]{10,}"),  # X bearer tokens
    re.compile(
        r"(?i)((?:api[_-]?key|token|secret|password|authorization|client_secret)\"?\s*[:=]\s*\"?)[^\s\",}]{4,}"
    ),
]

_known_lock = threading.Lock()
_known_secrets: set[str] = set()


def register_secret(value: str | None) -> None:
    """Remember a live secret value so it is scrubbed verbatim from any log line."""
    if value and len(value) >= 6:
        with _known_lock:
            _known_secrets.add(value)


def forget_all_secrets() -> None:
    with _known_lock:
        _known_secrets.clear()


def redact_text(text: str) -> str:
    if not text:
        return text
    with _known_lock:
        known = sorted(_known_secrets, key=len, reverse=True)
    for secret in known:
        text = text.replace(secret, "[REDACTED]")
    for pattern in _PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: m.group(1) + "[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text
