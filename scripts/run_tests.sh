#!/usr/bin/env bash
# Full verification: backend tests, frontend typecheck/build, E2E UI tests (optionally against a packaged build).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend" && python -m pytest -p no:warnings
cd "$ROOT/frontend" && npx tsc --noEmit -p . && npm run build
FM_PYTHON="$(command -v python)" npx playwright test   # set FM_BUNDLE=/path/to/pennywarden to test a package
