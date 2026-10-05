#!/usr/bin/env bash
# 1.6.7: smoke test of the macOS app - start it with an empty data folder, check /api/health, the version, the web
# interface and the bundled license, then stop it.
#   bash packaging/macos/smoke_test.sh <path to Fundwarden.app or .dmg> <version> [port] [window|headless]
# "window" (default) starts it the way a double-click does (status window, server in a background thread);
# "headless" sets FM_NO_WINDOW=1.
set -euo pipefail
TARGET="$1"; VERSION="$2"; PORT="${3:-8793}"; HOW="${4:-window}"
DATA="$(mktemp -d)"; LOG="$DATA.log"; MNT=""
cleanup() {
  [ -n "${PID:-}" ] && kill "$PID" 2>/dev/null || true
  [ -n "$MNT" ] && hdiutil detach "$MNT" -quiet 2>/dev/null || true
}
trap cleanup EXIT
fail() { echo "::error::macOS smoke test failed: $*"; tail -40 "$LOG" 2>/dev/null || true; exit 1; }

if [[ "$TARGET" == *.dmg ]]; then
  MNT="$(mktemp -d)"
  hdiutil attach "$TARGET" -nobrowse -readonly -mountpoint "$MNT" >/dev/null
  [ -L "$MNT/Applications" ] || fail "the disk image has no Applications shortcut"
  [ -f "$MNT/Read me first.txt" ] || fail "the disk image has no 'Read me first.txt'"
  APP="$MNT/Fundwarden.app"
else
  APP="$TARGET"
fi
BIN="$APP/Contents/MacOS/Fundwarden"
[ -x "$BIN" ] || fail "$BIN not found"
codesign --verify --deep --strict "$APP" || fail "the app's signature does not verify"
file "$BIN" | grep -q arm64 || fail "the app is not arm64"
PLIST_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist")"
[ "$PLIST_VERSION" = "$VERSION" ] || fail "Info.plist says version '$PLIST_VERSION', expected '$VERSION'"

[ "$HOW" = "headless" ] && export FM_NO_WINDOW=1
"$BIN" --no-browser --port "$PORT" --data-dir "$DATA" >"$LOG" 2>&1 &
PID=$!
OK=""
for i in $(seq 1 120); do
  kill -0 "$PID" 2>/dev/null || fail "the app exited early"
  curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && { OK=1; break; }
  sleep 1
done
[ -n "$OK" ] || fail "no healthy answer on port $PORT within 120 s"
echo "healthy after $i s ($HOW)"
STATUS="$(curl -fs "http://127.0.0.1:$PORT/api/system/status")"; echo "$STATUS"
[[ "$STATUS" == *"\"version\":\"$VERSION\""* ]] || fail "reports the wrong version"
[[ "$STATUS" == *"\"mode\":\"local\""* ]] || fail "expected local mode by default"
curl -fs "http://127.0.0.1:$PORT/" | grep -q '<div id="root">' || fail "the web interface is missing"
curl -fs "http://127.0.0.1:$PORT/api/system/legal/license" | grep -q "GNU AFFERO GENERAL PUBLIC LICENSE" || fail "LICENSE is not bundled"
[ -d "$DATA/database" ] || fail "the data folder was not used"
kill "$PID"; for i in $(seq 1 20); do kill -0 "$PID" 2>/dev/null || break; sleep 0.5; done
kill -0 "$PID" 2>/dev/null && fail "the app did not stop"
PID=""
echo "SMOKE TEST PASSED: $TARGET ($HOW)"
