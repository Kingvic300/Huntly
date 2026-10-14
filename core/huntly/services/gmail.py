"""Gmail via the official OAuth 2.0 installed-app flow.

* The user supplies their *own* OAuth client (Desktop app) from their own Google
  Cloud project. Huntly ships no client ID and no shared backend.
* The consent screen opens in the system browser; Google redirects to a
  temporary loopback listener on 127.0.0.1.
* The resulting token is stored only in the encrypted local vault.
* Scopes: ``gmail.compose`` (create drafts, send what you approve) and
  ``gmail.metadata`` (read headers such as From/Date of messages in a thread, used
  only to notice replies to applications you sent). Huntly cannot read message bodies.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import threading
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Protocol

log = logging.getLogger(__name__)

COMPOSE = "https://www.googleapis.com/auth/gmail.compose"
METADATA = "https://www.googleapis.com/auth/gmail.metadata"
READONLY = "https://www.googleapis.com/auth/gmail.readonly"  # only when the user opts in to reply reading
SCOPES = [COMPOSE, METADATA]


def scopes_for(read_replies: bool) -> list[str]:
    return [COMPOSE, READONLY] if read_replies else SCOPES


class Sent(dict):
    """Result of a send: Gmail message id and thread id."""

    @property
    def id(self) -> str:
        return self["id"]

    @property
    def thread_id(self) -> str | None:
        return self.get("threadId")


class GmailError(Exception):
    pass


class GmailGateway(Protocol):
    def email_address(self) -> str: ...
    def create_draft(self, msg: EmailMessage, thread_id: str | None = None) -> str: ...
    def update_draft(self, draft_id: str, msg: EmailMessage, thread_id: str | None = None) -> str: ...
    def send_draft(self, draft_id: str) -> Sent: ...
    def send_message(self, msg: EmailMessage) -> str: ...
    def can_read_metadata(self) -> bool: ...
    def message_id_header(self, message_id: str) -> str | None: ...
    def thread_senders(self, thread_id: str) -> list[tuple[str, str, str, str]]: ...
    def can_read_bodies(self) -> bool: ...
    def message_text(self, message_id: str) -> str: ...


def _raw(msg: EmailMessage) -> str:
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def build_message(
    *,
    sender: str,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    attachments: list[Path] | None = None,
    in_reply_to: str | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    for path in attachments or []:
        ctype, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
    return msg


class GoogleGmail:
    """Real Gmail gateway backed by google-api-python-client."""

    def __init__(self, token_json: str, on_token_refresh: Callable[[str], None]):
        from google.oauth2.credentials import Credentials

        # Use the scopes stored with the token, so older compose-only tokens are recognised as such.
        self._creds = Credentials.from_authorized_user_info(json.loads(token_json))
        self._on_refresh = on_token_refresh
        self._service = None

    def _svc(self):
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        if not self._creds.valid:
            if self._creds.expired and self._creds.refresh_token:
                try:
                    self._creds.refresh(Request())
                except RefreshError as exc:
                    raise GmailError("Gmail authorisation expired or was revoked. Reconnect Gmail in Settings.") from exc
                self._on_refresh(self._creds.to_json())
            else:
                raise GmailError("Gmail token invalid. Reconnect Gmail in Settings.")
        if self._service is None:
            self._service = build("gmail", "v1", credentials=self._creds, cache_discovery=False)
        return self._service

    def _call(self, request):
        from googleapiclient.errors import HttpError

        try:
            return request.execute(num_retries=2)
        except HttpError as exc:
            raise GmailError(f"Gmail API error {exc.resp.status}") from exc

    def email_address(self) -> str:
        return self._call(self._svc().users().getProfile(userId="me"))["emailAddress"]

    @staticmethod
    def _message_body(msg: EmailMessage, thread_id: str | None) -> dict:
        body = {"raw": _raw(msg)}
        if thread_id:
            body["threadId"] = thread_id
        return body

    def create_draft(self, msg: EmailMessage, thread_id: str | None = None) -> str:
        res = self._call(self._svc().users().drafts().create(userId="me", body={"message": self._message_body(msg, thread_id)}))
        return res["id"]

    def update_draft(self, draft_id: str, msg: EmailMessage, thread_id: str | None = None) -> str:
        res = self._call(
            self._svc().users().drafts().update(userId="me", id=draft_id, body={"id": draft_id, "message": self._message_body(msg, thread_id)})
        )
        return res["id"]

    def send_draft(self, draft_id: str) -> Sent:
        res = self._call(self._svc().users().drafts().send(userId="me", body={"id": draft_id}))
        return Sent(id=res["id"], threadId=res.get("threadId"))

    def _scopes(self) -> set[str]:
        return set(self._creds.scopes or []) | set(getattr(self._creds, "granted_scopes", None) or [])

    def can_read_metadata(self) -> bool:
        return bool(self._scopes() & {METADATA, READONLY})

    def can_read_bodies(self) -> bool:
        return READONLY in self._scopes()

    def message_text(self, message_id: str) -> str:
        """Plain text of one message, for local classification only. Never stored."""
        from huntly.security.sanitize import html_to_text

        res = self._call(self._svc().users().messages().get(userId="me", id=message_id, format="full"))
        plain, html = [], []

        def walk(part):
            mime = part.get("mimeType", "")
            data = part.get("body", {}).get("data")
            if data and mime in ("text/plain", "text/html"):
                text = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
                (plain if mime == "text/plain" else html).append(text)
            for p in part.get("parts", []) or []:
                walk(p)

        walk(res.get("payload", {}))
        return ("\n".join(plain) if plain else html_to_text("\n".join(html)))[:20000]

    def message_id_header(self, message_id: str) -> str | None:
        if not self.can_read_metadata():
            return None
        res = self._call(self._svc().users().messages().get(userId="me", id=message_id, format="metadata", metadataHeaders=["Message-ID"]))
        for h in res.get("payload", {}).get("headers", []):
            if h.get("name", "").lower() == "message-id":
                return h.get("value")
        return None

    def thread_senders(self, thread_id: str) -> list[tuple[str, str, str, str]]:
        """(From, internalDate ms, Subject, message id) for each message in a thread. Headers only."""
        res = self._call(self._svc().users().threads().get(userId="me", id=thread_id, format="metadata", metadataHeaders=["From", "Subject"]))
        out = []
        for m in res.get("messages", []):
            headers = {h.get("name", "").lower(): h.get("value", "") for h in m.get("payload", {}).get("headers", [])}
            out.append((headers.get("from", ""), m.get("internalDate", "0"), headers.get("subject", ""), m.get("id", "")))
        return out

    def send_message(self, msg: EmailMessage) -> str:
        res = self._call(self._svc().users().messages().send(userId="me", body={"raw": _raw(msg)}))
        return res["id"]


def validate_client_config(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise GmailError("OAuth client must be the JSON file downloaded from Google Cloud Console") from exc
    inner = data.get("installed")
    if not isinstance(inner, dict):
        raise GmailError("Use an OAuth client of type 'Desktop app' (JSON must contain an 'installed' section)")
    for key in ("client_id", "client_secret", "auth_uri", "token_uri"):
        if not inner.get(key):
            raise GmailError(f"OAuth client JSON is missing '{key}'")
    return data


class OAuthFlowState:
    """Tracks one in-progress browser consent flow (run in a background thread)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.error: str | None = None
        self.auth_url: str | None = None


def run_installed_flow(client_config: dict, state: OAuthFlowState, on_success: Callable[[str], None], scopes: list[str] | None = None) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    def target():
        try:
            flow = InstalledAppFlow.from_client_config(client_config, scopes or SCOPES)
            creds = flow.run_local_server(
                host="127.0.0.1",
                bind_addr="127.0.0.1",
                port=0,
                open_browser=True,
                authorization_prompt_message="",
                success_message="Huntly is connected to Gmail. You can close this tab and return to the app.",
                timeout_seconds=300,
                access_type="offline",
                prompt="consent",
            )
            if not creds or not creds.refresh_token:
                raise GmailError("Google did not return a refresh token; try again")
            on_success(creds.to_json())
            state.error = None
        except Exception as exc:
            log.warning("gmail oauth flow failed: %s", type(exc).__name__)
            state.error = str(exc) or type(exc).__name__
        finally:
            state.running = False

    with state.lock:
        if state.running:
            raise GmailError("A Gmail connection is already in progress")
        state.running = True
        state.error = None
    threading.Thread(target=target, name="gmail-oauth", daemon=True).start()
