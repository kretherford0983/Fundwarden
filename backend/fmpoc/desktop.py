"""1.6.7: desktop window for the macOS app (PennyWarden.app).

A Mac app has no console window to show the address or to close, so the app shows a small window instead:
the address, a button that opens the browser, and Quit. Closing the window (or Quit in the menu / Dock) stops
PennyWarden. The web server runs in a background thread; the window owns the main thread, as macOS requires.

Only the standard library is used (tkinter). When no window can be created - no display, tkinter missing, or
FM_NO_WINDOW=1 - the server simply runs in the foreground like on Windows and Linux.
"""
from __future__ import annotations

import os
import threading
import urllib.request
import webbrowser


class ServerThread:
    """uvicorn in a background thread, stoppable from the window."""

    def __init__(self, app, **uvicorn_kwargs):
        import uvicorn

        self.server = uvicorn.Server(uvicorn.Config(app, **uvicorn_kwargs))
        self.error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, name="pennywarden-server", daemon=True)

    def _run(self) -> None:
        try:
            self.server.run()
        except BaseException as exc:  # noqa: BLE001 - shown in the window (e.g. the port is already in use)
            self.error = exc

    def start(self) -> None:
        self._thread.start()

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    @property
    def started(self) -> bool:
        return bool(getattr(self.server, "started", False))

    def stop(self, timeout: float = 10) -> None:
        self.server.should_exit = True
        self._thread.join(timeout)


def healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=1) as r:  # noqa: S310 - fixed loopback URL
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def window_wanted(settings) -> bool:
    return settings.mode == "local" and os.environ.get("FM_NO_WINDOW", "") not in ("1", "true", "yes")


def run_with_window(app, settings, url: str, version: str, uvicorn_kwargs: dict) -> int:
    """Runs the server behind a small status window. Falls back to a plain foreground server without a display."""
    try:
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
    except Exception:  # noqa: BLE001 - ImportError, TclError (no display)
        import uvicorn

        uvicorn.run(app, **uvicorn_kwargs)
        return 0

    srv = ServerThread(app, **uvicorn_kwargs)
    state = {"opened": False, "closing": False}
    root.title("PennyWarden")
    root.resizable(False, False)
    box = ttk.Frame(root, padding=22)
    box.grid()
    ttk.Label(box, text=f"PennyWarden {version}", font=("TkDefaultFont", 16, "bold")).grid(sticky="w")
    status = ttk.Label(box, text="Starting…")
    status.grid(sticky="w", pady=(10, 0))
    ttk.Label(box, text=f"Your data: {settings.data_dir}", foreground="#555555", wraplength=420,
              justify="left").grid(sticky="w", pady=(4, 0))
    buttons = ttk.Frame(box)
    buttons.grid(sticky="w", pady=(16, 0))
    ttk.Label(box, text="Closing this window stops PennyWarden. Your data stays on this Mac.",
              foreground="#555555").grid(sticky="w", pady=(14, 0))

    def open_browser(*_):
        if srv.started:
            webbrowser.open(url)

    def quit_app(*_):
        if state["closing"]:
            return
        state["closing"] = True
        status.configure(text="Stopping…")
        root.update_idletasks()
        srv.stop()
        root.destroy()

    open_btn = ttk.Button(buttons, text="Open PennyWarden", command=open_browser, state="disabled", default="active")
    open_btn.grid(row=0, column=0)
    ttk.Button(buttons, text="Quit", command=quit_app).grid(row=0, column=1, padx=(10, 0))
    root.protocol("WM_DELETE_WINDOW", quit_app)
    for name, fn in (("::tk::mac::Quit", quit_app), ("::tk::mac::ReopenApplication", open_browser)):
        try:  # macOS only: Quit from the menu / Dock, and a click on the Dock icon while running
            root.createcommand(name, fn)
        except Exception:  # noqa: BLE001
            pass

    def poll():
        if state["closing"]:
            return
        if not srv.alive:
            reason = str(srv.error) if srv.error else f"is port {settings.port} already in use?"
            status.configure(text=f"PennyWarden could not start ({reason}).", foreground="#b3261e", wraplength=420)
            open_btn.configure(state="disabled")
            return
        if srv.started and healthy(url):
            status.configure(text=f"Running at {url}")
            open_btn.configure(state="normal")
            if not state["opened"]:
                state["opened"] = True
                if settings.open_browser:
                    webbrowser.open(url)
            root.after(3000, poll)
        else:
            root.after(250, poll)

    srv.start()
    root.after(200, poll)
    root.mainloop()
    if srv.alive:
        srv.stop()
    return 0
