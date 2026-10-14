#!/usr/bin/env bash
# Run every automated test. External services are mocked; no real email is ever sent.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "== core (pytest) =="
(cd "$ROOT/core" && "$ROOT/.venv/bin/python" -m pytest)
echo "== desktop (typecheck + vitest) =="
(cd "$ROOT/desktop" && npx tsc --noEmit && npx vitest run)
echo "== shell (cargo check) =="
(cd "$ROOT/desktop/src-tauri" && cargo check --quiet)
echo "All tests passed."
