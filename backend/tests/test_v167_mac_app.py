"""1.6.7: macOS app - the server runs in a background thread behind a status window; packaging files are in place."""
import re
import socket
import time
from pathlib import Path

import pytest

from fmpoc import desktop
from fmpoc.__main__ import main
from fmpoc.app import create_app
from fmpoc.config import VERSION

ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait(fn, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.1)
    return False


def test_server_thread_starts_answers_and_stops(settings):
    port = free_port()
    srv = desktop.ServerThread(create_app(settings), host="127.0.0.1", port=port, access_log=False, log_config=None)
    assert not srv.started
    srv.start()
    url = f"http://127.0.0.1:{port}"
    assert wait(lambda: srv.started and desktop.healthy(url))
    srv.stop()
    assert not srv.alive and srv.error is None and not desktop.healthy(url)


def test_server_thread_reports_a_port_that_is_in_use(settings):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        srv = desktop.ServerThread(create_app(settings), host="127.0.0.1", port=s.getsockname()[1], access_log=False,
                                   log_config=None)
        srv.start()
        assert wait(lambda: not srv.alive) and not srv.started   # the window then says it could not start


def test_window_only_in_local_mode_and_can_be_switched_off(settings, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.delenv("FM_NO_WINDOW", raising=False)
    assert desktop.window_wanted(SimpleNamespace(mode="local"))
    assert not desktop.window_wanted(SimpleNamespace(mode="server"))
    monkeypatch.setenv("FM_NO_WINDOW", "1")
    assert not desktop.window_wanted(SimpleNamespace(mode="local"))


def test_main_hands_local_mode_to_the_window(tmp_path, monkeypatch):
    seen = {}

    def fake(app, settings, url, version, kwargs):
        seen.update(url=url, version=version, port=kwargs["port"], mode=settings.mode, browser=settings.open_browser)
        return 0

    monkeypatch.delenv("FM_NO_WINDOW", raising=False)
    monkeypatch.setattr(desktop, "run_with_window", fake)
    assert main(["--port", "8799", "--data-dir", str(tmp_path), "--no-browser"], window=True) == 0
    assert seen == {"url": "http://127.0.0.1:8799", "version": VERSION, "port": 8799, "mode": "local", "browser": False}


def test_packaging_files():
    spec = (ROOT / "packaging/pyinstaller/fundwarden-mac.spec").read_text()
    assert 'target_arch="arm64"' in spec and "console=False" in spec and "BUNDLE(" in spec and "entry_mac.py" in spec
    assert (ROOT / "packaging/macos/fundwarden.icns").read_bytes()[:4] == b"icns"
    build = (ROOT / "packaging/build_macos.sh").read_text()
    assert "codesign --force --deep --sign -" in build and "hdiutil create" in build and "macos-arm64.dmg" in build
    assert "Open Anyway" in (ROOT / "packaging/macos/READ-ME-FIRST.txt").read_text()
    wf = (ROOT / ".github/workflows/build.yml").read_text()
    assert re.search(r"macos-app:.*runs-on: macos-15", wf, re.S) and "needs: [package, windows-exe, macos-app]" in wf
    assert wf.count("macos-arm64.dmg") >= 4      # built, smoke-tested, uploaded, named in the release notes
