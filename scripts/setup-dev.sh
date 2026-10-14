#!/usr/bin/env bash
# One-time developer setup: Python venv for the core and npm packages for the desktop shell.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

if [[ ! -d "$ROOT/.venv" ]]; then
  "$PYTHON" -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/pip" install --upgrade pip
"$ROOT/.venv/bin/pip" install -r "$ROOT/core/requirements-dev.txt"
"$ROOT/.venv/bin/pip" install -e "$ROOT/core" --no-deps

(cd "$ROOT/desktop" && npm ci)

cat <<'MSG'

Setup complete.
Linux system packages needed by Tauri (Debian / Ubuntu / Kali):
  sudo apt install -y libwebkit2gtk-4.1-dev libgtk-3-dev libsoup-3.0-dev librsvg2-dev \
    libayatana-appindicator3-dev build-essential libssl-dev patchelf file

Run the app in development:   scripts/dev.sh
Run all tests:                scripts/test.sh
Build installable packages:   scripts/build-linux.sh
MSG
