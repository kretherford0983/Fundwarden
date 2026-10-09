# Configuration

Precedence (docs/06 §11): **built-in defaults → `APP_DATA_DIR/config.toml` → `FM_*` environment variables →
command-line options**.

## Application data directory (`APP_DATA_DIR`)

Separate from the replaceable binaries (BR-086). Set with `--data-dir` or `FM_DATA_DIR`.

| OS | Default |
|---|---|
| Windows | `%LOCALAPPDATA%\PennyWarden` |
| Mac | `~/Library/Application Support/PennyWarden` |
| Linux | `$XDG_DATA_HOME/pennywarden` or `~/.local/share/pennywarden` (a server install uses `/var/lib/pennywarden`) |

**Earlier names.** The application was called *Fundwarden* in 1.6.6 – 1.6.8 and *Financial Management POC* before
that. At its first start under the current name, if the PennyWarden folder does not exist yet, PennyWarden takes over
the folder of the most recent earlier name it finds — renaming it, or using it in place if it cannot be renamed:

| OS | Fundwarden (1.6.6 – 1.6.8) | before 1.6.6 |
|---|---|---|
| Windows | `%LOCALAPPDATA%\Fundwarden` | `%LOCALAPPDATA%\FinancialManagementPOC` |
| Mac | `~/Library/Application Support/Fundwarden` | — (the Mac app arrived in 1.6.7) |
| Linux | `~/.local/share/fundwarden` | `~/.local/share/financial-management-poc` |

A folder chosen with `--data-dir` or `FM_DATA_DIR` is never renamed. (A Linux *server* install is moved by the
installer instead; see docs/upgrade.md.)

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
| `login_max_failures` | `FM_LOGIN_MAX_FAILURES` | `5` | Failed sign-ins per client address (and per unknown username) before a pause - a brake on top of the per-account count below |
| `login_lockout_seconds` | `FM_LOGIN_LOCKOUT_SECONDS` | `900` | Window / pause for `login_max_failures` |
| `lockout_1_failures` / `lockout_1_minutes` | `FM_LOCKOUT_1_FAILURES` / `FM_LOCKOUT_1_MINUTES` | `5` / `15` | 1.8.0: failed attempts in a row on one account (wrong passwords and wrong *Forgot password* answers or codes together, kept in the database) that lock it, and for how long |
| `lockout_2_failures` / `lockout_2_minutes` | `FM_LOCKOUT_2_FAILURES` / `FM_LOCKOUT_2_MINUTES` | `10` / `60` | Second lock; from this one on, Administrators see a notice |
| `lockout_3_failures` / `lockout_3_minutes` | `FM_LOCKOUT_3_FAILURES` / `FM_LOCKOUT_3_MINUTES` | `15` / `1440` | Third lock (24 hours) |
| `lockout_disable_failures` | `FM_LOCKOUT_DISABLE_FAILURES` | `20` | The account is disabled; an Administrator (or the host `reset-password` / `reset-mfa`) enables it again |
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

## On a Mac

PennyWarden.app (Apple Silicon, since 1.6.7; installation: [install-macos.md](install-macos.md)) uses the same
settings as Windows and Linux. What is different:

- **Data folder:** `~/Library/Application Support/PennyWarden` — the database, attachments, `secrets/`, `logs/` and
  `config.toml` (see *Application data directory* above). Replacing the app with a newer one never touches it.
- **Opening the folder:** the `Library` folder is hidden in Finder. Use **Finder → Go → Go to Folder…** (⇧⌘G) and
  type `~/Library/Application Support/PennyWarden`. In Terminal: `open ~/Library/Application\ Support/PennyWarden`.
- **Log file:** `~/Library/Application Support/PennyWarden/logs/fmpoc.log`.
- **Settings for the app opened from Finder:** put them in `config.toml` in the data folder (create it with any text
  editor). An app opened from Finder or the Dock does **not** see `FM_*` environment variables set in a Terminal
  profile, so `config.toml` is the way to change settings permanently.
- **Starting with options:** run the app's program from Terminal, with the same options as on the other systems:
  ```
  /Applications/PennyWarden.app/Contents/MacOS/PennyWarden --port 8800
  /Applications/PennyWarden.app/Contents/MacOS/PennyWarden --data-dir ~/Documents/PennyWarden-data
  /Applications/PennyWarden.app/Contents/MacOS/PennyWarden --mode server     # server mode, no status window
  ```
  Started this way, `FM_*` environment variables of that Terminal do apply. In local mode the small PennyWarden
  window opens as usual (set `FM_NO_WINDOW=1` to run in the Terminal instead); closing it stops PennyWarden.
- **Host commands** work the same way, e.g. after a lost authenticator:
  `/Applications/PennyWarden.app/Contents/MacOS/PennyWarden reset-mfa --user NAME`, or when the only Administrator
  forgot the password and the answers to the security questions:
  `/Applications/PennyWarden.app/Contents/MacOS/PennyWarden reset-password --user NAME` (prints a temporary password
  that must be changed at the next sign-in). Both also enable a disabled account again.
- More about the Mac app (upgrading, the first start): [deployment.md](deployment.md) and
  [install-macos.md](install-macos.md).
