#!/usr/bin/env bash
# macOS app for Apple Silicon (1.6.7): dist/PennyWarden.app and dist/PennyWarden-<version>-macos-arm64.dmg.
# Run ON a Mac with Apple Silicon from the repo root, with Python 3.12 (including Tk) and Node.js 22 on the BUILD
# machine only; the app itself needs nothing installed. CI: job "macos-app" in .github/workflows/build.yml.
#
# The app is signed "ad hoc" (no Apple Developer ID, not notarized): required for arm64 code to run at all, and
# enough when macOS is told once to open it (System Settings -> Privacy & Security -> Open Anyway). See
# docs/deployment.md. To sign with a Developer ID later, set FM_CODESIGN_IDENTITY (and notarize the .dmg).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[ "$(uname -s)" = "Darwin" ] || { echo "build_macos.sh must run on macOS" >&2; exit 1; }
[ "$(uname -m)" = "arm64" ] || { echo "build_macos.sh must run on Apple Silicon (arm64)" >&2; exit 1; }
PY="${FM_PYTHON:-python3}"
VERSION="$(bash scripts/version.sh)"
IDENTITY="${FM_CODESIGN_IDENTITY:--}"          # "-" = ad hoc
DMG="dist/PennyWarden-${VERSION}-macos-arm64.dmg"

test -f backend/fmpoc/static/index.html || { echo "Build the frontend first: npm --prefix frontend ci && npm --prefix frontend run build" >&2; exit 1; }
"$PY" -c "import tkinter" || { echo "This Python has no Tk (tkinter); the app's window needs it." >&2; exit 1; }
"$PY" -m pip install --quiet -r backend/requirements.txt pyinstaller==6.22.3
rm -rf dist/PennyWarden dist/PennyWarden.app build/pyinstaller-mac build/dmg "$DMG"
FM_VERSION="$VERSION" "$PY" -m PyInstaller --noconfirm --log-level WARN --distpath dist \
  --workpath build/pyinstaller-mac packaging/pyinstaller/pennywarden-mac.spec
rm -rf dist/PennyWarden                           # the loose folder; the app bundle holds its own copy

if [ "$IDENTITY" = "-" ]; then
  codesign --force --deep --sign - dist/PennyWarden.app
else
  codesign --force --deep --options runtime --timestamp --sign "$IDENTITY" dist/PennyWarden.app
fi
codesign --verify --deep --strict dist/PennyWarden.app
file dist/PennyWarden.app/Contents/MacOS/PennyWarden | grep -q arm64 || { echo "the app is not arm64" >&2; exit 1; }

mkdir -p build/dmg
cp -R dist/PennyWarden.app build/dmg/
ln -s /Applications build/dmg/Applications
cp packaging/macos/READ-ME-FIRST.txt "build/dmg/Read me first.txt"
hdiutil create -volname "PennyWarden ${VERSION}" -srcfolder build/dmg -ov -format UDZO "$DMG" >/dev/null
echo "Built $DMG"
