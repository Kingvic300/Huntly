#!/usr/bin/env bash
# Build Linux packages (.deb and AppImage) into release/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
"$ROOT/scripts/build-sidecar.sh"
# Update packages are signed. Use the local key if present (see docs/RELEASING.md).
if [[ -z "${TAURI_SIGNING_PRIVATE_KEY:-}" && -f "$HOME/.tauri/huntly-updater.key" ]]; then
  export TAURI_SIGNING_PRIVATE_KEY="$(cat "$HOME/.tauri/huntly-updater.key")"
  export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="$(cat "$HOME/.tauri/huntly-updater.password" 2>/dev/null || true)"
fi
cd "$ROOT/desktop"
npx tauri build --bundles "${HUNTLY_BUNDLES:-deb,appimage}"
mkdir -p "$ROOT/release"
find src-tauri/target/release/bundle \( -name '*.deb' -o -name '*.AppImage' \) -exec cp {} "$ROOT/release/" \;
(cd "$ROOT/release" && sha256sum ./* > SHA256SUMS)
ls -lh "$ROOT/release"
