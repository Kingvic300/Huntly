#!/usr/bin/env bash
# Build Linux packages (.deb and AppImage) into release/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
"$ROOT/scripts/build-sidecar.sh"
cd "$ROOT/desktop"
npx tauri build --bundles deb,appimage
mkdir -p "$ROOT/release"
find src-tauri/target/release/bundle \( -name '*.deb' -o -name '*.AppImage' \) -exec cp {} "$ROOT/release/" \;
(cd "$ROOT/release" && sha256sum ./* > SHA256SUMS)
ls -lh "$ROOT/release"
