from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from huntly.api.app import create_app
from huntly.config import Paths
from huntly.context import AppContext
from huntly.security.ssrf import FetchResult
from huntly.services.profile import Experience, ProfileData, save_profile

FAST_KDF = {"name": "argon2id", "memory_cost": 1024, "iterations": 1, "lanes": 1, "length": 32}
TOKEN = "test-token-0123456789"
PASSWORD = "correct horse battery"


class FakeGmail:
    """Records every call. Never touches the network."""

    def __init__(self, address: str = "me@example.com"):
        self.address = address
        self.drafts: dict[str, object] = {}
        self.draft_threads: dict[str, str | None] = {}
        self.sent: list[tuple[str, object]] = []
        self.threads: dict[str, list[tuple[str, str]]] = {}
        self.metadata = True
        self.bodies: dict[str, str] | None = None  # message id -> text when "read access" is granted

    def email_address(self) -> str:
        return self.address

    def create_draft(self, msg, thread_id=None) -> str:
        draft_id = f"d{len(self.drafts) + 1}"
        self.drafts[draft_id] = msg
        self.draft_threads[draft_id] = thread_id
        return draft_id

    def update_draft(self, draft_id, msg, thread_id=None) -> str:
        self.drafts[draft_id] = msg
        self.draft_threads[draft_id] = thread_id
        return draft_id

    def send_draft(self, draft_id):
        from huntly.services.gmail import Sent

        self.sent.append(("draft", self.drafts[draft_id]))
        thread = self.draft_threads.get(draft_id) or f"t{len(self.sent)}"
        self.threads.setdefault(thread, []).append((self.address, "1000", self.drafts[draft_id]["Subject"]))
        return Sent(id=f"m{len(self.sent)}", threadId=thread)

    def can_read_metadata(self) -> bool:
        return self.metadata

    def message_id_header(self, message_id):
        return f"<{message_id}@mail.example>"

    def thread_senders(self, thread_id):
        return self.threads.get(thread_id, [])

    def can_read_bodies(self) -> bool:
        return self.bodies is not None

    def message_text(self, message_id):
        return (self.bodies or {})[message_id]

    def send_message(self, msg) -> str:
        self.sent.append(("message", msg))
        return f"m{len(self.sent)}"


class FakeFetch:
    def __init__(self, routes: dict[str, tuple[int, object]] | None = None):
        self.routes = routes or {}
        self.calls: list[tuple[str, dict | None, dict | None]] = []

    def __call__(self, url, *, headers=None, params=None, **_):
        self.calls.append((url, headers, params))
        status, body = self.routes.get(url, (404, b"not found"))
        if isinstance(body, (dict, list)):
            content, ctype = json.dumps(body).encode(), "application/json"
        elif isinstance(body, str):
            content, ctype = body.encode(), "text/html; charset=utf-8"
        else:
            content, ctype = body, "application/octet-stream"
        return FetchResult(url, status, httpx.Headers({"content-type": ctype}), content)


@pytest.fixture
def fake_gmail():
    return FakeGmail()


@pytest.fixture
def fake_fetch():
    return FakeFetch()


@pytest.fixture
def ctx(tmp_path: Path, fake_gmail, fake_fetch, monkeypatch) -> AppContext:
    monkeypatch.setattr("huntly.security.vault.keyring_available", lambda: False)
    c = AppContext(Paths(tmp_path / "data").ensure(), kdf_params=FAST_KDF, gmail_factory=lambda _ctx: fake_gmail, fetch=fake_fetch)
    c.startup()
    return c


@pytest.fixture
def unlocked(ctx) -> AppContext:
    ctx.vault.create(PASSWORD)
    return ctx


@pytest.fixture
def client(ctx) -> TestClient:
    app = create_app(ctx, TOKEN)
    return TestClient(app, base_url="http://127.0.0.1", headers={"Authorization": f"Bearer {TOKEN}"})


SAMPLE_PROFILE = ProfileData(
    full_name="Ada Example",
    headline="Backend Engineer",
    email="ada@example.com",
    location="Lagos, Nigeria",
    summary="Backend engineer focused on reliable APIs.",
    skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS", "React"],
    experience=[
        Experience(
            title="Backend Engineer",
            company="Acme Ltd",
            start="2021",
            end="Present",
            highlights=["Built payment APIs in Python and FastAPI", "Cut deploy time by moving to Docker"],
        )
    ],
    target_roles=["Backend Engineer", "Python Developer"],
    preferred_locations=["Lagos"],
)


@pytest.fixture
def with_profile(ctx):
    with ctx.db.session() as s:
        save_profile(s, SAMPLE_PROFILE)
    return ctx
