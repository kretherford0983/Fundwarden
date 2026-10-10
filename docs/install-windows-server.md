# Running PennyWarden as a server on Windows

For an organization where several people use PennyWarden from their own computers, and the server is a Windows
machine (Windows 10/11 or Windows Server) that stays on. On a single PC for one person, use the normal Windows
download instead ([deployment.md](deployment.md#local-installation-single-user-loopback)). On Linux, the one-command
install does all of this for you ([deployment.md](deployment.md#linux-one-command-since-150)).

In server mode PennyWarden requires **two-step verification** for every user, and it must be reached over
**HTTPS**. The steps below set up both: PennyWarden itself listens only on the server, and an HTTPS front end passes
the browsers' requests to it.

## 1. Unpack PennyWarden

1. From the [latest release](https://github.com/kretherford0983/PennyWarden/releases/latest), download
   **`PennyWarden-windows-x64.zip`** (the portable folder — better for a server than the one-file `.exe`, which
   unpacks itself at every start). Optionally check it: `Get-FileHash .\PennyWarden-windows-x64.zip` against
   `SHA256SUMS.txt` from the same release.
2. Unzip it to a folder of its own, for example **`C:\PennyWarden\1.10.0`**. It contains `PennyWarden-Server.cmd`
   (server mode) and `PennyWarden.cmd` (local mode and the host commands).

## 2. Choose the data folder and the settings

A service does not run as you, so give PennyWarden a fixed data folder instead of the per-user default:

1. Create **`C:\ProgramData\PennyWarden`**. Right-click → Properties → Security: leave access to *Administrators*,
   *SYSTEM* and the account the service will run as (step 4) only. The folder holds the database, the attachments
   and the encryption key.
2. In it, create **`config.toml`** (Notepad is fine; save as "All files", not `.txt`):

   ```toml
   [server]
   mode = "server"
   host = "127.0.0.1"          # only the HTTPS front end on this machine talks to PennyWarden
   port = 8765
   secure_cookies = "true"     # it is reached over HTTPS
   trusted_proxies = "127.0.0.1"
   # where scheduled backups may be written (Backup / Restore -> Scheduled), e.g. a second drive or a NAS share:
   backup_folders = ['D:\PennyWarden-backups']
   ```

   All settings: [configuration.md](configuration.md). Single quotes keep Windows backslashes as they are.

Try it once from a Command Prompt:

```
C:\PennyWarden\1.10.0\PennyWarden-Server.cmd --data-dir C:\ProgramData\PennyWarden
```

It prints `PennyWarden <version> - server mode - http://127.0.0.1:8765`. Open that address **on the server** and
you see the Initialization Wizard. Do not finish it yet if you want the first Administrator to be created over the
HTTPS address — close the window (Ctrl+C) and continue.

## 3. HTTPS in front of PennyWarden

Pick one:

- **Cloudflare Tunnel** (no open ports on your network; a domain managed by Cloudflare). Install `cloudflared` as a
  Windows service from the Cloudflare Zero Trust dashboard (Networks → Tunnels → *Create a tunnel* → Windows) and add a
  public hostname, e.g. `books.example.org`, with the service **`http://127.0.0.1:8765`**. Cloudflare provides the
  certificate.
- **Caddy** (the server is reachable from the internet or your network under a domain name that points at it). Download
  `caddy.exe` from <https://caddyserver.com/download>, put it in `C:\Caddy` with a file `Caddyfile`:

  ```
  books.example.org {
      reverse_proxy 127.0.0.1:8765
  }
  ```

  Caddy obtains and renews the certificate itself (ports 80 and 443 must reach the server). Run it as a service the
  same way as PennyWarden in step 4 (program `C:\Caddy\caddy.exe`, arguments `run --config C:\Caddy\Caddyfile`), and
  allow it through the firewall:
  `New-NetFirewallRule -DisplayName "Caddy HTTPS" -Direction Inbound -Protocol TCP -LocalPort 80,443 -Action Allow`

Port 8765 is **not** opened in the firewall: only the front end on the same machine uses it.

## 4. Start PennyWarden with Windows

Windows' built-in **Task Scheduler** runs PennyWarden at start-up, before anyone signs in:

1. Create a local user for the service, e.g. `pennywarden` (Computer Management → Local Users and Groups), and give
   it full control of `C:\ProgramData\PennyWarden` and of the backup folder.
2. Task Scheduler → **Create Task…** (not "Basic Task"):
   - *General:* name `PennyWarden`; **Run whether user is logged on or not**; user `pennywarden`.
   - *Triggers:* **At startup**.
   - *Actions:* Start a program — Program `C:\PennyWarden\1.10.0\PennyWarden-Server.cmd`, arguments
     `--data-dir C:\ProgramData\PennyWarden`.
   - *Conditions:* clear "Start the task only if the computer is on AC power".
   - *Settings:* **If the task fails, restart every 1 minute**, up to 3 times; clear **Stop the task if it runs
     longer than…**.
3. Right-click the task → **Run**, then open your HTTPS address. The Initialization Wizard creates the organization
   and the first Administrator, who sets up two-step verification right away.

The log is `C:\ProgramData\PennyWarden\logs\fmpoc.log`.

## Upgrading

1. Make a backup first (System/About → Backup / Restore), or copy `C:\ProgramData\PennyWarden` while PennyWarden is
   stopped.
2. Unzip the new version next to the old one, e.g. `C:\PennyWarden\1.11.0`.
3. Task Scheduler → PennyWarden → **End**; edit the action to the new folder; **Run**. The database is updated at the
   start. To go back, point the task at the old folder again and restore the backup if the new version changed the
   database ([upgrade.md](upgrade.md) lists the database changes per version).

When an update is available, Administrators see it in PennyWarden itself (the gold arrow next to their name).

## Host commands

Run them on the server, in a Command Prompt started as the service account or as Administrator, with PennyWarden
stopped or running:

```
C:\PennyWarden\1.10.0\PennyWarden.cmd reset-mfa --user NAME --data-dir C:\ProgramData\PennyWarden
C:\PennyWarden\1.10.0\PennyWarden.cmd reset-password --user NAME --data-dir C:\ProgramData\PennyWarden
```

`reset-mfa` makes the user set up two-step verification again; `reset-password` prints a temporary password that
must be changed at the next sign-in. Both also enable an account that was disabled after too many failed attempts.
