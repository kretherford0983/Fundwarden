#!/usr/bin/env bash
# Self-contained Linux x86-64 build (PyInstaller onedir). Run on Linux x86-64 from the repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
npm --prefix frontend ci
npm --prefix frontend run build
python3 -m venv build/venv-linux
build/venv-linux/bin/pip install --quiet -r backend/requirements.txt pyinstaller==6.22.3
build/venv-linux/bin/pyinstaller --noconfirm --log-level WARN --distpath dist --workpath build/pyinstaller packaging/pyinstaller/fmpoc.spec
tar -C dist -czf dist/PennyWarden-linux-x64.tar.gz pennywarden
echo "Built dist/PennyWarden-linux-x64.tar.gz  (run: ./pennywarden/pennywarden)"
