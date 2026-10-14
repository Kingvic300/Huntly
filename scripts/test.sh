#!/usr/bin/env bash
# Run every automated test. External services are mocked; no real email is ever sent.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "== core (pytest) =="
(cd "$ROOT/core" && "$ROOT/.venv/bin/python" -m pytest)
echo "== desktop (typecheck + vitest) =="
(cd "$ROOT/desktop" && npx tsc --noEmit && npx vitest run)
echo "== shell (cargo check) =="
# tauri-build requires the bundled UI and a sidecar binary to exist. Build the UI and,
# if no real sidecar has been built yet, use an empty placeholder for the check only.
(cd "$ROOT/desktop" && npx vite build --logLevel error)
TRIPLE="$(rustc -vV | sed -n 's/^host: //p')"
EXT=""; [[ "$TRIPLE" == *windows* ]] && EXT=".exe"
SIDECAR="$ROOT/desktop/src-tauri/binaries/huntly-core-$TRIPLE$EXT"
if [[ ! -e "$SIDECAR" ]]; then
  mkdir -p "$(dirname "$SIDECAR")" && printf '#!/bin/sh\nexit 1\n' > "$SIDECAR" && chmod +x "$SIDECAR"
fi
(cd "$ROOT/desktop/src-tauri" && cargo check --quiet)
echo "All tests passed."
