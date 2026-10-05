"""Launcher for local and server modes (docs/06 §7).

    fmpoc [--mode local|server] [--host HOST] [--port PORT] [--data-dir DIR] [--no-browser]

Local mode binds to 127.0.0.1, applies migrations, waits for /api/health and opens the default browser.
Server mode binds to the configured interface; plain-HTTP network exposure logs a prominent warning.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
import urllib.request
import webbrowser

from .config import VERSION, is_loopback, load_settings


def _open_browser_when_ready(url: str) -> None:
    for _ in range(120):
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1) as r:  # noqa: S310 - fixed loopback URL
                if r.status == 200:
                    webbrowser.open(url)
                    return
        except Exception:
            time.sleep(0.25)


def reset_mfa_cli(argv: list[str]) -> int:
    """v1.4.1 CR-018: host-side MFA reset for a locked-out user (e.g. the only Administrator).

        fundwarden reset-mfa --user NAME [--reason TEXT] [--data-dir DIR]

    Run it as the account that owns the data directory (on the Linux server: sudo -u fundwarden ...). The user sets MFA
    up again at the next sign-in. Recorded in the audit log as MFA_RESET via "host_cli".
    """
    p = argparse.ArgumentParser(prog="fundwarden reset-mfa", description="Reset a user's two-step verification")
    p.add_argument("--user", required=True, help="username")
    p.add_argument("--reason", default="Reset from the server command line")
    p.add_argument("--data-dir")
    a = p.parse_args(argv)
    from sqlalchemy import select

    from .db import make_engine, make_session_factory, upgrade_database
    from .models import User
    from .services import mfa

    settings = load_settings({"data_dir": a.data_dir})
    if not settings.database_path.is_file():
        print(f"No database found in {settings.data_dir}", file=sys.stderr)
        return 2
    upgrade_database(settings.database_url)
    factory = make_session_factory(make_engine(settings.database_url))
    with factory() as db:
        user = db.scalar(select(User).where(User.username_normalized == a.user.strip().lower()))
        if user is None:
            print(f"User '{a.user}' not found.", file=sys.stderr)
            return 1

        from types import SimpleNamespace
        host_ctx = SimpleNamespace(workspace_id=user.workspace_id, user=None, correlation_id="host-cli", ip=None)
        mfa.reset(db, host_ctx, user, a.reason, via="host_cli")  # audit context: host action, no signed-in user
        db.commit()
    print(f"Two-step verification for '{user.username}' was reset. They will set it up again at the next sign-in.")
    return 0


def main(argv: list[str] | None = None, window: bool = False) -> int:
    """window=True (1.6.7, the macOS app): local mode runs behind a small status window instead of a console."""
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "reset-mfa":
        return reset_mfa_cli(argv[1:])
    p = argparse.ArgumentParser(prog="fundwarden", description="Fundwarden")
    p.add_argument("--mode", choices=["local", "server"])
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--data-dir")
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--version", action="store_true")
    a = p.parse_args(argv)
    if a.version:
        print(VERSION)
        return 0
    overrides = {"mode": a.mode, "host": a.host, "port": a.port, "data_dir": a.data_dir}
    if a.no_browser:
        overrides["open_browser"] = False
    settings = load_settings(overrides)
    if settings.mode == "local" and not is_loopback(settings.host):
        print("WARNING: local mode is intended for loopback only; binding to", settings.host, file=sys.stderr)
    if settings.mode == "server" and not is_loopback(settings.host) and settings.secure_cookies != "true":
        print("\n" + "!" * 78 + "\n SECURITY WARNING: serving on a network interface over plain HTTP.\n"
              " This is NOT secure for authenticated use. Place the application behind an HTTPS reverse\n"
              " proxy (Caddy/nginx/Apache) and set FM_SECURE_COOKIES=true.\n" + "!" * 78 + "\n", file=sys.stderr)

    import uvicorn

    from .app import create_app

    app = create_app(settings)
    url = f"http://{'127.0.0.1' if settings.host in ('0.0.0.0', '::') else settings.host}:{settings.port}"
    print(f"Fundwarden {VERSION} - {settings.mode} mode - {url}")
    print(f"Application data: {settings.data_dir}")
    trusted = settings.trusted_proxies.strip()
    kwargs = dict(host=settings.host, port=settings.port, access_log=False, server_header=False,
                  proxy_headers=bool(trusted), forwarded_allow_ips=trusted or None, log_config=None)
    if window:
        from . import desktop

        if desktop.window_wanted(settings):
            return desktop.run_with_window(app, settings, url, VERSION, kwargs)  # opens the browser itself
    if settings.mode == "local" and settings.open_browser:
        threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(app, **kwargs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
