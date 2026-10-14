#!/usr/bin/env bash
# Start the desktop app in development mode. The shell spawns the Python core from .venv.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/desktop"
exec npx tauri dev
