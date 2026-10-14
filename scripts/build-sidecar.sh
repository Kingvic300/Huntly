#!/usr/bin/env bash
# Build the Python core into a single executable and place it where Tauri expects a sidecar.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HUNTLY_PYTHON:-$ROOT/.venv/bin/python}"
command -v "$PY" >/dev/null 2>&1 || [[ -x "$PY" ]] || PY=python
TRIPLE="$(rustc -vV | sed -n 's/^host: //p')"
EXT=""
[[ "$TRIPLE" == *windows* ]] && EXT=".exe"

cd "$ROOT/core/packaging"
"$PY" -m PyInstaller --noconfirm --clean --distpath "$ROOT/core/dist" --workpath "$ROOT/core/build" huntly-core.spec
mkdir -p "$ROOT/desktop/src-tauri/binaries"
cp "$ROOT/core/dist/huntly-core$EXT" "$ROOT/desktop/src-tauri/binaries/huntly-core-$TRIPLE$EXT"
echo "Sidecar ready: desktop/src-tauri/binaries/huntly-core-$TRIPLE$EXT"
