"""v1.5.0 CR-027: packaging/linux/install.sh against a local fake GitHub (API + release downloads).

The release's install-server.sh is replaced by a stub that records its arguments, so the test needs neither root
nor systemd (the real install path is covered by the upgrade simulation in docs/upgrade.md).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "packaging" / "linux" / "install.sh"
PKG = "PennyWarden-linux-x64-portable.tar.gz"

pytestmark = pytest.mark.skipif(not (shutil.which("bash") and shutil.which("curl") and shutil.which("sha256sum")),
                                reason="needs bash, curl and sha256sum")


def _release_json(tag: str, prerelease: bool, draft: bool = False) -> dict:
    # key order and nesting like the real API (the installer reads the pretty-printed form)
    return {"url": "x", "id": 1, "author": {"login": "k", "id": 2}, "node_id": "n", "tag_name": tag,
            "target_commitish": "test", "name": tag, "draft": draft, "immutable": False, "prerelease": prerelease,
            "assets": [{"name": PKG, "uploader": {"login": "github-actions[bot]"}}], "body": "notes"}


def _tarball() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        data = b"#!/bin/sh\necho fake\n"
        info = tarfile.TarInfo("PennyWarden-linux-x64/pennywarden")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


STUB = b"""#!/usr/bin/env bash
printf '%s\\n' "$@" > "$PENNYWARDEN_TEST_RECORD"
"""


class Fake:
    def __init__(self):
        self.releases: list[dict] = []
        self.latest: dict | None = None
        self.files: dict[str, bytes] = {}
        self.requests: list[str] = []
        self.compact = False  # 1.6.7: GitHub answers on one line unless the client looks like curl

    def dump(self, obj) -> bytes:
        return (json.dumps(obj, separators=(",", ":")) if self.compact else json.dumps(obj, indent=2)).encode()

    def add_release(self, tag: str, prerelease: bool, *, draft=False, corrupt=False, html=False, sums_skip=()):
        tb, stub = _tarball(), STUB
        sums = "".join(f"{hashlib.sha256(b).hexdigest()}  {n}\n" for n, b in ((PKG, tb), ("install-server.sh", stub))
                       if n not in sums_skip)
        if corrupt:
            tb = tb[:-1] + bytes([tb[-1] ^ 1])
        if html:
            tb = b"<!DOCTYPE html><html><body>Not Found</body></html>"
        self.files.update({f"/dl/{tag}/{PKG}": tb, f"/dl/{tag}/install-server.sh": stub,
                           f"/dl/{tag}/SHA256SUMS.txt": sums.encode()})
        rel = _release_json(tag, prerelease, draft)
        self.releases.insert(0, rel)  # newest first, like the API
        if not prerelease and not draft:
            self.latest = rel


@pytest.fixture()
def gh():
    fake = Fake()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            fake.requests.append(self.path)
            path = self.path.split("?")[0]
            if path == "/api/releases":
                return self._send(200, fake.dump(fake.releases))
            if path == "/api/releases/latest":
                if fake.latest is None:
                    return self._send(404, b'{\n  "message": "Not Found"\n}')
                return self._send(200, fake.dump(fake.latest))
            if path in fake.files:
                return self._send(200, fake.files[path])
            self._send(404, b"Not Found")

        def _send(self, code, body):
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    fake.base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield fake
    srv.shutdown()


def run(gh, tmp_path, *args, config: str | None = None):
    rec = tmp_path / "args.txt"
    cfg = tmp_path / "config.toml"
    if config is not None:
        cfg.write_text(config)
    env = {**os.environ, "PENNYWARDEN_API": gh.base + "/api", "PENNYWARDEN_DOWNLOAD": gh.base + "/dl",
           "PENNYWARDEN_TEST_NONROOT": "1", "PENNYWARDEN_TEST_RECORD": str(rec), "PENNYWARDEN_CONFIG": str(cfg)}
    # piped into bash exactly like `curl … | sudo bash -s -- …`
    p = subprocess.run(["bash", "-s", "--", "--yes", *args], input=SCRIPT.read_bytes(), env=env,
                       capture_output=True, timeout=60)
    out = (p.stdout + p.stderr).decode()
    recorded = rec.read_text().split("\n")[:-1] if rec.exists() else None
    return p.returncode, out, recorded


def test_auto_uses_newest_test_prerelease_while_in_beta(gh, tmp_path):
    gh.add_release("v1.4.1-test.10", True)
    gh.add_release("v1.5.0-test.12", True, draft=True)  # drafts are ignored
    gh.add_release("v1.5.0-test.11", True)
    code, out, args = run(gh, tmp_path)
    assert code == 0, out
    assert "PennyWarden v1.5.0-test.11" in out and "TEST pre-release" in out
    assert args is not None and args[0].endswith(PKG) and len(args) == 1


def test_auto_prefers_production_from_1_5_0(gh, tmp_path):
    gh.add_release("v1.5.0", False)
    gh.add_release("v1.6.0-test.3", True)
    code, out, args = run(gh, tmp_path, "--port", "9001")
    assert code == 0, out
    assert "PennyWarden v1.5.0 " in out and "TEST" not in out
    assert args[1:] == ["--port", "9001"]


def test_auto_ignores_production_older_than_the_installer(gh, tmp_path):
    gh.add_release("v1.2.1", False)
    gh.add_release("v1.5.0-test.2", True)
    code, out, _ = run(gh, tmp_path)
    assert code == 0 and "PennyWarden v1.5.0-test.2" in out


def test_channels_and_pinned_version(gh, tmp_path):
    gh.add_release("v1.5.0-test.2", True)
    code, out, _ = run(gh, tmp_path, "--channel", "production")
    assert code != 0 and "no production release" in out
    code, out, _ = run(gh, tmp_path, "--channel", "test")
    assert code == 0 and "v1.5.0-test.2" in out
    gh.add_release("v1.5.0-test.3", True)
    code, out, _ = run(gh, tmp_path, "--version", "v1.5.0-test.2")
    assert code == 0 and "PennyWarden v1.5.0-test.2" in out
    assert not any(r.startswith("/api") for r in gh.requests[-3:])  # pinned: no API lookup
    assert run(gh, tmp_path, "--version", "1.5;rm -rf /")[0] != 0
    assert run(gh, tmp_path, "--port", "http")[0] != 0
    assert run(gh, tmp_path, "--channel", "nightly")[0] != 0


@pytest.mark.parametrize("kind,msg", [({"corrupt": True}, "checksum mismatch"),
                                      ({"html": True}, "web page instead of a file"),
                                      ({"sums_skip": ("install-server.sh",)}, "not listed in SHA256SUMS")])
def test_bad_downloads_are_refused(gh, tmp_path, kind, msg):
    gh.add_release("v1.5.0-test.9", True, **kind)
    code, out, args = run(gh, tmp_path)
    assert code != 0 and msg in out, out
    assert args is None  # install-server.sh never ran


def test_requires_root(gh, tmp_path):
    if os.geteuid() == 0:
        pytest.skip("running as root")
    gh.add_release("v1.5.0-test.9", True)
    env = {**os.environ, "PENNYWARDEN_API": gh.base + "/api", "PENNYWARDEN_DOWNLOAD": gh.base + "/dl"}
    p = subprocess.run(["bash", "-s", "--", "--yes"], input=SCRIPT.read_bytes(), env=env, capture_output=True)
    assert p.returncode != 0 and b"run as root" in p.stderr


def test_upgrade_health_checks_the_existing_port(gh, tmp_path):
    gh.add_release("v1.5.0-test.9", True)
    code, out, args = run(gh, tmp_path, config='[server]\nmode = "server"\nport = 8899   # mine\n')
    assert code == 0, out
    assert args[1:] == ["--port", "8899"]
    code, out, args = run(gh, tmp_path, "--port", "9000", config="[server]\nport = 8899\n")
    assert args[1:] == ["--port", "9000"]  # explicit wins


@pytest.mark.parametrize("compact", [False, True])
def test_release_lookup_understands_both_api_formats(gh, tmp_path, compact):
    """1.6.7: against the real GitHub the answer came on ONE line and 'latest' found nothing ("no release found")."""
    gh.compact = compact
    gh.add_release("v1.6.5-test.27", True)
    gh.add_release("v1.6.6-test.31", True)
    gh.releases[0]["body"] = 'notes that mention "tag_name": "v9.9.9" and "prerelease": false'
    code, out, recorded = run(gh, tmp_path, "--channel", "test")
    assert code == 0 and "PennyWarden v1.6.6-test.31" in out, out
    code, out, _ = run(gh, tmp_path)   # auto: no production release yet -> newest test pre-release
    assert code == 0 and "v1.6.6-test.31" in out and "TEST pre-release" in out, out
    gh.add_release("v1.6.6", False)
    gh.add_release("v1.6.7-test.40", True)
    code, out, recorded = run(gh, tmp_path)   # auto: the production release wins over a newer test build
    assert code == 0 and "PennyWarden v1.6.6 " in out and "TEST" not in out, out
    assert recorded[0].endswith(PKG)
    code, out, _ = run(gh, tmp_path, "--channel", "test")
    assert code == 0 and "v1.6.7-test.40" in out, out
