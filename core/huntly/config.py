"""Runtime paths and constants.

All user data lives under a single per-user data directory. Nothing is written
outside it and nothing is sent anywhere unless the user triggers a network action.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

APP_NAME = "huntly"
TIMEZONE_NAME = "Africa/Lagos"
TZ = ZoneInfo(TIMEZONE_NAME)

# Upper bounds for anything we ingest from the network or from the user.
MAX_HTTP_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_JOB_DESCRIPTION_CHARS = 20_000
HTTP_TIMEOUT_SECONDS = 20.0
USER_AGENT = "Huntly/0.2.0 (+https://github.com/Kingvic300/Huntly; local desktop job assistant)"


def _default_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_NAME


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def db(self) -> Path:
        return self.root / "huntly.sqlite3"

    @property
    def vault(self) -> Path:
        return self.root / "vault.json"

    @property
    def documents(self) -> Path:
        return self.root / "documents"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def ensure(self) -> "Paths":
        for p in (self.root, self.documents, self.logs):
            p.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(p, 0o700)
            except OSError:
                pass
        return self


def get_paths() -> Paths:
    root = os.environ.get("HUNTLY_DATA_DIR")
    return Paths(Path(root) if root else _default_data_dir()).ensure()


def resource_path(*parts: str) -> Path:
    """Locate bundled resources both from source and from a PyInstaller bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    candidate = base.joinpath("huntly", *parts)
    if candidate.exists():
        return candidate
    return Path(__file__).resolve().parent.joinpath(*parts)
