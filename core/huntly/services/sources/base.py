"""Common types for job sources.

Every source returns :class:`RawJob` objects built from *untrusted* remote data.
Text is sanitised here; nothing from a job posting is ever interpreted as an instruction.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Protocol

from huntly.security.sanitize import clean_text, html_to_text, looks_like_injection
from huntly.security.ssrf import FetchResult, safe_get

SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
EMAIL = re.compile(r"(?i)\b(?:mailto:)?([a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,})\b")
REMOTE_HINT = re.compile(r"(?i)\b(remote|work from home|wfh|anywhere|distributed)\b")
# Hybrid means not remote. In a title or location any "hybrid" counts except tech terms ("Hybrid
# Cloud Engineer"); in the text it must describe the way of working ("hybrid role", "work model:
# hybrid", "3 days a week in the office"). "Remote or hybrid" offers remote, so it stays remote.
HYBRID_LABEL = re.compile(r"(?i)\bhybrid\b(?![\s-]*(?:cloud|apps?|mobile|application|infrastructure|integration|vehicle|it\b|environments?\b))")
HYBRID_TEXT = re.compile(
    r"(?i)\bhybrid[\s-]*(?:remote|role|position|job|work(?:ing|place)?|model|schedule|arrangement|set[- ]?up|policy|opportunity|basis)\b"
    r"|\b(?:workplace|work\s+(?:type|model|arrangement|style|location|setup)|working\s+model|location|this\s+(?:is\s+a|role\s+is))[\s:(-]*hybrid\b"
    r"|\b(?:\d|one|two|three|four)(?:\s*(?:-|to)\s*(?:\d|two|three|four))?\s*days?\s*(?:a|per|each|every)?\s*week\s+(?:in|at|from)\s+(?:the\s+|our\s+)?office"
)
REMOTE_OR_HYBRID = re.compile(r"(?i)\bremote\s*(?:or|/)\s*hybrid\b|\bhybrid\s*(?:or|/)\s*remote\b")


def is_hybrid(title: str, location: str, text: str) -> bool:
    head = f"{title} {location}"
    found = HYBRID_LABEL.search(head) or HYBRID_TEXT.search(text[:4000])
    return bool(found) and not REMOTE_OR_HYBRID.search(f"{head} {text[:4000]}")


class SourceError(Exception):
    pass


@dataclass
class RawJob:
    title: str
    url: str | None
    description: str = ""
    company: str | None = None
    location: str | None = None
    remote: bool | None = None
    posted_at: datetime | None = None
    external_id: str | None = None
    apply_email: str | None = None
    extra: dict = field(default_factory=dict)

    def normalized(self) -> "RawJob":
        self.title = clean_text(self.title, 300) or "Untitled role"
        self.company = clean_text(self.company or "", 200) or None
        self.location = clean_text(self.location or "", 200) or None
        self.description = html_to_text(self.description)
        if is_hybrid(self.title, self.location or "", self.description):
            self.remote = False  # even when the board files it under remote
        elif self.remote is None:
            self.remote = bool(REMOTE_HINT.search(f"{self.title} {self.location or ''} {self.description[:2000]}"))
        if not self.apply_email:
            m = EMAIL.search(self.description)
            if m and not m.group(1).lower().startswith(("noreply", "no-reply")):
                self.apply_email = m.group(1)[:320]
        if self.posted_at and self.posted_at.tzinfo is None:
            self.posted_at = self.posted_at.replace(tzinfo=timezone.utc)
        return self

    @property
    def injection_suspected(self) -> bool:
        return looks_like_injection(f"{self.title}\n{self.description}")

    def dedupe_key(self) -> str:
        if self.url:
            basis = re.sub(r"[?#].*$", "", self.url.strip().lower()).rstrip("/")
        else:
            basis = f"{self.title}|{self.company}|{self.location}".lower()
        return hashlib.sha256(basis.encode()).hexdigest()


@dataclass
class SourceContext:
    get_secret: Callable[[str], str | None]
    fetch: Callable[..., FetchResult] = safe_get


class JobSource(Protocol):
    kind: str
    label: str
    needs_secret: str | None

    def validate(self, config: dict) -> dict: ...

    def fetch(self, config: dict, ctx: SourceContext) -> list[RawJob]: ...


def parse_dt(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(ts, timezone.utc)
    if isinstance(value, str):
        v = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(v)
        except ValueError:
            from email.utils import parsedate_to_datetime

            try:
                dt = parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def require_ok(resp: FetchResult, what: str) -> None:
    if resp.status_code == 401 or resp.status_code == 403:
        raise SourceError(f"{what}: authorisation rejected (HTTP {resp.status_code}). Check your credentials.")
    if resp.status_code == 429:
        raise SourceError(f"{what}: rate limited (HTTP 429). It will retry on the next run.")
    if resp.status_code >= 400:
        raise SourceError(f"{what}: HTTP {resp.status_code}")
