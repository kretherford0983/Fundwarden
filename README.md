<h1><img src="frontend/public/favicon.svg" alt="" width="36" align="top"> Fundwarden</h1>

**Free financial ledger for small organizations** — clubs, associations, booster groups and similar bodies that
keep a checkbook, a budget and an annual audit. Fundwarden runs on your own Windows PC, Mac or Linux server; your data
stays in one folder you control. Current release: **1.6.7** (1.6.6 was the first production release) —
[download](https://github.com/kretherford0983/Fundwarden/releases/latest) · [changelog](CHANGELOG.md).

## What it does

- **Fiscal years and budgets** — hierarchical income/expense budgets per Fiscal Year, budget adjustments, a
  Fiscal Year close with a stored **Close report**.
- **Registers** — continuous checking/savings/investment registers, split allocations across budgets, transfers
  between accounts, void lifecycle, duplicate and check-number protection, missing-check review.
- **Documentation** — attachments (PDF/PNG/JPEG) on transactions and allocations, typed Fiscal Year documents
  (approval, audit signoff), a documentation review that shows what is still missing.
- **Reports** — printable **End of Year Audit** PDF (budgets, every transaction with its attachments, signature
  page), Entity activity report with CSV, Fiscal Year Close report, dashboard with charts and a per-user layout.
- **Fundraisers** (optional module) — budgets, buckets, cash float, exclusions, documents, a fundraiser report,
  cancelled fundraisers and a printable cash count sheet.
- **Reminders** — personal and organization reminders with a notification bell and dashboard section.
- **Roles** — Administrator, Budget Manager, Budget User, Register User, Auditor (read-only), with strict
  separation between administration and financial work.
- **Security** — Argon2id passwords, two-step verification (TOTP) with recovery codes, server-side sessions, CSRF
  protection, AES-256-GCM encrypted bank account numbers, an append-only audit trail, encrypted backup/restore.

## Install

| | |
|---|---|
| **Mac with Apple Silicon (single user)** | Download `Fundwarden-<version>-macos-arm64.dmg` from the [latest release](https://github.com/kretherford0983/Fundwarden/releases/latest), drag Fundwarden to Applications and open it. First start: *System Settings → Privacy & Security → Open Anyway* ([details](docs/deployment.md)). |
| **Windows (single user)** | Download `Fundwarden-<version>-windows-x64.exe` from the [latest release](https://github.com/kretherford0983/Fundwarden/releases/latest) and double-click it. |
| **Linux server (multiple users)** | `curl -fsSL https://github.com/kretherford0983/Fundwarden/releases/latest/download/install.sh \| sudo bash` — installs or upgrades a systemd service; put an HTTPS reverse proxy in front of it. |

The first start shows the **Initialization Wizard** (organization name, administrator account). There are no
default credentials. Details, HTTPS, Docker and moving data between machines: [docs/deployment.md](docs/deployment.md).
Upgrades never touch your data or configuration: [docs/upgrade.md](docs/upgrade.md). **Make encrypted backups
regularly** (System/About → Backup / Restore) and keep them off the machine: [docs/backup-restore.md](docs/backup-restore.md).

Fundwarden is provided without warranty (see [License](#license)). It is a record-keeping tool, not accounting,
tax or legal advice.

## Documentation

**Using Fundwarden** — the guides describe what each release line added; read them in order for the full picture:
[1.2](docs/user-guide-v1.2.md) (reports, transfers) · [1.3](docs/user-guide-v1.3.md) (Fiscal Year documents, close
report) · [1.4](docs/user-guide-v1.4.md) (audit signatures, two-step verification, charts, backup) ·
[1.5](docs/user-guide-v1.5.md) (dashboard layout, installers) · [1.6](docs/user-guide-v1.6.md) (fundraisers,
reminders).

**Running Fundwarden**
- [docs/deployment.md](docs/deployment.md) — local and server installation, HTTPS reverse proxy, Docker, data portability
- [docs/upgrade.md](docs/upgrade.md) — upgrading and rolling back; database changes per version
- [docs/backup-restore.md](docs/backup-restore.md) — encrypted backups, restore, disaster recovery
- [docs/configuration.md](docs/configuration.md) — settings, config file, environment variables, data layout
- [docs/security.md](docs/security.md) — security controls and dependency-vulnerability checks

**Developing Fundwarden**
- [docs/branching.md](docs/branching.md) — branches, builds, releases and versioning (`Breaking.Major.Minor`)
- [docs/implementation-notes.md](docs/implementation-notes.md) — design decisions, including every change request (§1a)
- [CHANGELOG.md](CHANGELOG.md) — what changed in each version

**Origin.** Fundwarden started as an implementation of the *Financial Management POC Agent-Agnostic Benchmark v1.1*.
The specification is kept unchanged in [`spec/`](spec/); [docs/acceptance-results.md](docs/acceptance-results.md),
[docs/benchmark-results.md](docs/benchmark-results.md) and [docs/manual-verification.md](docs/manual-verification.md)
record the results against that specification as of version 1.1 and are not updated for later versions. Until 1.6.5
the application was called *Financial Management POC* / *Freedger*; the Python package (`fmpoc`), the database file
and the `FM_*` settings keep those internal names. Upgrading an installation from before the rename:
[docs/upgrade.md](docs/upgrade.md).

## Technology

| | |
|---|---|
| Frontend | React 18 + TypeScript (Vite build, served by FastAPI) |
| Backend | Python 3.11/3.12, FastAPI, SQLAlchemy 2, Alembic, SQLite |
| Tests | 230+ backend API tests (incl. security negative tests) and 31 Playwright E2E UI tests, run on every pull request; every package is smoke-tested before it is published |

## Build from source

```bash
python3 -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r backend/requirements-dev.txt
npm --prefix frontend ci && npm --prefix frontend run build   # emits backend/fmpoc/static
cd backend && python -m fmpoc                          # local mode: http://127.0.0.1:8765, opens browser
```

Useful options: `--mode server --host 0.0.0.0 --port 8765 --data-dir DIR --no-browser` (see
[docs/configuration.md](docs/configuration.md)). Frontend development with hot reload: run the backend
(`python -m fmpoc --no-browser`) and `npm --prefix frontend run dev` (Vite proxies `/api` to port 8765).

### Tests

```bash
cd backend && python -m pytest                    # API tests incl. security negative tests
cd frontend && npx tsc --noEmit -p . && npm run build
cd frontend && FM_PYTHON=$(which python) npx playwright test                     # E2E vs source
cd frontend && FM_BUNDLE=../dist/fundwarden/fundwarden npx playwright test   # E2E vs package
bash scripts/security_check.sh                    # pip-audit + npm audit + security tests
```

### Packaging

| Artifact | Command | Notes |
|---|---|---|
| Linux x86-64 portable (servers, glibc ≥ 2.27) | `bash packaging/build_linux_portable.sh` | → `dist/Fundwarden-linux-x64-portable.tar.gz`; install with `sudo bash packaging/linux/install-server.sh <tarball>` |
| Linux x86-64 self-contained | `bash packaging/build_linux.sh` | PyInstaller onedir → `dist/Fundwarden-linux-x64.tar.gz` |
| Windows x86-64 portable folder | `bash packaging/build_windows_portable.sh` | Runs on any OS; relocatable CPython + win_amd64 wheels → `dist/Fundwarden-windows-x64.zip`; launch `Fundwarden.cmd` |
| Windows x86-64 one-file .exe | `pyinstaller --noconfirm --distpath dist packaging/pyinstaller/fmpoc-onefile.spec` | Build on Windows (CI: `windows-latest`) → `Fundwarden-<version>-windows-x64.exe` |
| macOS arm64 app + disk image | `bash packaging/build_macos.sh` | Build on a Mac with Apple Silicon (CI: `macos-15`) → `dist/Fundwarden.app`, `Fundwarden-<version>-macos-arm64.dmg` (ad hoc signed) |
| Windows x86-64 PyInstaller folder | `pwsh packaging/build_windows.ps1` | Build on Windows → `Fundwarden.exe` |
| Linux one-command install | `packaging/linux/install.sh` | Published with every release — see [docs/deployment.md](docs/deployment.md) |
| Docker (optional, server) | `docker build -f packaging/docker/Dockerfile -t fundwarden .` | plus `docker-compose.yml` with Caddy HTTPS |
| Docker from bundle (no registry needed) | `bash packaging/docker/build_bundle_image.sh` | image from the self-contained Linux bundle |

CI/CD (GitHub Actions, `.github/workflows/`): every pull request and feature branch runs the full test suite; merges
into `develop`, `test` and `main` build the packages; `test` publishes a pre-release `v<version>-test.<n>` and `main`
publishes the production release `v<version>`. See [docs/branching.md](docs/branching.md).

### Repository layout

```
backend/fmpoc/            FastAPI app (routers/, services/, security/, migrations/, static/ = built UI)
backend/tests/            pytest suite
frontend/src/             React + TypeScript UI;  frontend/e2e/  Playwright tests
packaging/                PyInstaller specs, Linux/Windows build scripts, installers, Docker
scripts/                  version, promotion and release checks, security_check.sh
spec/                     original benchmark specification (unchanged)
docs/                     user guides, operations and implementation documentation
```

## Issues and contributions

Bugs and enhancement requests: [GitHub issues](https://github.com/kretherford0983/Fundwarden/issues). Please do **not**
put real financial data, account numbers or backups in an issue.

## License

Fundwarden is free software: you can redistribute it and/or modify it under the terms of the
[GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0-only). If you run a modified version for other people
over a network, you must offer them its source code. Bundled third-party components keep their own licenses — see
[THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt) (regenerate with `python scripts/third_party_notices.py`; CI
checks it is current).
