"""Small persistence helpers: settings, encrypted credentials, audit log, notifications."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from huntly.models import AuditLog, Notification, Secret, Setting
from huntly.security.redact import redact_text
from huntly.security.vault import Vault

# Credentials the app knows how to use. Values are never returned by the API.
CREDENTIALS: dict[str, dict[str, str]] = {
    "google_oauth_client": {
        "label": "Google OAuth client (Desktop app JSON)",
        "help": "Create a 'Desktop app' OAuth client in your own Google Cloud project and paste the downloaded JSON.",
    },
    "google_token": {"label": "Gmail OAuth token", "help": "Created automatically when you connect Gmail."},
    "groq_api_key": {"label": "Groq API key", "help": "Optional. Enables LLM ranking notes and wording suggestions."},
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "collection_interval_minutes": 60,
    "collection_enabled": True,
    "digest_enabled": True,
    "digest_time": "08:00",
    "digest_min_score": 50,
    "min_score_to_show": 0,
    "groq_model": "llama-3.3-70b-versatile",
    "groq_enabled": False,
    "onboarding_complete": False,
    "approval_window_minutes": 15,
    "reply_tracking_enabled": True,
    "follow_up_after_days": 7,
    "reply_body_analysis": False,
    "auto_update": True,
    "directory_batch_size": 300,
}


def get_setting(s: Session, key: str) -> Any:
    row = s.get(Setting, key)
    return row.value if row is not None else DEFAULT_SETTINGS.get(key)


def all_settings(s: Session) -> dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    for row in s.scalars(select(Setting)):
        out[row.key] = row.value
    return out


def set_setting(s: Session, key: str, value: Any) -> None:
    row = s.get(Setting, key)
    if row is None:
        s.add(Setting(key=key, value=value))
    else:
        row.value = value


def put_secret(s: Session, vault: Vault, name: str, value: str) -> None:
    if name not in CREDENTIALS:
        raise KeyError(name)
    nonce, ct = vault.seal(name, value)
    row = s.get(Secret, name)
    if row is None:
        s.add(Secret(name=name, nonce=nonce, ciphertext=ct))
    else:
        row.nonce, row.ciphertext = nonce, ct


def get_secret(s: Session, vault: Vault, name: str) -> str | None:
    row = s.get(Secret, name)
    if row is None:
        return None
    return vault.open(name, row.nonce, row.ciphertext)


def delete_secret(s: Session, name: str) -> bool:
    row = s.get(Secret, name)
    if row is None:
        return False
    s.delete(row)
    return True


def credential_status(s: Session) -> list[dict]:
    present = {row.name: row.updated_at for row in s.scalars(select(Secret))}
    return [
        {
            "name": name,
            "label": meta["label"],
            "help": meta["help"],
            "configured": name in present,
            "updated_at": present.get(name),
        }
        for name, meta in CREDENTIALS.items()
    ]


def audit(s: Session, actor: str, action: str, entity: str, entity_id: Any = None, **detail: Any) -> None:
    safe = {k: redact_text(str(v)) if isinstance(v, str) else v for k, v in detail.items()}
    s.add(AuditLog(actor=actor, action=action, entity=entity, entity_id=str(entity_id) if entity_id else None, detail=safe))


def notify(s: Session, title: str, body: str = "", level: str = "info") -> None:
    s.add(Notification(title=title[:200], body=body, level=level))


def iso(dt: datetime | None) -> str | None:
    """Serialise a timestamp. SQLite drops tzinfo, and every stored time is UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
