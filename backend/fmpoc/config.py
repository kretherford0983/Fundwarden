"""Application configuration.

Precedence (docs/06 §11): built-in defaults < config file (APP_DATA_DIR/config.toml) < environment variables.
Secrets are never stored in the general configuration file; the portable encryption key lives in
APP_DATA_DIR/secrets/.
"""
from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

APP_NAME = "Fundwarden"
LEGACY_APP_NAME = "FinancialManagementPOC"  # name of the default data folder before 1.6.6
VERSION = "1.6.7"


BUILD_INFO_FILE = Path(__file__).with_name("build_info.json")


def build_info() -> dict | None:
    """v1.4 CR-022: CI writes build_info.json into packaged builds (channel/branch, run number, commit)."""
    import json
    try:
        data = json.loads(BUILD_INFO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    keep = ("version", "branch", "commit", "run", "built_at")
    return {k: str(data[k])[:64] for k in keep if data.get(k) not in (None, "")}


def _default_data_dir(name: str, unix_name: str) -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / name
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / name
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / unix_name


def default_data_dir() -> Path:
    """OS-appropriate default application-data directory (separate from binaries, BR-086)."""
    return _default_data_dir(APP_NAME, "fundwarden")


def legacy_default_data_dir() -> Path:
    """Default data directory used before the 1.6.6 rename (Financial Management POC / Freedger)."""
    return _default_data_dir(LEGACY_APP_NAME, "financial-management-poc")


def adopt_legacy_data_dir(new: Path, old: Path) -> Path:
    """1.6.6 rename: a local installation that still has its data in the old default folder keeps it - the folder
    is renamed once (same parent folder, nothing is copied or rewritten). If that is not possible (e.g. the folder is
    in use), the old folder is used where it is. Never called when the data directory was chosen explicitly."""
    if new.exists() or not old.is_dir():
        return new
    try:
        old.rename(new)
    except OSError as e:
        print(f"NOTE: using the existing data folder {old} (it could not be renamed to {new}: {e})", file=sys.stderr)
        return old
    print(f"Data folder renamed: {old} -> {new}", file=sys.stderr)
    return new


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=default_data_dir)
    mode: str = "local"  # local | server
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True
    # Cookie "Secure" flag: auto = enabled when the request arrived over HTTPS
    secure_cookies: str = "auto"  # auto | true | false
    hsts: bool = False
    # Comma separated list of proxy IPs whose X-Forwarded-* headers are trusted ("" = none)
    trusted_proxies: str = ""
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    login_max_failures: int = 5
    login_lockout_seconds: int = 900
    restore_max_mb: int = 20480  # v1.4.1 CR-024/025: largest backup file accepted for a restore
    log_level: str = "INFO"
    debug: bool = False  # never enabled in packaged builds
    frontend_dir: Path | None = None

    @property
    def database_dir(self) -> Path:
        return self.data_dir / "database"

    @property
    def database_path(self) -> Path:
        return self.database_dir / "fmpoc.sqlite3"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path.as_posix()}"

    @property
    def attachments_dir(self) -> Path:
        return self.data_dir / "attachments"

    @property
    def secrets_dir(self) -> Path:
        return self.data_dir / "secrets"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.database_dir, self.attachments_dir, self.secrets_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.secrets_dir, 0o700)
        except OSError:  # pragma: no cover - platform dependent (Windows ACLs)
            pass


_BOOL_TRUE = {"1", "true", "yes", "on"}
_ENV_PREFIX = "FM_"


def _coerce(name: str, value, current):
    target = type(current) if current is not None else str
    if name == "data_dir" or name == "frontend_dir":
        return Path(str(value)) if value not in (None, "") else None
    if target is bool:
        return value if isinstance(value, bool) else str(value).strip().lower() in _BOOL_TRUE
    if target is int:
        return int(value)
    return str(value)


def load_settings(overrides: dict | None = None) -> Settings:
    """Build settings from defaults, config file and environment (then explicit overrides e.g. CLI)."""
    s = Settings()
    env_data_dir = os.environ.get(_ENV_PREFIX + "DATA_DIR")
    explicit = (overrides or {}).get("data_dir") or env_data_dir
    data_dir = Path(explicit) if explicit else adopt_legacy_data_dir(s.data_dir, legacy_default_data_dir())
    s = replace(s, data_dir=data_dir)
    values: dict = {}
    cfg = data_dir / "config.toml"
    if cfg.is_file():
        with cfg.open("rb") as fh:
            values.update(tomllib.load(fh).get("server", {}) or {})
    names = {f.name for f in fields(Settings)}
    for n in names:
        env = os.environ.get(_ENV_PREFIX + n.upper())
        if env is not None:
            values[n] = env
    for k, v in (overrides or {}).items():
        if v is not None:
            values[k] = v
    clean = {}
    for k, v in values.items():
        if k in names and k != "data_dir":
            clean[k] = _coerce(k, v, getattr(s, k))
    s = replace(s, **clean)
    if s.mode not in ("local", "server"):
        raise ValueError("mode must be 'local' or 'server'")
    if s.mode == "local" and "host" not in values:
        s = replace(s, host="127.0.0.1")
    return s


def is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "::1", "localhost") or host.startswith("127.")
