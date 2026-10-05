# Upgrading a Linux server install (current release: 1.6.7)

The upgrade replaces only the application binaries. It does **not** modify:

- `/var/lib/fundwarden/config.toml` (only written when it does not exist)
- `/var/lib/fundwarden/secrets/` (portable encryption key), `database/`, `attachments/`, `logs/`

Before switching versions the installer stops the service and copies the whole data directory to
`/var/backups/fundwarden/<timestamp>/`. The previous release stays in `/opt/fundwarden/releases/` for rollback.

| Upgrade | Database change | Rollback |
|---|---|---|
| 1.6.6 → 1.6.7 | migrations `0014` — **adds** column `entity.position` (empty for every existing Entity); `0015` — **adds** columns `reminder.repeat_every`, `repeat_unit`, `repeat_until`, `repeat_anchor`, `repeat_index`, `repeat_source_id` (existing reminders stay one-time) | switch binaries **and** restore the pre-upgrade data backup |
| 1.6.5 → 1.6.6 | none — the application is renamed to Fundwarden (see *1.6.6: the rename* below) | switch back to the old `fmpoc` service (left in place) |
| 1.6.4 → 1.6.5 | none | switch binaries only |
| 1.6.3 → 1.6.4 | migration `0013` — **adds** columns `fundraiser.cancelled_at`, `cancelled_by_user_id`, `cancel_reason` | switch binaries **and** restore the pre-upgrade data backup |
| 1.6.2 → 1.6.3 | migration `0012` — **adds** table `reminder` | switch binaries **and** restore the pre-upgrade data backup |
| 1.6.1 → 1.6.2 | none | switch binaries only |
| 1.6.0 → 1.6.1 | migration `0011` — **adds** tables `fundraiser_bucket`, `fundraiser_bucket_line`, `fundraiser_classification`, `fundraiser_exclusion` and column `attachment.fundraiser_id` | switch binaries **and** restore the pre-upgrade data backup |
| 1.5.0 → 1.6.0 | migration `0010` — **adds** column `workspace.fundraisers_enabled` (off) and tables `fundraiser`, `fundraiser_budget` | switch binaries **and** restore the pre-upgrade data backup |
| 1.4.1 → 1.5.0 | migration `0009` — **adds** column `app_user.dashboard_layout` (NULL = standard dashboard layout) | switch binaries **and** restore the pre-upgrade data backup |
| 1.3.0 → 1.4.1 | migrations `0006`–`0008` (as below) | switch binaries **and** restore the pre-upgrade data backup |
| 1.4.0 → 1.4.1 | migrations `0006` — **adds** table `signature_template`; `0007` — **adds** column `app_user.dashboard_charts`; `0008` — **adds** tables `user_mfa`, `mfa_recovery_code`, `trusted_device` and column `auth_session.mfa_pending`. **After the upgrade every user of a server install sets up two-step verification at the next sign-in** — see below | switch binaries **and** restore the pre-upgrade data backup |
| 1.3.0 → 1.4.0 | none | switch binaries only |
| 1.2.x → 1.4.0 | migration `0005` (see 1.2.x → 1.3.0) | switch binaries **and** restore the pre-upgrade data backup |
| 1.2.x → 1.3.0 | migration `0005` — **adds** tables `request_key`, `check_number_acknowledgement` and columns on `attachment` (document type, system-generated), `fiscal_year` (approval "no document" mark) and `app_user` (collapsed menu); existing Fiscal Year documents are labelled "Other" | switch binaries **and** restore the pre-upgrade data backup |
| 1.1.x → 1.3.0 | migrations `0003`–`0005` applied in order automatically | restore the pre-upgrade data backup |
| 1.2.0 → 1.2.1 | migration `0004` — **adds** four columns to `transaction_allocation` (per-allocation no-attachment flag, reason, who/when); no existing value is changed or removed | switch binaries **and** restore the pre-upgrade data backup (1.2.0 does not know revision 0004) |
| 1.1.x → 1.2.1 | migrations `0003` + `0004` applied in order automatically | restore the pre-upgrade data backup |
| 1.1.x → 1.2.0 | migration `0003` — **adds** columns to `register_transaction` (transfer link, no-attachment flag); no existing value is changed or removed | switch binaries **and** restore the pre-upgrade data backup (1.1.x cannot open a 0003 database) |
| 1.1.0 → 1.1.1 | none | switch binaries only |

Verified during release testing: upgrading a 1.4.0 server with data to 1.4.1 (installer, simulated systemd) left
`config.toml`, the key and all attachments byte-for-byte identical, kept every row and applied `0006`–`0008`; users
were then asked to set up two-step verification; a backup → restore round trip on the upgraded server worked
(including two-step verification from the backup). Rollback: the 1.4.0 binaries alone refuse the 1.4.1 database
("Can't locate revision"); restoring the installer's data snapshot with the 1.4.0 binaries returned exactly the
pre-upgrade data.
Verified for 1.6.7 (simulated systemd): a 1.6.6 `fundwarden` server with data was upgraded with `install-server.sh`:
snapshot taken, `0014` applied (`entity.position` empty for every Entity), every other row, attachment, the key and a
hand-edited `config.toml` identical. The 1.6.6 binaries alone refuse the 1.6.7 database ("Can't locate revision");
with the snapshot restored they started on exactly the pre-upgrade data.
Verified for 1.6.1: a 1.6.0 server with fundraisers was upgraded with `install.sh`: files identical, every row kept,
`0011` applied (four new empty tables); rollback started 1.6.0 on the identical data.
Verified for 1.6.0: a 1.5.0 server with data was upgraded with `install.sh` (test channel): `config.toml`, the key and
the attachment byte-for-byte identical, every row kept, `0010` applied (two new empty tables, module off). Rollback
(previous release + snapshot) started 1.5.0 on the identical data.
Verified for 1.5.0: a 1.4.1 server installation with data (users, accounts, transactions, an attachment) was
upgraded with the one-command `install.sh` from a (local) release: it chose the test pre-release, verified the
checksums, read the port from `config.toml`, snapshotted the data and ran `install-server.sh`. `config.toml`, the key
and the attachment were byte-for-byte identical, every row was kept and `0009` was applied. Rollback (previous
release + the snapshot) started 1.4.1 on the identical data.
Earlier: upgrading a 1.2.1 server with data to 1.3.0 left `config.toml`, the key and all
attachments byte-for-byte identical, kept every row, applied `0005`, labelled the existing Fiscal Year document "Other"
and reported the Audit Signoff as the only new closing requirement.
Earlier: upgrading a 1.2.0 server with data to 1.2.1 left `config.toml`, the key and all
attachments byte-for-byte identical, kept every row and existing no-attachment marks, and applied `0004`.
Earlier: upgrading a 1.1.1 server with data left `config.toml`, the encryption key and
every attachment file byte-for-byte identical, kept all rows, and the audit/entity reports, transfers and
documentation review worked on the pre-existing data.

## Steps

**One command on the server** (does steps 1–4 below; the data snapshot and rollback copy are the same):
```bash
curl -fsSL https://github.com/kretherford0983/Fundwarden/releases/latest/download/install.sh | sudo bash
```
This installs the newest production release. A specific release (for example a test pre-release on a test server):
`curl -fsSL https://github.com/kretherford0983/Fundwarden/releases/download/<tag>/install.sh | sudo bash -s -- --version <tag>`
(`<tag>` e.g. `v1.6.6` or `v1.6.6-test.30`). A release from before 1.6.6 installs under the old name (service `fmpoc`).

**From a test pre-release to the production release:** a server installed from any `v1.x.y-test.N` build upgrades
to the production release with the same command; the table above applies unchanged (a test build and the release of
the same version have the same database).
The port of the existing installation is read from `config.toml`. Then continue with *Verify*.

**Manual:**

1. Copy the new package and installer to the server (from the Fundwarden folder on your PC):
   ```powershell
   scp dist\Fundwarden-linux-x64-portable.tar.gz packaging\linux\install-server.sh you@yourserver:~/
   ```
2. (Optional) note the current version: `curl -s http://127.0.0.1:8765/api/system/status`
3. Run the installer — the same command as the first install:
   ```bash
   sudo bash install-server.sh Fundwarden-linux-x64-portable.tar.gz
   ```
   The port for the health check is read from your `config.toml` (which is never changed).
4. Expected output ends with `"version":"<new version>"` and `Installed.` and names the backup folder
   (`snapshotting data to /var/backups/fundwarden/<timestamp>`). The Cloudflare tunnel needs no change.
5. Verify: sign in, check the version under System/About (or My Account), open a Fiscal Year page and a register.
6. **Only when upgrading from a version before 1.3.0:** open each Fiscal Year that is not closed yet. Documents uploaded earlier are listed
   under *Other documents*; use the drop-down to mark the signoff as **Audit Signoff** and the budget approval as
   **Approval document** (or tick "No approval document"). Closed years are unaffected.

## Rollback

Rolling back across a database change (see the table above) requires restoring the data snapshot taken by the upgrade, because an older release
cannot open a database migrated by a newer one. **Anything entered after the upgrade is lost**, so export anything you need first.

```bash
sudo systemctl stop fundwarden
ls /opt/fundwarden/releases/ /var/backups/fundwarden/        # previous release + the snapshot taken at upgrade time
sudo ln -sfn /opt/fundwarden/releases/<previous> /opt/fundwarden/current
sudo mv /var/lib/fundwarden /var/lib/fundwarden.failed-upgrade      # keep it until you are sure
sudo cp -a /var/backups/fundwarden/<timestamp> /var/lib/fundwarden
sudo systemctl start fundwarden
```
(Verified during release testing: the previous release starts normally on the restored snapshot. Switching only the
symlink is not enough after a schema change — the older release refuses to start with "Can't locate revision".)
For 1.1.1 → 1.1.0 (no schema change) switching the symlink alone is enough.

## Notes

- The installer rewrites `/etc/systemd/system/fundwarden.service` on every run. Put any service customisations in a
  drop-in (`sudo systemctl edit fundwarden`), which is preserved.
- Old backups in `/var/backups/fundwarden/` are not pruned automatically; remove ones you no longer need.

## Windows (local install)

Data lives in `%LOCALAPPDATA%\Fundwarden` and is separate from the program folder.

1. Close the running console window (Ctrl+C) so the app is stopped.
2. Copy `%LOCALAPPDATA%\Fundwarden` somewhere safe (backup).
3. Unzip the new `Fundwarden-windows-x64.zip` into a **new** folder (keep the old one for rollback).
4. Run `Fundwarden.cmd` from the new folder. The database is migrated automatically on start.

To roll back: stop the app, restore the backed-up data folder, and run the old program folder.

## 1.6.6: the rename to Fundwarden (server installs)

Up to 1.6.5 the application was called *Financial Management POC* / *Freedger* and a server install used the service
`fmpoc`, `/opt/fmpoc`, `/var/lib/fmpoc` and `/var/backups/fmpoc`. From 1.6.6 everything is called `fundwarden`.
You do not prepare anything: run the normal upgrade command. When the installer finds an old installation and no
Fundwarden data yet, it migrates it:

1. checks that there is room for a second copy of the data (otherwise it stops before changing anything);
2. stops the `fmpoc` service and **copies** `/var/lib/fmpoc` to `/var/lib/fundwarden` (compared file by file before
   it is used), owned by the new system user `fundwarden` — `config.toml`, the key, the database and attachments
   arrive unchanged, so the port and your tunnel / reverse proxy stay as they are;
3. installs the program under `/opt/fundwarden`, creates and starts the service `fundwarden`, and disables `fmpoc`.

**Nothing of the old installation is changed or removed.** If Fundwarden does not come up healthy, the installer
switches back to `fmpoc` by itself and says so.

| Before 1.6.6 | From 1.6.6 |
|---|---|
| service and system user `fmpoc` | `fundwarden` |
| `/opt/fmpoc/current/FinancialManagementPOC` | `/opt/fundwarden/current/fundwarden` |
| `/var/lib/fmpoc` (data, `config.toml`) | `/var/lib/fundwarden` |
| `/var/backups/fmpoc/<timestamp>` (snapshots) | `/var/backups/fundwarden/<timestamp>` |
| `FinancialManagementPOC-linux-x64-portable.tar.gz`, `FinancialManagementPOC-windows-x64.zip`, `Freedger-<version>-windows-x64.exe` | `Fundwarden-linux-x64-portable.tar.gz`, `Fundwarden-windows-x64.zip`, `Fundwarden-<version>-windows-x64.exe` |
| `%LOCALAPPDATA%\FinancialManagementPOC` (Windows, local) | `%LOCALAPPDATA%\Fundwarden` |
| backups `freedger-backup-….fmbak` | `fundwarden-backup-….fmbak` (older backup files restore as before) |

Not renamed (internal, invisible in normal use): the database file `database/fmpoc.sqlite3`, the log file
`logs/fmpoc.log`, the `FM_*` environment variables and the `.fmbak` extension.

**Going back to 1.6.5** (no database change between 1.6.5 and 1.6.6): the old installation is still complete.
```bash
sudo systemctl disable --now fundwarden && sudo systemctl enable --now fmpoc
```
It continues with the data as it was at the moment of the migration; anything entered in Fundwarden since then
stays in `/var/lib/fundwarden`. To migrate again later, move `/var/lib/fundwarden` away first and run the installer.

Verified for 1.6.6 (simulated systemd): a 1.6.5 `fmpoc` server with data was upgraded with `install.sh`: every table
row, every attachment, the key and a hand-edited `config.toml` identical in `/var/lib/fundwarden`; `/var/lib/fmpoc`
byte-for-byte untouched; 1.6.6 answered on the same port. The switch back started 1.6.5 on its data; a package that
does not start made the installer return to `fmpoc` automatically; after the cleanup below 1.6.6 kept running on
identical data and a further upgrade took its snapshot in `/var/backups/fundwarden`.

### Cleanup after the rename

Do this on each migrated server (dev, test, later any other) **once you are sure you will not go back** — for
example after a few days of normal use and one fresh backup (System/About → Backup / Restore) stored off the server.
Until then the leftovers only cost disk space. The installer reminds you with a `NOTE:` line as long as they exist.

```bash
# 0. Fundwarden is the one that is running, and the old service is not
systemctl is-active fundwarden            # must print: active
systemctl is-active fmpoc                 # must print: inactive
curl -s http://127.0.0.1:<port>/api/system/status      # "version":"1.6.6" (or later) and your organization's name

# 1. optional: one last archive of the old data, kept somewhere safe (it contains the encryption key)
sudo tar -C /var/lib -czf /root/fmpoc-final-data.tar.gz fmpoc

# 2. remove the old service
sudo systemctl disable --now fmpoc
sudo rm -f /etc/systemd/system/fmpoc.service
sudo rm -rf /etc/systemd/system/fmpoc.service.d      # only exists if you made a drop-in with "systemctl edit fmpoc"
sudo systemctl daemon-reload

# 3. remove the old program, data and snapshots
sudo rm -rf /opt/fmpoc /var/lib/fmpoc /var/backups/fmpoc

# 4. remove the old system user
sudo userdel fmpoc

# 5. check
systemctl is-active fundwarden            # still: active
ls -d /opt/fmpoc /var/lib/fmpoc /var/backups/fmpoc 2>&1    # "No such file or directory" three times
```

Also check, because the installer cannot know about them:
- a **drop-in** you created for the old service (`/etc/systemd/system/fmpoc.service.d/`): recreate what you still
  need with `sudo systemctl edit fundwarden` before deleting it;
- your own **backup jobs, cron entries or monitoring** that mention `fmpoc`, `/var/lib/fmpoc` or
  `/var/backups/fmpoc`: point them at the new names;
- **downloaded installers** in home directories (`install-server.sh`, `FinancialManagementPOC-*.tar.gz`) and
  `/var/lib/fundwarden.failed-migration-*` (only present if a migration attempt failed): delete them;
- the Cloudflare tunnel / reverse proxy needs **no** change (same address and port).

On a **Windows** PC nothing needs cleaning up: at its first start 1.6.6 renames the data folder
`%LOCALAPPDATA%\FinancialManagementPOC` to `%LOCALAPPDATA%\Fundwarden` (a rename in place — nothing is copied; a
data folder you chose yourself with `--data-dir` or `FM_DATA_DIR` is never touched). Delete the old
`Freedger-…exe` / `FinancialManagementPOC-windows-x64` folder when you no longer want it. To go back to 1.6.5 on
Windows, rename the folder back first.

## 1.4.1: two-step verification after the upgrade (server installs)

Sessions that were open before the upgrade keep working until they end. At the **next sign-in every user** is asked to
set up an authenticator app (QR code or typed key) and to save 10 recovery codes. Do it yourself first as the
Administrator, with your phone at hand.

If a user loses both the phone and the recovery codes: Users → *Reset two-step* (Administrator, reason required).
If the only Administrator is locked out, on the server:

```
sudo -u fundwarden /opt/fundwarden/current/fundwarden reset-mfa --user <username> --data-dir /var/lib/fundwarden
```

(run it as the `fundwarden` service account so file ownership in the data directory does not change). The reset is
recorded in the audit log; the user sets up two-step verification again at the next sign-in.
