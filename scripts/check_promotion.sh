#!/usr/bin/env bash
# Pull-request rules for the branch flow  feature/* -> develop -> test -> main   (hotfix/* -> main, then back-merged).
# dependabot/* (1.6.8): dependency update pull requests opened by Dependabot - into develop only.
# Usage: check_promotion.sh <base branch> <head branch>
set -euo pipefail
BASE="$1"; HEAD="$2"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fail() { echo "::error::$1"; exit 1; }
case "$BASE" in
  develop) [[ "$HEAD" =~ ^(feature|hotfix|dependabot)/ || "$HEAD" == "main" || "$HEAD" == "test" ]] \
             || fail "Only feature/*, hotfix/*, dependabot/* (or back-merges from test/main) may be merged into develop (got '$HEAD')." ;;
  test)    [[ "$HEAD" == "develop" || "$HEAD" =~ ^hotfix/ || "$HEAD" == "main" ]] \
             || fail "Only develop (or hotfix/*, or a back-merge from main) may be merged into test (got '$HEAD')." ;;
  main)    [[ "$HEAD" == "test" || "$HEAD" =~ ^hotfix/ ]] \
             || fail "Only test (or hotfix/*) may be merged into main (got '$HEAD')." ;;
  *) echo "No promotion rule for base '$BASE'."; exit 0 ;;
esac
VERSION=$(bash "$ROOT/scripts/version.sh")
bash "$ROOT/scripts/version.sh" --check
if [ "$BASE" = "main" ]; then
  git fetch --tags --quiet origin || true
  if git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null; then
    fail "v$VERSION is already released. Bump the version (backend/fmpoc/config.py + frontend/package.json) and add a CHANGELOG entry before merging into main."
  fi
  grep -q "^## $VERSION " "$ROOT/CHANGELOG.md" || fail "CHANGELOG.md has no '## $VERSION' section."
fi
echo "OK: $HEAD -> $BASE (version $VERSION)"
