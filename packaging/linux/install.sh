#!/usr/bin/env bash
# Fundwarden one-command install / upgrade for Linux servers (v1.5.0 CR-027; renamed from Freedger in 1.6.6).
#
#   curl -fsSL https://github.com/kretherford0983/Fundwarden/releases/latest/download/install.sh | sudo bash
#   curl -fsSL https://github.com/kretherford0983/Fundwarden/releases/download/<tag>/install.sh | sudo bash -s -- --version <tag>
#
# Options:
#   --channel auto|production|test   which releases to pick from (default: auto)
#                                      auto       = newest production release that has this installer (1.5.0 or
#                                                   later); while there is none (beta), the newest test pre-release
#                                      production = newest production release only
#                                      test       = newest test pre-release
#   --version <tag>                  install exactly this release (e.g. v1.5.0 or v1.5.0-test.42)
#   --port <n>                       port of the app (default: the port in an existing /var/lib/fundwarden/config.toml,
#                                    else 8765). A new installation writes it to config.toml; an upgrade only uses
#                                    it for the health check - an existing config.toml is never changed.
#   --yes                            do not wait 5 seconds before installing
#
# What it does: finds the release (public GitHub API, no token), downloads the Linux package, install-server.sh and
# SHA256SUMS.txt from that release, verifies both checksums and runs that release's install-server.sh. Everything
# install-server.sh does is unchanged: data snapshot before an upgrade, previous release kept for rollback,
# config.toml / secrets / database / attachments left in place, health check.
#
# Prefer to read it first?  curl -fsSLO <url>/install.sh ; less install.sh ; sudo bash install.sh
set -euo pipefail

main() {
  local REPO="${FUNDWARDEN_REPO:-kretherford0983/Fundwarden}"
  local API="${FUNDWARDEN_API:-https://api.github.com/repos/$REPO}"
  local DL="${FUNDWARDEN_DOWNLOAD:-https://github.com/$REPO/releases/download}"
  local MIN_PRODUCTION="1.5.0"   # first production version that ships this installer
  local PKG="Fundwarden-linux-x64-portable.tar.gz"
  local OLD_PKG="FinancialManagementPOC-linux-x64-portable.tar.gz"   # package name before 1.6.6
  local CHANNEL=auto TAG="" PORT="" YES=0

  while [ $# -gt 0 ]; do
    case "$1" in
      --channel) CHANNEL="${2:-}"; shift 2 ;;
      --version) TAG="${2:-}"; shift 2 ;;
      --port) PORT="${2:-}"; shift 2 ;;
      --yes|-y) YES=1; shift ;;
      -h|--help) echo "see the comments at the top of install.sh, or docs/deployment.md"; return 0 ;;
      *) die "unknown option: $1 (see --help)" ;;
    esac
  done
  case "$CHANNEL" in auto|production|test) ;; *) die "--channel must be auto, production or test" ;; esac
  if [ -n "$PORT" ]; then [[ "$PORT" =~ ^[0-9]+$ ]] && [ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] || die "invalid --port"; fi
  if [ -n "$TAG" ]; then [[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-test\.[0-9]+)?$ ]] || die "invalid --version (expected vX.Y.Z or vX.Y.Z-test.N)"; fi

  # (FUNDWARDEN_TEST_NONROOT=1 is used only by the automated tests, which replace install-server.sh)
  [ "$(id -u)" = 0 ] || [ "${FUNDWARDEN_TEST_NONROOT:-}" = 1 ] || die "run as root, e.g.  curl -fsSL <url>/install.sh | sudo bash"
  for c in curl tar gzip sha256sum sort; do command -v "$c" >/dev/null || die "'$c' is required"; done

  if [ -z "$TAG" ]; then
    case "$CHANNEL" in
      production) TAG="$(latest_production)" || die "no production release found" ;;
      test) TAG="$(latest_test)" || die "no test pre-release found" ;;
      auto)
        TAG="$(latest_production || true)"
        if [ -z "$TAG" ] || ! version_ge "$(plain "$TAG")" "$MIN_PRODUCTION"; then
          TAG="$(latest_test)" || die "no release found"
          note "No production release with the one-command installer yet."
          note "Installing the newest TEST pre-release $TAG. Use --channel production to refuse this."
        fi ;;
    esac
  fi
  local CFG="${FUNDWARDEN_CONFIG:-/var/lib/fundwarden/config.toml}"
  [ -f "$CFG" ] || [ -n "${FUNDWARDEN_CONFIG:-}" ] || CFG=/var/lib/fmpoc/config.toml   # installation from before 1.6.6
  if [ -z "$PORT" ] && [ -f "$CFG" ]; then  # upgrade: health-check the port the installation already uses
    PORT="$(sed -n 's/^[[:space:]]*port[[:space:]]*=[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$CFG" | head -1)"
  fi
  echo "==> Fundwarden $TAG from github.com/$REPO"
  if [ "$YES" = 0 ]; then echo "    installing in 5 seconds (Ctrl+C to cancel)"; sleep 5; fi

  WORK="$(mktemp -d)"; trap 'rm -rf "${WORK:-}"' EXIT
  fetch "$DL/$TAG/SHA256SUMS.txt" "$WORK/SHA256SUMS.txt"
  if ! grep -qE "^[0-9a-f]{64}  \*?$PKG\$" "$WORK/SHA256SUMS.txt" && grep -qE "^[0-9a-f]{64}  \*?$OLD_PKG\$" "$WORK/SHA256SUMS.txt"; then
    PKG="$OLD_PKG"; note "$TAG is from before the rename to Fundwarden (1.6.6): it installs under the old name (service fmpoc)."
  fi
  fetch "$DL/$TAG/$PKG" "$WORK/$PKG"
  fetch "$DL/$TAG/install-server.sh" "$WORK/install-server.sh"
  echo "==> verifying checksums"
  (cd "$WORK" && for f in "$PKG" install-server.sh; do
     grep -E "^[0-9a-f]{64}  \*?$f\$" SHA256SUMS.txt > "$f.sum" || die "$f is not listed in SHA256SUMS.txt"
     sha256sum -c --quiet "$f.sum" || die "checksum mismatch for $f - download refused"
   done)
  gzip -t "$WORK/$PKG" 2>/dev/null || die "the package is not a valid .tar.gz"

  echo "==> running install-server.sh from $TAG"
  if [ -n "$PORT" ]; then bash "$WORK/install-server.sh" "$WORK/$PKG" --port "$PORT"
  else bash "$WORK/install-server.sh" "$WORK/$PKG"; fi
  echo "==> Fundwarden $TAG installed"
}

die() { echo "install.sh: $*" >&2; exit 1; }
note() { echo "NOTE: $*" >&2; }
plain() { local v="${1#v}"; echo "${v%%-*}"; }
version_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]; }

api() {  # GET a GitHub API path, print the body; non-2xx -> failure
  curl -fsSL --retry 3 -H "Accept: application/vnd.github+json" -H "User-Agent: fundwarden-install" "$API/$1"
}

# The API answers pretty-printed or on one line depending on the client (1.6.7: the one-line form was not understood,
# so "latest" found nothing). Reduce either form to one line per field: tag_name / draft / prerelease, in API order.
fields() { grep -oE '"(tag_name|draft|prerelease)": *("[^"]*"|true|false)' | sed -E 's/^"([a-z_]+)": *"?([^"]*)"?$/\1 \2/'; }

latest_production() {  # releases/latest never returns pre-releases or drafts
  local t; t="$(api releases/latest 2>/dev/null | fields | awk '$1 == "tag_name" { print $2; exit }')"
  [[ "$t" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] && echo "$t"
}

latest_test() {  # newest published pre-release named v*-test.N (the API lists newest first)
  local t
  t="$(api "releases?per_page=30" | fields | awk '
    $1 == "tag_name" { tag = $2; draft = "" }
    $1 == "draft" { draft = $2 }
    $1 == "prerelease" { if ($2 == "true" && draft == "false" && tag ~ /^v[0-9]+\.[0-9]+\.[0-9]+-test\.[0-9]+$/) { print tag; exit } }')"
  [ -n "$t" ] && echo "$t"
}

fetch() {  # download, refusing empty files and HTML error pages
  curl -fsSL --retry 3 -o "$2" "$1" || die "download failed: $1"
  [ -s "$2" ] || die "empty download: $1"
  if head -c 512 "$2" | grep -qi '<!doctype html\|<html'; then die "got a web page instead of a file: $1"; fi
}

main "$@"
