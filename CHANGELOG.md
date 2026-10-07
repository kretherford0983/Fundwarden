# Changelog

Versions are `Breaking.Major.Minor` from 1.6.0 (docs/branching.md).

## 1.6.8 — 2026-10-07
Maintenance of the build pipeline and repository security automation. No change to the application itself, its data
or its settings.
- **GitHub Actions on Node.js 24 (#48).** The workflow actions ran on the deprecated Node.js 20 runtime and were
  being forced onto Node.js 24 with a warning on every run. They now use the versions built for Node.js 24:
  `actions/checkout@v7`, `actions/setup-node@v7`, `actions/setup-python@v7`, `actions/upload-artifact@v7` and
  `actions/download-artifact@v8`. The Node.js version that builds the application (22) is unchanged.
- **Linux jobs pinned to Ubuntu 26.04 (#49).** GitHub moves `ubuntu-latest` to Ubuntu 26.04 from 2026-10-19. The
  five Linux jobs (tests, promotion rules, packages, assemble, publish) now name `ubuntu-26.04`, so the move happens
  on our schedule and is proven by the pull request's own run. The E2E tests use **Playwright 1.63.0** (was 1.56.1,
  which cannot install its browser on Ubuntu 26.04). Returning to `ubuntu-latest` is a later one-line change.
- **Weekly security check (#64).** New workflow `security`: every Monday (and on demand from the Actions tab) GitHub
  runs the dependency vulnerability checks and the security tests on `main`. A new advisory fails the run and GitHub
  emails the repository owner, so it is noticed between releases — not, as with 1.6.7, at the release pull request.
- **Dependabot (#65).** `.github/dependabot.yml`: weekly update pull requests into `develop` for the Python,
  JavaScript and GitHub Actions dependencies — minor and patch updates grouped into one pull request per group,
  major versions separately, at most 5 open per group. The promotion rules now accept `dependabot/*` branches into
  `develop` (and only there). docs/branching.md describes how such a pull request is handled.
- **Demo data script (#66).** `scripts/demo_data.py` no longer prints the demo password when it finishes (reported
  by CodeQL as clear-text logging); it points to the `PASSWORD` constant in the script instead. The password was
  always a made-up value in a public file — nothing was exposed.

## 1.6.7 — 2026-10-06
Recurring organization reminders, a Mac app, account start and end pages in the audit report, register filters,
phone number formatting, cash count sheet refinements and a position for people. Database migrations `0014`,
`0015` (new optional columns only) and `0016` (tidies stored phone numbers). Rolling back to 1.6.6 needs the data
snapshot the installer takes before the upgrade (docs/upgrade.md).
- **Recurring organization reminders.** An organization reminder can **repeat every N days, weeks, months or
  years**, optionally **until** an end date (New reminder → *Repeat*). Each occurrence is its own reminder with its
  own resolution note. **Resolving one creates the next**, due one interval after the *scheduled* due date — not the
  day it was resolved — so a monthly reminder stays on its day of the month (the 31st falls on the last day of
  shorter months). In the Resolve dialog, *Stop repeating after this one* ends the series; so does deleting the
  upcoming occurrence. Reopening a resolved occurrence takes back the next one it created (refused once that next
  one has itself been resolved). Personal reminders stay one-time. Existing reminders are unchanged.
- **Audit and Fiscal Year Close reports — account start and end pages.** When the report covers more than one bank
  account, each account's transactions now sit between a **"Start of transactions"** page and an **"End of
  transactions"** page. Both name the account, its number of transactions, deposits, withdrawals, first and last
  transaction, and state the account's page range ("pages 4 to 9 of 12 (6 pages…)"), each pointing at the other.
  Every page in between shows the account and **"section page k of n"** at the bottom right, so a reviewer can see
  which account a page belongs to and that no page is missing. A report for a single account is unchanged. The
  page range of each account is also recorded with the report in the audit log.
- **Mac app (Apple Silicon).** New download `Fundwarden-<version>-macos-arm64.dmg` for Macs with an M1 or later
  chip (macOS 11+): open the disk image, drag **Fundwarden** to Applications and open it. A small Fundwarden window
  shows the address, opens the browser and has **Quit**; closing the window stops Fundwarden. Data is kept in
  `~/Library/Application Support/Fundwarden`, so replacing the app with a newer one keeps everything. Like the
  Windows .exe, the app is **not signed with a paid developer certificate**: the first time, macOS says it could
  not verify the app — open *System Settings → Privacy & Security* and click **Open Anyway** (once). The steps are
  in *Read me first* inside the disk image and in docs/deployment.md. Built and smoke-tested by CI on a macOS
  arm64 machine with every build.
- **Documentation.** The README on the project page now presents what Fundwarden does: the core features, each
  with a screenshot (dashboard, budgets, register, audit report, closing the year, fundraisers, reminders), and a
  table of all capabilities. The screenshots come from a made-up organization: `scripts/demo_data.py` fills a new,
  empty installation through the normal API and `scripts/readme_screenshots.mjs` retakes them.
- **Fiscal Year documentation review — links to the Register.** The transaction number of every item in the
  documentation review is now a link: it opens the Register on that bank account (all dates), scrolls to the
  transaction, highlights it and opens its details — where a document can be attached right away.
- **Register — Attachments filter.** A new **Attachments** filter next to Status: *All* (default), *Yes* (only
  transactions that have an attachment, on the transaction or on one of its lines) or *No* (only those without).
  It counts exactly what the paperclip in the row counts, so a transaction marked "no attachment will be
  provided" is listed under *No*. It combines with the other filters; the balances stay those of the whole register.
- **Register — Clear filters.** A **Clear** button next to the register's filters puts Fiscal Year, Type, Status,
  Attachments, From, To and Search back to how the register opens (the current Fiscal Year, everything else
  empty). The chosen bank account stays. The button is greyed out when no filter is set.
- **Entity phone numbers.** Type a phone number any way you like — `5551234567`, `555-123-4567`, `555.123.4567`,
  `(555) 123-4567`, with or without a leading 1. It is stored as plain digits and always shown as
  **(555) 123-4567**; the field tidies itself when you leave it. An extension (`x204`, `ext 204`, `#204`) is kept
  and shown as `x204`; a number from another country is entered with a leading `+` and kept as typed digits.
  Anything else is refused with a hint. Database migration `0016` rewrites the numbers already stored that are
  clearly 10-digit numbers; any other existing value is left untouched and can still be edited.
- **Position of a person.** An individual Entity can have a **Position in the organization** (for example
  "Treasurer"; optional, set by a Budget Manager or Register User on the Entity). When that person is chosen as a
  signer on the **audit review signature page** or the **cash count sheet**, the position is filled in as the title.
  It can still be changed or cleared for that one print. Not used anywhere else.
- **Cash count sheet — chosen signers.** A chosen signer now gets one long signature line running across to the
  date, with the name (and title) printed under it — no "Signature" / "Printed" labels and no empty gap. Rows left
  empty are unchanged (Signature, Printed, Date to fill in by hand).
- **Cash count sheet — dialog.** Starts with two empty rows and offers *+ Add signature line* right away (still at
  most three empty rows, or two next to chosen signers, and five rows in total).
- **Installer fix.** `curl …/releases/latest/download/install.sh | sudo bash` (without `--version`) stopped with
  "no release found": GitHub answers the release lookup on one line and the installer only understood the
  multi-line form. It now understands both. (Installing with `--version <tag>` was not affected.)
- Build: a build tool's helper library (`source-map-js`, used only while building the web interface and not part
  of what is installed) is updated to 1.2.2 after a security advisory published on the day of the release
  (GHSA-68fv-2mgg-jv7q) stopped the release check.
- Build: the Mac app's smoke test no longer fails at random ("LICENSE is not bundled" on one build of develop):
  it searched the page while still downloading it.
- Build: the browser tests wait longer for the page after signing in (a slow build machine failed one run of 1.6.6).

## 1.6.6 — 2026-10-02
**First production release, under a new name: Fundwarden.** The application leaves its proof-of-concept names
(*Financial Management POC*, *Freedger*, `fmpoc`) behind. No database change; nothing about how you work changes.
Everything from 1.1 to 1.6.5 (sections below, kept as written) was published on the test channel only.
- **New name everywhere you see it:** browser tab, sign-in page, top bar, PDF properties, authenticator entry for
  new two-step set-ups (existing entries keep working and keep their old label), backup file names
  (`fundwarden-backup-….fmbak`; older backups restore as before) and the recovery-codes file.
- **App icon:** a gold coin with a keyhole — browser tab (favicon), phone home-screen icon and the Windows `.exe`.
- **Downloads renamed:** `Fundwarden-<version>-windows-x64.exe`, `Fundwarden-windows-x64.zip` (start
  `Fundwarden.cmd`), `Fundwarden-linux-x64-portable.tar.gz` (program `fundwarden`).
- **Linux servers:** service, system user and folders are now `fundwarden` (`/opt/fundwarden`,
  `/var/lib/fundwarden`, `/var/backups/fundwarden`). The normal upgrade command migrates an existing `fmpoc`
  installation: the data is *copied* (and compared) to the new place, the old service is stopped and disabled and
  **left in place**, so going back is one command; if Fundwarden does not start, the installer switches back by
  itself. Removing the old installation afterwards is a short manual checklist: docs/upgrade.md,
  *Cleanup after the rename*.
- **Windows:** the data folder `%LOCALAPPDATA%\FinancialManagementPOC` is renamed to `%LOCALAPPDATA%\Fundwarden`
  at the first start (in place; nothing is copied).
- **Installer:** `install-server.sh` reads the health-check port from the existing `config.toml` and takes its data
  snapshot before every upgrade even when the service was stopped; `install.sh` can still install a release from
  before the rename (`--version <tag>`).
- **Cash count sheet — signature rows.** The sheet is meant to be printed before it is known who will count. Each
  person now gets one row across the page: **Signature**, **Printed** name and **Date**, with room to write. A row
  left empty in *Cash count sheet…* is filled in by hand; a chosen signer's name is printed on the *Printed* line.
  The dialog starts with three empty rows. Up to five rows; at most three may be empty, or two next to chosen
  signers. Always two lines for notes. (Before: a single line captioned "Name and title".)
- **Cash count sheet — checks.** Page 1 now lists 13 checks, level with the 13 bill and coin lines, which leaves the
  room for notes and signatures. An optional **page 2** (on by default) has 30 more check lines and their own total:
  print it on the back with two-sided printing, as a second sheet, or leave it out when it is not needed.
- The source code moved to `github.com/kretherford0983/Fundwarden` (the old address redirects).
- Unchanged on purpose (internal): Python package `fmpoc`, `database/fmpoc.sqlite3`, `logs/fmpoc.log`, `FM_*`
  settings, the `.fmbak` format.

## 1.6.5 — 2026-10-02
Polish and documentation. Beta: test channel only. No database change.
- **Documentation** prepared for the first production release (planned: 1.6.6): README, deployment, upgrade, backup
  and branching guides. Until that release exists, the `releases/latest` install command does not work yet — use a
  pre-release's own address (shown in its release notes).
- **Dashboard bank account balances** (GitHub issue #15): *Checking & Savings* and *Investments and Other* are now
  separate tables with their own heading and subtotal and space between them, and the total of all accounts stands
  on its own below — matching the Bank Accounts page.

## 1.6.4 — 2026-10-02
Two fundraiser additions. Beta: test channel only.
- **CR-037 Cancelled fundraisers.** A Budget Manager can **mark a fundraiser as cancelled** (a reason is required)
  when it did not take place as planned, and **reinstate** it later. The fundraiser shows the status *Cancelled* and
  the reason on its page, in the lists, in its report and therefore in the End of Year Audit and Fiscal Year Close
  reports. Expenses and deposits already made stay listed and counted; buckets, documents and everything else keep
  working. Recorded in the audit log. Database migration `0013` (three new columns).
- **CR-038 Cash count sheet.** *Cash count sheet…* on a fundraiser's page opens a one-page PDF to print and fill in
  by hand: date and time of the count, a grid for bills and coins, a list for checks, **Cash total / Check total /
  Total counted** (the totals can be used on their own), notes, and signature lines with dates — for up to five
  chosen individuals (with optional titles) or three blank lines — under a statement that the signers agree with the
  amounts. Scan the signed sheet and add it under *Fundraiser documents*.

## 1.6.3 — 2026-10-02
Reminders and notifications. Beta: test channel only.
- **CR-036 Reminders.** A bell in the top bar shows how many reminders are due; **Notifications** lists them (Due,
  Upcoming, Resolved), and the dashboard shows due reminders in a new *Notifications* section (at the top by default;
  it can be hidden or moved with *Customize dashboard*).
  - **Personal reminders** — Budget Managers and Register Users set them for themselves; nobody else sees them.
  - **Organization reminders** — set by Budget Managers; shown to every financial user and to Auditors once due.
    Budget Managers and Register Users resolve them; Budget Users and Auditors see them read-only until they are
    cleared.
  - A reminder has a due date, optionally *show N days before*, details and a link to a Fiscal Year, budget or bank
    account. Once shown it stays until it is **resolved** (optional note); a resolved reminder can be reopened.
    It can be edited or deleted only before it is shown. One-time reminders only; no e-mail.
  - Everything is recorded in the audit log. Database migration `0012` (additive).

## 1.6.2 — 2026-10-01
Fundraiser module, part 3: the fundraiser report. Beta: test channel only. No database change.
- **CR-035 Fundraiser report.** **Report (PDF)** on a fundraiser's page (everyone who can see the fundraiser):
  event, budgets and filter; income, expenses, net and return; cash float and excluded amounts; breakdown per Fiscal
  Year; buckets; every counted transaction line; excluded lines with their reasons; then the fundraiser documents and
  the transactions' attachments reproduced.
- The same section can be added to the **End of Year Audit** and **Fiscal Year Close** reports (*Include
  fundraisers*, ticked by default when the module is on): all non-archived fundraisers with a budget in that Fiscal
  Year, after the transactions and before the signature page. A fundraiser spanning two Fiscal Years is shown complete
  in both years' reports, with that report's year marked. The Close report stored automatically when a Fiscal Year is
  closed includes them too.

## 1.6.1 — 2026-10-01
Fundraiser module, part 2: managing a fundraiser's transactions. Beta: test channel only.
- **CR-034 Managing a fundraiser** (Budget Managers and Register Users; everything is recorded in the audit log):
  - **Buckets** — sub-categories such as *Food sales* or *Raffle*. Assign a transaction line to a bucket, or split it
    across buckets by amount (*Manage* on the line). Each bucket shows income, expenses and net; whatever is not
    assigned is shown as *Unassigned*. New chart: income, expenses and net per bucket.
  - **Cash float** — mark the cash taken out for the cash box (*Cash float out*, on a withdrawal) and the float coming
    back inside a deposit (*Cash float returned*), each with an amount. Those amounts are left out of the fundraiser's
    income and expenses and shown separately.
  - **Exclude a line** that does not belong to the fundraiser (a reason is required); it can be included again.
  - **Fundraiser documents** — flyers, permits, tally sheets (PDF/JPG/PNG, 5 MB) on the fundraiser page; the
    transactions' own attachments are still listed below them.
  - Lines of a closed Fiscal Year are frozen. Removing a budget from a fundraiser drops the buckets, classifications
    and exclusions of its lines. A fundraiser with buckets, classifications, exclusions or documents can be archived
    but not deleted.
  - Database migration `0011` (additive).

## 1.6.0 — 2026-10-01
First feature release of the 1.6 line: the optional Fundraiser module (core). Beta: test channel only.
- **CR-033 Fundraiser module.** An Administrator turns it on under System/About → *Optional modules*; it then appears
  in the menu of Budget Managers, Budget Users, Register Users and Auditors (turning it off hides it and keeps the data).
  - **Budget Managers** create a fundraiser as soon as it is agreed — name, description and the event date(s); budgets
    can be added later. Up to one income and one expense budget per Fiscal Year, from at most two adjacent Fiscal
    Years: a Fiscal Year's budgets can be chosen once it is set up and open, when the event is inside it or within
    3 months of its start or end (e.g. preparation in November for a January event). A fundraiser for an event in a
    closed Fiscal Year cannot be set up; budgets of a closed Fiscal Year are frozen. Fundraisers can be archived, and
    deleted while nothing depends on them.
  - **What counts:** every active line allocated to the chosen budgets (a parent budget includes its sub-budgets),
    whatever its date; optionally only lines whose description contains a filter text (or matches a regular
    expression). Warnings for an "Other" budget, a parent budget, a filter and a budget shared with another fundraiser;
    the form previews how many lines will be included.
  - **Everyone with access** sees the fundraisers of a Fiscal Year (or *Upcoming — no Fiscal Year yet*) and each
    fundraiser's details: income, expenses, net and return, a per-Fiscal-Year breakdown, charts (cumulative income and
    expenses with the event marked; income vs expenses), every included transaction with a link to the Register, and
    the transactions' attachments.
  - Everything is recorded in the audit log. Database migration `0010` (additive).
- Register: a link can open a bank account's register with a search filled in (used by fundraiser lines).
- New dependency google-re2 (BSD) for regular-expression filters that can never hang the server.

## 1.5.0 — 2026-10-01
Polish of existing features and easier installation; nothing new in the data model except one per-user setting. Beta: test channel only.
- **Sign-in from a bookmarked page** (found testing 1.4.1): signing in — including two-step verification — now always
  happens on the dashboard address, so a bookmark such as `/about` or `/users` leads to sign-in, then two-step
  verification (or its setup), then the dashboard. A "two-step verification required" answer from the server shows the
  two-step screen instead of the login page.
- A page left open while the server is upgraded now reloads itself once to pick up the new version (API responses name
  the page build they belong to); the page itself is never cached.
- **HF-001** Right after setting up a new installation (or on a slow computer), the sign-in page could briefly appear
  and replace the security token of the new session, so the next action failed ("Missing or invalid CSRF token"). The
  page no longer flashes and a late sign-in token can no longer overwrite the session's token.
- **CR-028 Bank Accounts in two tables.** The Bank Accounts page shows *Checking & Savings* (CHECKING and SAVINGS
  accounts) and *Investments and Other* (every other type) as separate tables, each with a total of its active
  accounts. The dashboard's bank balances table uses the same two groups with a subtotal for each, then the total of
  all accounts.
- **CR-029 Preview the audit signature page.** With *Include audit review signature page* ticked, *Preview signature
  page* opens just that page as a PDF (with the chosen wording and signers) before the full report is generated.
- **CR-030 Charts fill the space.** Charts are placed in two columns that each fill from the top, so a short chart
  no longer leaves a gap next to a tall one (one column on narrow screens).
- **CR-032** The backup passphrase and its confirmation fields line up even when only one has a hint.
- **CR-031 Customize the dashboard.** Financial users and Auditors can choose which dashboard sections are shown and
  in what order: **Customize dashboard** → a checkbox and ↑/↓ buttons per section (Current Fiscal Year, Budget, Bank
  account balances, Attention, Charts and, for Auditors, Review summary). Saved for your account; **Reset to
  default** restores the standard layout. Database migration `0009` (one new column; existing users keep the
  standard layout).
- **CR-026 Windows: one file.** Every release has `Freedger-<version>-windows-x64.exe` — download and double-click
  (local mode, opens the browser; data stays in `%LOCALAPPDATA%\FinancialManagementPOC`). It is not code-signed, so
  SmartScreen may ask: *More info → Run anyway*. The portable .zip is still published. Before a release is published,
  the .exe and the .zip are started on a Windows machine and checked (health, version, web page, license).
- **CR-027 Linux: one command.** `curl -fsSL https://github.com/kretherford0983/Freeger/releases/latest/download/install.sh | sudo bash`
  installs or upgrades a server: it picks the newest production release (while in beta: the newest test
  pre-release, with a notice), verifies the checksums and runs that release's `install-server.sh` (same snapshot,
  rollback copy and untouched `config.toml` as before). `--channel`, `--version` and `--port` options; the port of an
  existing installation is read from its `config.toml`. See docs/deployment.md.
- **License: AGPL-3.0.** Freedger is now free software under the GNU Affero General Public License v3.0 (`LICENSE`).
  `THIRD-PARTY-NOTICES.txt` lists every bundled component with its license; both files are in every package. The
  sign-in page, My Account and System/About show the license and a *Source code* link to the exact commit of the
  build. Runtime dependencies, including indirect ones, are now pinned so packages contain exactly what the notices
  list (CI checks the notices are current).

## 1.4.1 — 2026-09-30
The rest of the 1.4 plan (decisions in docs/implementation-notes.md §1a). Beta: test channel only.
- **CR-016 Audit review signature page.** Reports → End of Year Audit → *Include audit review signature page* adds a
  last page with a blank date line, the wording and a signature line for up to five signers (individual Entities,
  each with an optional title, printed as "Jane Doe, Trustee"). Choose the built-in default wording, one of up to four
  saved wordings (shared by the organization, each with a Delete button) or new wording, which can be saved for future
  use. The variables {FY} (Fiscal Year dates), {ORG} (organization) and {FYE} (Fiscal Year end date) are filled in;
  unknown variables are refused. Saving and deleting wordings is recorded in the audit log.
- **CR-020 Dashboard charts.** The dashboard (financial roles and Auditors) has a *Charts* section for a chosen Fiscal
  Year: income by budget (donut), monthly expenses (bars) with income (line), expense budgets budgeted vs spent, bank
  balances at each month end (per account and total), expenses by budget (donut) and cumulative net. **Choose charts**
  shows or hides each chart; the choice is saved per user (default: the first three). Every chart has a tooltip on
  hover and a *Show data table* view. VOID transactions and transfers are left out; months follow the Fiscal Year.
- **CR-018 Two-step verification (MFA).** Sign-in asks for a 6-digit code from an authenticator app after the
  password. Setup shows a QR code and a key to type in by hand, then 10 one-time **recovery codes** (shown once; new
  ones only by setting it up again). **On a server install it is required for every user** — everyone is asked to set
  it up at their next sign-in; on a local (desktop) install it is optional. "Trust this browser for 30 days" skips the
  code on a private computer. My account → *Two-step verification*: change authenticator, remove trusted browsers.
  Users (Administrator): *Reset two-step* (reason required). A locked-out sole Administrator can be reset on the
  server with `FinancialManagementPOC reset-mfa --user NAME`. Passkeys follow in 1.6.
- **CR-023 Backup.** System/About → *Backup / Restore* (Administrators): one encrypted `.fmbak` file with the
  database, all attachments and the encryption key (not `config.toml`), protected by a passphrase you choose.
- **CR-025 Restore.** Upload a backup, enter its passphrase, your password and `RESTORE`: the current data is replaced,
  kept as a safety copy in `pre-restore/`, the application reloads itself and everyone signs in again with the
  accounts from the backup. Progress is shown step by step; any failure leaves (or puts back) the current data.
- **CR-024 Restore when setting up.** The initialization wizard offers *Restore from a backup instead*, to move an
  installation to a new server. See docs/backup-restore.md.

Upgrade notes: database migrations `0006` (table `signature_template`), `0007` (column `app_user.dashboard_charts`)
and `0008` (tables `user_mfa`, `mfa_recovery_code`, `trusted_device`; column `auth_session.mfa_pending`) are
additive. Users already signed in stay signed in; on a server install each user sets up two-step verification at their
next sign-in (have your phone ready when you first sign in after the upgrade). New folders in the data directory:
`backup-work/` (temporary) and `pre-restore/` (safety copy after a restore).

## 1.4.0 — 2026-09-30
Change requests CR-017, CR-019, CR-021 and CR-022 (decisions recorded in docs/implementation-notes.md §1a). The rest of
the 1.4 plan — audit signature page (CR-016), MFA (CR-018), dashboard charts (CR-020) and backup/restore
(CR-023 … CR-025) — follows in **1.4.1**. Beta: pre-release on the test channel only (no production release is
planned before 1.6).
- **CR-017 Documentation review.** A transaction (or split allocation) marked "no attachment will be provided" **with a
  reason** now counts as documented: it no longer appears in the Fiscal Year documentation review, the closing
  warnings or the dashboard count. A mark without a reason is still listed. Transfers (which carry the reason
  "Internal transfer between accounts") are no longer listed.
- **CR-019 Income budgets.** An income budget that received more than budgeted shows **+$X above budget** in green
  (Budgets page, dashboard, budget selector and the PDF reports) instead of a negative remaining amount, and is no
  longer an "over budget" closing warning. Expense budgets are unchanged.
- **CR-021** The dashboard's bank account balances show a **Total** of all listed accounts.
- **CR-022** **My account → About** shows the application version and build (e.g. *test build #12*) to every user.
  System/About (Administrators) shows the same plus the bind address; other users no longer receive the bind address
  and port from the About API.

## 1.3.0 — 2026-09-29
Change requests CR-007 … CR-015 (decisions recorded in docs/implementation-notes.md §1a):
- **CR-007 Fiscal Year document types.** Fiscal Year documents are *Approval document*, *Audit Signoff* or *Other*.
  Approving a Fiscal Year needs an Approval document — or the "No approval document" mark (strong warning, optional
  reason), which is then a Fiscal Year review warning. Closing needs an Audit Signoff (an "other" document no longer
  counts) and an Approval document unless the mark is set. Budget Managers can change a document's type while the
  year is open (audited); uploading an Approval document clears the mark automatically.
- **CR-008 Fiscal Year Close report.** New PDF on the Reports page: the audit report with the Fiscal Year documents
  placed after the Fiscal Year review and before the budgets and transactions. A copy is generated automatically when
  the year is closed and kept as a permanent, system-generated Fiscal Year document (if it cannot be produced the
  closing is not performed). The End of Year Audit report no longer includes the Fiscal Year documents.
- **CR-009** Split-allocation attachment lists and PDF captions are labelled "<Entity> - <Budget>"
  (e.g. "Bob Smith - 4000 Donations"; the transaction's entity is used when the allocation has none).
- **CR-010** Files can be attached while entering or editing a transaction — for the transaction and for each split
  allocation. They upload right after saving; any file that fails is named and can be added again from the register.
- **CR-011 Duplicate protection.** Every form is locked with "Saving…" while it saves; each create form sends a
  one-time request key so a repeated submit returns the record already created; a *possible duplicate* confirmation
  appears for a transaction with the same account, date, type, amount and entity. A check number can be used only once
  per account — voided checks keep their number. A wrongly entered number on a VOID record is fixed with
  **Correct check number…** (clear or change, reason required, audited, noted on the record).
- **CR-012 Missing check review.** Register → Fiscal Year reviews lists gaps in each account's check sequence (from
  the lowest to the highest recorded number; VOID records count as recorded). Resolve by entering the transaction,
  recording a zero-dollar VOID for the number, or "Confirm not missing" with a note. Gaps are a closing warning only.
  Check numbers repeated before 1.3 are listed for clean-up.
- **CR-013** The top bar and left navigation stay in place; only the page content scrolls.
- **CR-014** The left navigation collapses to icons («/»); the choice is remembered per user.
- **CR-015** The register header (title, account, buttons, filters, balances) and the column headings stay on screen
  while scrolling (normal scrolling on very small windows).

Upgrade notes: database migration `0005` is additive (new tables `request_key`, `check_number_acknowledgement`; new
columns on `attachment`, `fiscal_year`, `app_user`). Existing Fiscal Year documents become "Other": before closing an
open Fiscal Year, mark its signoff document as **Audit Signoff** (and its approval document as **Approval**).
`config.toml`, the key and attachments are not touched. See docs/upgrade.md.

## 1.2.1 — 2026-09-29
Corrections requested by the product owner after reviewing 1.2.0:
- **CR-002 — End of Year Audit PDF layout.** Page 1 is a title page; page 2 is the *Fiscal Year Review*
  introduction (activity summary per account, closure readiness, documentation review); pages 3–n list the budgets;
  then **every transaction gets at least one page** with its headline fields at the top — *Transaction date, Entity,
  Transaction type, Amount, Description, Clear Date, Notes* — and **each attachment reproduced underneath, scaled to
  the 8.5×11 page width** (images drawn; PDF attachments embedded page by page as vector content, landscape/legal
  pages scaled to fit). Every page of the report is US Letter. The transaction index page was removed. The Entity
  activity report and its CSV are unchanged.
- **CR-003 — Transfers.** The transfer form has an **Entity** field; the generated descriptions read
  `Transfer to|from <masked account> for <selected Entity>` (the organization/workspace name when no Entity is chosen),
  and the Entity is recorded on both legs. Legs remain locked together (voiding one voids both) as before.
- **CR-005 — Split documentation rule** is now exactly: if the transaction (parent) has **no** attachment **and** is
  not marked "no attachment", every allocation (child) needs an attachment **or its own "no attachment" mark**;
  if the parent has an attachment or the mark, the allocations need neither and are not reviewed.
  Split allocations therefore get their own **"No attachment will be provided for this allocation"** checkbox
  (with the same warning and optional reason); uploading a file to that allocation clears it automatically.

Upgrade notes: database migration `0004` **adds** four columns to `transaction_allocation` (per-allocation
no-attachment flag, reason, who/when); existing rows are not changed. `config.toml`, the key and attachments are
untouched. See docs/upgrade.md.

## 1.2.0 — 2026-09-29
New features (change requests CR-002 … CR-006):
- **Reports** (new menu item for all financial roles and Auditors):
  - *End of Year Audit report* — one printable PDF: Fiscal Year budget (Q1–Q4, actuals, remaining), closure/review
    summary, transaction index, then **every transaction of the year on its own page followed immediately by its
    attachments** (images rendered, PDF attachments merged page-for-page, SHA-256 verified), then the Fiscal Year
    supporting documents. Options: one account or all, include/exclude VOID. Generation is audited.
  - *Entity activity report* — deposits and withdrawals per entity for an account (or all accounts) and date range,
    with per-transaction detail, print view and CSV export. Transfers are shown separately.
- **Transfers** — "Transfer…" button in the Register records a withdrawal in the source account and a deposit in the
  destination account (linked; descriptions generated as `Transfer to|from <masked account> for <organization>`;
  Budget 0, so budgets are unaffected). Voiding either side voids both; per-side clear date and notes stay editable.
- **Searchable entity picker** in the transaction form (type to filter by name or Entity Number; keyboard friendly).
- **"No attachment will be provided" checkbox** on transactions, with a warning when ticked and an optional reason.
  Adding an attachment later clears the mark automatically (audited).
- **Documentation review** on the Fiscal Year page, in closure-readiness warnings, on the dashboard and in the audit
  report: transactions without supporting attachments and transactions marked "no attachment". Warnings only —
  never a blocker for approval or closure.
- Budget 0 is now shown as inflows/outflows (transfers post both directions).

Upgrade notes: database migration `0003` adds columns only (existing rows untouched). New runtime libraries:
reportlab, pypdf (bundled in the packages). See docs/upgrade.md.

## 1.1.1 — 2026-09-28
- **CR-001 (change request): correct the Transaction Date of a VOID transaction.** Register Users can use
  **Register → expand a VOID row → Correct date…** (API `POST /api/transactions/{id}/void-date`). Only the date changes;
  the record stays VOID with zero balance/budget effect and the change is audited (`TRANSACTION_VOID_DATE_CORRECTED`).
  For a zero-dollar VOID accountability record, its protected Budget 0 allocation follows the new date's Fiscal Year.
  Closed Fiscal Years stay immutable (a record in a closed year cannot be changed, and a record cannot be moved into one).
- Zero-dollar VOID records dated inside a Closed Fiscal Year are now refused instead of attaching to the nearest open year.
- New portable Linux build (`packaging/build_linux_portable.sh`, glibc ≥ 2.27) and server installer
  (`packaging/linux/install-server.sh`).
- No database schema change (no new migration); existing data, `config.toml` and the encryption key are untouched by the upgrade.

## 1.1.0 — 2026-09-28
- Initial implementation of the benchmark v1.1 POC.
