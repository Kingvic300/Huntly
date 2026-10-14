"""Application context shared by the API, background workers and tests."""

from __future__ import annotations

import logging
import threading
from typing import Callable

from huntly.config import Paths
from huntly.db import Database
from huntly.security.vault import Vault, VaultLocked
from huntly.services import store
from huntly.services.gmail import GmailError, GmailGateway, GoogleGmail, OAuthFlowState
from huntly.services.llm import GroqClient

log = logging.getLogger(__name__)


class AppContext:
    def __init__(
        self,
        paths: Paths,
        *,
        kdf_params: dict | None = None,
        gmail_factory: Callable[["AppContext"], GmailGateway] | None = None,
        groq_factory: Callable[[str, str], GroqClient] | None = None,
        fetch=None,
    ):
        self.paths = paths
        self.db = Database(paths.db)
        self.vault = Vault(paths.vault, kdf_params)
        self.oauth_state = OAuthFlowState()
        self.collect_lock = threading.Lock()
        self._gmail_factory = gmail_factory or _google_gmail
        self._groq_factory = groq_factory or (lambda key, model: GroqClient(key, model))
        self.fetch = fetch  # injectable HTTP fetcher for tests
        self.scheduler = None

    def startup(self) -> None:
        self.db.migrate()
        self.vault.try_keyring_unlock()

    def secret(self, name: str) -> str | None:
        if not self.vault.unlocked:
            raise VaultLocked("Unlock the vault to use stored credentials")
        with self.db.session() as s:
            return store.get_secret(s, self.vault, name)

    def store_secret(self, name: str, value: str) -> None:
        with self.db.session() as s:
            store.put_secret(s, self.vault, name, value)

    def gmail(self) -> GmailGateway:
        return self._gmail_factory(self)

    def gmail_connected(self) -> bool:
        with self.db.session() as s:
            return s.get(store.Secret, "google_token") is not None

    def groq(self) -> GroqClient | None:
        with self.db.session() as s:
            enabled = store.get_setting(s, "groq_enabled")
            model = store.get_setting(s, "groq_model")
        if not enabled or not self.vault.unlocked:
            return None
        key = self.secret("groq_api_key")
        return self._groq_factory(key, model) if key else None


def _google_gmail(ctx: AppContext) -> GmailGateway:
    token = ctx.secret("google_token")
    if not token:
        raise GmailError("Gmail is not connected")
    return GoogleGmail(token, on_token_refresh=lambda t: ctx.store_secret("google_token", t))
