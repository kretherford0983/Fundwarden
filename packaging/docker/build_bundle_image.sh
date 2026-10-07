#!/usr/bin/env bash
# Alternative container build that needs NO registry access: packages the self-contained Linux bundle
# (dist/pennywarden from packaging/build_linux.sh) plus its shared-library closure into a minimal image.
# Used during POC verification where Docker Hub was unreachable.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
R="$(mktemp -d)"
mkdir -p "$R/app" "$R/data" "$R/tmp" "$R/etc" "$R/lib64"
cp -r "$ROOT/dist/pennywarden/." "$R/app/"
for f in $(find "$R/app" -type f \( -name "*.so*" -o -name pennywarden \) -exec ldd {} \; 2>/dev/null | grep -oE "/[^ ]+\.so[^ ]*" | sort -u); do
  mkdir -p "$R$(dirname "$f")"; cp -L "$f" "$R$f"
done
cp -L /lib64/ld-linux-x86-64.so.2 "$R/lib64/"
echo "app:x:10001:10001::/data:/sbin/nologin" > "$R/etc/passwd"; echo "app:x:10001:" > "$R/etc/group"
chown -R 10001:10001 "$R/data"; chmod 1777 "$R/tmp"
tar -C "$R" -c . | docker import -c 'USER 10001' -c 'ENV FM_DATA_DIR=/data FM_MODE=server FM_HOST=0.0.0.0 FM_PORT=8765' \
  -c 'EXPOSE 8765' -c 'VOLUME ["/data"]' -c 'ENTRYPOINT ["/app/pennywarden","--no-browser"]' - pennywarden:bundle
rm -rf "$R"
echo "Image pennywarden:bundle created. Run: docker run -d -p 8765:8765 -v pennywarden-data:/data pennywarden:bundle"
