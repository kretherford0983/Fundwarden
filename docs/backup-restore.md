# Backup and restore (since 1.4.1)

Administrators create and restore backups on **System/About → Backup / Restore**. A new installation can also be
set up from a backup in the **initialization wizard** ("Restore from a backup instead").

## What a backup contains

| Included | Not included |
|---|---|
| The database: organization, users and their password hashes, roles, two-step verification (authenticator secrets, recovery codes), every financial record, the audit log | `config.toml` (server settings: bind address, port, proxy, cookies) |
| Every attachment | Logs, the `pre-restore/` safety copy, temporary work files |
| The portable encryption key (`secrets/`) — needed to read bank account numbers and authenticator secrets | |

A backup is a single file `pennywarden-backup-<organization>-<date>-<time>.fmbak` (1.6.6 to 1.6.8:
`fundwarden-backup-…`; before 1.6.6:
`freedger-backup-…` — those files restore exactly as before).

## Encryption

The file is encrypted with a **passphrase you choose** (at least 12 characters): AES-256-GCM in 1 MiB authenticated
records, key derived with scrypt (N = 2^15, r = 8, p = 1). Record order, the end of the file and the header are
authenticated, so a changed, reordered or shortened file is refused. **Without the passphrase the backup cannot be
restored** — nobody (including the application) can recover a lost passphrase. Keep the passphrase in a password
manager and the backup file away from the server.

## Creating a backup

System/About → Backup / Restore → **Backup**: passphrase twice + your own password → **Create backup**. The database
is copied with SQLite's online backup API, so users can keep working. The download starts automatically; the file
stays downloadable from that page for one hour and is then deleted from the server's work folder.

## Restoring

System/About → Backup / Restore → **Restore**: choose the `.fmbak` file, enter its passphrase, your password and type
`RESTORE`. The file is uploaded in 20 MB parts (so large backups pass Cloudflare Tunnel's 100 MB request limit;
an interrupted part is retried). The page then shows each step:

1. Decrypting and checking the backup (passphrase, integrity, every file against the manifest)
2. Checking versions and the encryption key — a backup from a **newer** version is refused (upgrade the
   application first); a backup from an older 1.4.1+ version is migrated forward
3. Pausing the application (other requests get "restore in progress" for a few seconds)
4. Saving a safety copy of the current data — moved to `pre-restore/` in the data directory (only the latest copy
   is kept)
5. Updating the database to this version
6. Restarting the application — the database and key are reopened inside the running service (no process restart,
   works the same on Windows, systemd and Docker)

Everyone is signed out (all sessions and trusted browsers are revoked). Sign in with an account **from the backup**;
two-step verification continues with the authenticator from the backup. The restore is recorded in the restored audit
log as `SYSTEM_RESTORED`.

If any step fails the current data stays in place (or is put back from the safety copy) and the page says which step
failed. The largest accepted file is set by `restore_max_mb` in `config.toml` (default 20480).

## Moving to another server

On the new server install the same or a newer version, open it in the browser and choose **Restore from a backup
instead** in the initialization wizard (anyone who can reach an uninitialized installation can do this — the same as
running the wizard). The new server keeps its own `config.toml`.

## Manual recovery without the application

The files can also be copied by hand while the service is stopped: `database/`, `attachments/` and `secrets/` from
the data directory (`/var/lib/pennywarden` on a Linux server). The installer's automatic snapshots before each upgrade
(`/var/backups/pennywarden/<timestamp>/`) are such copies.
