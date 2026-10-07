#!/usr/bin/env bash
# Assemble a self-contained Windows x86-64 distribution WITHOUT needing a Windows machine.
# Uses the relocatable CPython build from astral-sh/python-build-standalone plus official win_amd64 wheels.
# The result needs no separately installed Python, Node.js, SQLite, Docker or database server (BR-083).
#
# Usage (repo root):  bash packaging/build_windows_portable.sh      -> dist/PennyWarden-windows-x64.zip
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PBS_TAG="${PBS_TAG:-20251014}"
PYVER="${PYVER:-3.12.12}"
PYMINOR="312"
NAME="PennyWarden-windows-x64"
OUT="$ROOT/dist/$NAME"
CACHE="$ROOT/build/cache"
ARCHIVE="cpython-${PYVER}+${PBS_TAG}-x86_64-pc-windows-msvc-install_only.tar.gz"
URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${ARCHIVE}"

test -f "$ROOT/backend/fmpoc/static/index.html" || { echo "Build the frontend first: npm --prefix frontend ci && npm --prefix frontend run build"; exit 1; }
rm -rf "$OUT" "$ROOT/dist/$NAME.zip"
mkdir -p "$OUT/app" "$CACHE/wheels-win"

if [ ! -f "$CACHE/$ARCHIVE" ]; then
  curl -fsSL -o "$CACHE/$ARCHIVE.part" "$URL"
  mv "$CACHE/$ARCHIVE.part" "$CACHE/$ARCHIVE"
fi
if [ -n "${PBS_SHA256:-}" ]; then echo "$PBS_SHA256  $CACHE/$ARCHIVE" | sha256sum -c -; fi
tar -xzf "$CACHE/$ARCHIVE" -C "$OUT"          # -> $OUT/python/python.exe

python3 -m pip download --quiet --only-binary=:all: --platform win_amd64 --python-version "$PYMINOR" \
  --implementation cp --abi "cp$PYMINOR" --abi abi3 --abi none -r "$ROOT/backend/requirements.txt" colorama==0.4.6 -d "$CACHE/wheels-win"
# (colorama: Windows-only dependency of click/uvicorn that marker evaluation on the build host would skip)
SITE="$OUT/python/Lib/site-packages"
mkdir -p "$SITE"
python3 - "$CACHE/wheels-win" "$SITE" "$ROOT/backend/requirements.txt" <<'PY'
import re, sys, zipfile, pathlib
wheels, site, req = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
pins = {}
for line in open(req):
    m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", line.strip())
    if m:
        pins[m.group(1).lower().replace("-", "_")] = m.group(2)
used = set()
for w in sorted(wheels.glob("*.whl")):
    name, ver = w.name.split("-")[:2]
    key = name.lower().replace("-", "_")
    if key in pins and pins[key] != ver:
        continue
    if not ("win_amd64" in w.name or w.name.endswith("-none-any.whl")):
        raise SystemExit(f"unexpected wheel platform: {w.name}")
    zipfile.ZipFile(w).extractall(site)
    used.add(w.name)
print("installed wheels:\n  " + "\n  ".join(sorted(used)))
PY
# application code (no tests, no caches)
cp -r "$ROOT/backend/fmpoc" "$OUT/app/fmpoc"
cp "$ROOT/LICENSE" "$ROOT/THIRD-PARTY-NOTICES.txt" "$OUT/"   # v1.5.0: AGPL-3.0 + third-party notices
cat > "$OUT/app/launch.py" <<'PY'
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fmpoc.__main__ import main
sys.exit(main())
PY
find "$OUT" -name "__pycache__" -type d -prune -exec rm -rf {} +
cat > "$OUT/PennyWarden.cmd" <<'CMD'
@echo off
rem Local mode: binds to 127.0.0.1 and opens the default browser. Data: %LOCALAPPDATA%\PennyWarden
setlocal
set "HERE=%~dp0"
set PYTHONNOUSERSITE=1
set PYTHONDONTWRITEBYTECODE=1
"%HERE%python\python.exe" -I "%HERE%app\launch.py" %*
CMD
cat > "$OUT/PennyWarden-Server.cmd" <<'CMD'
@echo off
rem Server mode. Configure host/port in %LOCALAPPDATA%\PennyWarden\config.toml or FM_* variables.
rem Put an HTTPS reverse proxy in front for network use and set FM_SECURE_COOKIES=true.
setlocal
set "HERE=%~dp0"
set PYTHONNOUSERSITE=1
set PYTHONDONTWRITEBYTECODE=1
"%HERE%python\python.exe" -I "%HERE%app\launch.py" --mode server %*
CMD
sed -i 's/$/\r/' "$OUT"/*.cmd
cp "$ROOT/docs/deployment.md" "$OUT/README-DEPLOYMENT.md" 2>/dev/null || true
(cd "$ROOT/dist" && rm -f "$NAME.zip" && python3 -m zipfile -c "$NAME.zip" "$NAME" >/dev/null)
echo "Built $ROOT/dist/$NAME.zip"
