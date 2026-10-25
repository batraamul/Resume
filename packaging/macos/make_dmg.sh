#!/bin/bash
# Build the macOS disk image from the PyInstaller .app bundle.
#   packaging/macos/make_dmg.sh 1.1.0 arm64
set -euo pipefail
VERSION="${1:?version}"
ARCH="${2:-arm64}"
APP="dist/Resume Intelligence Studio.app"
STAGE="build/dmg"
OUT="dist/installer/ResumeIntelligenceStudio-${VERSION}-macos-${ARCH}.dmg"
[ -d "$APP" ] || { echo "Missing $APP — run PyInstaller first." >&2; exit 1; }
rm -rf "$STAGE"
mkdir -p "$STAGE" dist/installer
ditto "$APP" "$STAGE/Resume Intelligence Studio.app"
ln -s /Applications "$STAGE/Applications"
cp packaging/macos/README-FIRST.txt "$STAGE/Read me first.txt"
hdiutil create -volname "Resume Intelligence Studio ${VERSION}" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
echo "Built $OUT"
