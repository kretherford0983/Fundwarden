# Configuration

Precedence (docs/06 §11): **built-in defaults → `APP_DATA_DIR/config.toml` → `FM_*` environment variables →
command-line options**.

## Application data directory (`APP_DATA_DIR`)

Separate from the replaceable binaries (BR-086). Set with `--data-dir` or `FM_DATA_DIR`.

| OS | Default |
|---|---|
| Windows | `%LOCALAPPDATA%\PennyWarden` |
| Linux | `$XDG_DATA_HOME/pennywarden` or `~/.local/share/pennywarden` (a server install uses `/var/lib/pennywarden`) |

Before 1.6.6 the default folders were `%LOCALAPPDATA%\FinancialManagementPOC` and
`~/.local/share/financial-management-poc`. If the new folder does not exist yet and the old one does, 1.6.6 renames
the old folder at its first start (or uses it in place if it cannot be renamed). A folder chosen with `--data-dir`
or `FM_DATA_DIR` is never renamed.

```
APP_DATA_DIR/
  config.toml                      optional, human readable, no secrets
  database/fmpoc.sqlite3           SQLite (application owned; never opened over a network share)
  attachments/<xx>/<32-hex>.bin    generated storage names only
  secrets/portable-encryption-key.json   portable AES-256-GCM + HMAC keys (mode 0600; dir 0700)
  logs/fmpoc.log                   rotating, redacted
```

**The database, attachments and `secrets/` must be kept together.** Without the key file encrypted account
numbers cannot be decrypted; the application refuses to start if the key is missing or does not match the
database (key check value stored in the workspace row).

## Settings

| Setting (`config.toml [server]`) | Env var | Default | Meaning |
|---|---|---|---|
| `mode` | `FM_MODE` | `local` | `local` (loopback, opens browser) or `server` |
| `host` | `FM_HOST` | `127.0.0.1` | Bind address. Local mode always defaults to loopback |
| `port` | `FM_PORT` | `8765` | TCP port (UI and API share it) |
| `open_browser` | `FM_OPEN_BROWSER` | `true` | Local mode: open default browser after `/api/health` answers |
| `secure_cookies` | `FM_SECURE_COOKIES` | `auto` | `auto` = Secure flag when request is HTTPS; `true` behind a TLS proxy |
| `hsts` | `FM_HSTS` | `false` | Send HSTS on HTTPS responses |
| `trusted_proxies` | `FM_TRUSTED_PROXIES` | *(empty)* | Comma list of proxy IPs whose `X-Forwarded-*` headers are trusted (`*` only on a private network) |
| `session_idle_minutes` | `FM_SESSION_IDLE_MINUTES` | `30` | Idle session timeout |
| `session_absolute_hours` | `FM_SESSION_ABSOLUTE_HOURS` | `12` | Absolute session lifetime |
| `login_max_failures` | `FM_LOGIN_MAX_FAILURES` | `5` | Failed logins per username/IP before lock-out |
| `login_lockout_seconds` | `FM_LOGIN_LOCKOUT_SECONDS` | `900` | Failed-login window / lock-out duration |
| `log_level` | `FM_LOG_LEVEL` | `INFO` | Log level |

Example `config.toml`:

```toml
[server]
mode = "server"
host = "127.0.0.1"          # behind a reverse proxy on the same host
port = 8765
secure_cookies = "true"
hsts = true
trusted_proxies = "127.0.0.1"
```

Command line: `pennywarden --mode server --host 0.0.0.0 --port 8765 --data-dir /srv/pennywarden --no-browser`
(`python -m fmpoc` from source, `pennywarden` / `PennyWarden.exe` or `PennyWarden.cmd` when packaged).

Debug mode, interactive API docs (`/docs`, `/openapi.json`) and verbose exception pages are never enabled.
