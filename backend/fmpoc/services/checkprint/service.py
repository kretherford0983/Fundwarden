"""2.0.0 (#156, #158, #159, #161, #162): Check Printing module services.

Who does what (docs/04 permission matrix):
- Administrators (checks.setup): switch the module on/off, check styles, signers and signature images, limits, test
  prints with dummy data and calibration pages. Nothing here gives them transaction, entity or bank account data
  (BR-003).
- Register Users (checks.print): choose the check style for a bank account, print checks from register transactions,
  reprint, mark spoiled, alignment tests and their own printer settings.
- Budget Managers, Budget Users and Auditors: no access. Auditors see record copies as transaction attachments.

The module stores only check printing setup (#60): styles, signers, the per-account style choice and sheet counter,
and per-user printer settings. Every payment detail belongs to the register.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import io
import json
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import audit
from ...errors import AppError, Warning_, conflict, not_found, require_confirmations, validation
from ...models import (Attachment, BankAccount, Budget, CheckAccount, CheckPrinterSetting, CheckSigner, CheckStyle,
                       RegisterTransaction, Workspace, utcnow)
from ...money import fmt
from ...security import crypto
from .. import attachments as att_svc
from .. import checks as checknum
from .. import register as reg
from ..common import budget_display_code, get_scoped
from . import config as cfgmod
from . import fonts, patterns, presets, render

SIGNATURE_AAD = b"fmpoc:check_signature:v1"
MAX_SIGNATURE_BYTES = 1024 * 1024
CHECK_COPY = "CHECK_COPY"          # Attachment.document_type of a check record copy (system generated)
MAX_STYLES = 20
MAX_SIGNERS = 10


# ------------------------------------------------------------------ module switch
def module_enabled(db: Session, ws_id: int | None) -> bool:
    ws = db.get(Workspace, ws_id) if ws_id else None
    return bool(ws and ws.checks_enabled)


def require_module(db: Session, ctx) -> None:
    if not module_enabled(db, ctx.workspace_id):
        raise AppError(404, "MODULE_DISABLED", "The Check Printing module is not turned on.")


def set_module(db: Session, ctx, enabled: bool) -> bool:
    ws = db.get(Workspace, ctx.workspace_id)
    before = bool(ws.checks_enabled)
    if before != enabled:
        ws.checks_enabled = enabled
        audit.record(db, ctx, "MODULE_ENABLED" if enabled else "MODULE_DISABLED", "module", "checks",
                     {"checks_enabled": before}, {"checks_enabled": enabled}, category="SECURITY")
    return enabled


# ------------------------------------------------------------------ check styles
def _config_error(e: ValidationError) -> AppError:
    errs = []
    for err in e.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = err.get("msg", "Invalid value.")
        msg = msg.removeprefix("Value error, ")
        errs.append({"field": loc or None, "message": msg})
    first = errs[0]["message"] if errs else "The check style settings are not valid."
    return AppError(422, "VALIDATION_ERROR", first, errors=errs)


def parse_config(data: dict) -> cfgmod.StyleConfig:
    try:
        cfg = cfgmod.parse(data)
    except ValidationError as e:
        raise _config_error(e) from None
    if cfg.memo_default:
        try:
            patterns.parse(cfg.memo_default, patterns.CHECK)
        except patterns.PatternError as e:
            raise AppError(422, "PATTERN_INVALID", f"Default memo: {e}", variable=e.variable,
                           suggestion=e.suggestion) from None
    return cfg


def style_config(s: CheckStyle) -> cfgmod.StyleConfig:
    return cfgmod.parse(json.loads(s.config_json))


def style_out(s: CheckStyle, full: bool = True) -> dict:
    cfg = style_config(s)
    out = {"id": s.id, "name": s.name, "preset_key": s.preset_key, "active": s.active,
           "checks_per_sheet": len(cfg.stock.check_tops), "sheet_usage": cfg.stock.sheet_usage,
           "feed_modes": [{"key": m.key, "label": m.label, "kind": m.kind, "note": m.note, "page": m.page,
                           "guide": m.guide, "lead": m.lead, "position": m.position} for m in cfg.feed_modes],
           "updated_at": s.updated_at.isoformat() if s.updated_at else None}
    if full:
        out["config"] = cfg.model_dump()
    return out


def _snapshot(s: CheckStyle) -> dict:
    return {"name": s.name, "active": s.active, "preset_key": s.preset_key, "config": json.loads(s.config_json)}


def list_styles(db: Session, ctx, include_inactive: bool = True) -> list[CheckStyle]:
    q = select(CheckStyle).where(CheckStyle.workspace_id == ctx.workspace_id)
    if not include_inactive:
        q = q.where(CheckStyle.active.is_(True))
    return list(db.scalars(q.order_by(CheckStyle.name, CheckStyle.id)))


def _name(name: str) -> str:
    name = (name or "").strip()
    if not name or len(name) > 80:
        raise validation("A check style name of 1 to 80 characters is required.", "name")
    return name


def _unique_name(db: Session, ctx, name: str, exclude_id: int | None = None) -> None:
    for s in list_styles(db, ctx):
        if s.id != exclude_id and s.name.lower() == name.lower():
            raise conflict("DUPLICATE_NAME", f"A check style named \"{name}\" already exists.")


def create_style(db: Session, ctx, preset_key: str, name: str | None) -> CheckStyle:
    if preset_key not in presets.PRESETS:
        raise validation("Unknown preset.", "preset_key")
    if len(list_styles(db, ctx)) >= MAX_STYLES:
        raise conflict("TOO_MANY", f"At most {MAX_STYLES} check styles can be kept.")
    name = _name(name or presets.PRESETS[preset_key]["name"])
    _unique_name(db, ctx, name)
    cfg = parse_config(presets.config_for(preset_key))
    s = CheckStyle(workspace_id=ctx.workspace_id, name=name, preset_key=preset_key, active=True,
                   config_json=json.dumps(cfg.model_dump()), created_by_user_id=ctx.user.id,
                   updated_by_user_id=ctx.user.id)
    db.add(s)
    db.flush()
    audit.record(db, ctx, "CHECK_STYLE_CREATED", "check_style", s.id, None, _snapshot(s))
    return s


def copy_style(db: Session, ctx, s: CheckStyle, name: str) -> CheckStyle:
    if len(list_styles(db, ctx)) >= MAX_STYLES:
        raise conflict("TOO_MANY", f"At most {MAX_STYLES} check styles can be kept.")
    name = _name(name)
    _unique_name(db, ctx, name)
    n = CheckStyle(workspace_id=ctx.workspace_id, name=name, preset_key=s.preset_key, active=True,
                   config_json=s.config_json, created_by_user_id=ctx.user.id, updated_by_user_id=ctx.user.id)
    db.add(n)
    db.flush()
    audit.record(db, ctx, "CHECK_STYLE_CREATED", "check_style", n.id, None, {**_snapshot(n), "copied_from": s.id})
    return n


def update_style(db: Session, ctx, s: CheckStyle, name: str, config: dict) -> CheckStyle:
    name = _name(name)
    _unique_name(db, ctx, name, s.id)
    cfg = parse_config(config)
    if cfg.default_signer_id is not None:
        signer = db.get(CheckSigner, cfg.default_signer_id)
        if signer is None or signer.workspace_id != ctx.workspace_id or not signer.active:
            raise validation("The default signer does not exist or is inactive.", "default_signer_id")
    before = _snapshot(s)
    s.name = name
    s.config_json = json.dumps(cfg.model_dump())
    s.updated_by_user_id = ctx.user.id
    s.updated_at = utcnow()
    db.flush()
    after = _snapshot(s)
    if after != before:
        audit.record(db, ctx, "CHECK_STYLE_UPDATED", "check_style", s.id, before, after)
    return s


def set_style_active(db: Session, ctx, s: CheckStyle, active: bool) -> CheckStyle:
    if s.active != active:
        before = _snapshot(s)
        s.active = active
        s.updated_by_user_id = ctx.user.id
        db.flush()
        audit.record(db, ctx, "CHECK_STYLE_ACTIVATED" if active else "CHECK_STYLE_DEACTIVATED", "check_style",
                     s.id, {"active": before["active"]}, {"active": active})
    return s


def get_style(db: Session, ctx, style_id: int) -> CheckStyle:
    return get_scoped(db, CheckStyle, style_id, ctx, "Check style")


# ------------------------------------------------------------------ signers (#159)
def signer_out(s: CheckSigner) -> dict:
    return {"id": s.id, "name": s.name, "title": s.title, "active": s.active, "has_image": bool(s.image_ciphertext),
            "image_uploaded_at": s.image_uploaded_at.isoformat() if s.image_uploaded_at else None}


def _signer_snapshot(s: CheckSigner) -> dict:
    return {"name": s.name, "title": s.title, "active": s.active, "image_sha256": s.image_sha256}


def list_signers(db: Session, ctx) -> list[CheckSigner]:
    return list(db.scalars(select(CheckSigner).where(CheckSigner.workspace_id == ctx.workspace_id)
                           .order_by(CheckSigner.name, CheckSigner.id)))


def get_signer(db: Session, ctx, signer_id: int) -> CheckSigner:
    return get_scoped(db, CheckSigner, signer_id, ctx, "Signer")


def _signer_fields(name: str, title: str | None) -> tuple[str, str | None]:
    name = (name or "").strip()
    title = (title or "").strip() or None
    if not name or len(name) > 120:
        raise validation("A signer name of 1 to 120 characters is required.", "name")
    if title and len(title) > 80:
        raise validation("The title may be at most 80 characters.", "title")
    return name, title


def normalize_signature(data: bytes) -> tuple[bytes, int, int]:
    """Validates an uploaded signature image server-side and re-encodes it (dropping metadata). PNG only."""
    if not data:
        raise validation("The file is empty.", "file")
    if len(data) > MAX_SIGNATURE_BYTES:
        raise AppError(413, "FILE_TOO_LARGE", "A signature image may not exceed 1 MB.")
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AppError(415, "UNSUPPORTED_TYPE", "The signature must be a PNG image.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(data)) as im:
            if im.format != "PNG":
                raise AppError(415, "UNSUPPORTED_TYPE", "The signature must be a PNG image.")
            w, h = im.size
            if w < 50 or h < 20 or w > 4000 or h > 2000:
                raise validation("The signature image must be between 50 x 20 and 4000 x 2000 pixels.", "file")
            im = im.convert("RGBA")
            out = io.BytesIO()
            im.save(out, "PNG", optimize=True)
    except AppError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise AppError(415, "UNSUPPORTED_TYPE", "The file is not a valid PNG image.") from None
    return out.getvalue(), w, h


def _store_image(km, s: CheckSigner, png: bytes, w: int, h: int, ctx) -> None:
    s.image_ciphertext = crypto.encrypt(km, base64.b64encode(png).decode(), aad=SIGNATURE_AAD)
    s.image_sha256 = hashlib.sha256(png).hexdigest()
    s.image_width, s.image_height = w, h
    s.image_uploaded_at = utcnow()
    s.image_uploaded_by_user_id = ctx.user.id


def create_signer(db: Session, ctx, km, name: str, title: str | None, data: bytes | None) -> CheckSigner:
    if len(list_signers(db, ctx)) >= MAX_SIGNERS:
        raise conflict("TOO_MANY", f"At most {MAX_SIGNERS} signers can be kept.")
    name, title = _signer_fields(name, title)
    s = CheckSigner(workspace_id=ctx.workspace_id, name=name, title=title, active=True, created_by_user_id=ctx.user.id)
    if data:
        png, w, h = normalize_signature(data)
        _store_image(km, s, png, w, h, ctx)
    db.add(s)
    db.flush()
    audit.record(db, ctx, "CHECK_SIGNER_CREATED", "check_signer", s.id, None, _signer_snapshot(s), category="SECURITY")
    return s


def update_signer(db: Session, ctx, s: CheckSigner, name: str, title: str | None) -> CheckSigner:
    before = _signer_snapshot(s)
    s.name, s.title = _signer_fields(name, title)
    db.flush()
    if _signer_snapshot(s) != before:
        audit.record(db, ctx, "CHECK_SIGNER_UPDATED", "check_signer", s.id, before, _signer_snapshot(s),
                     category="SECURITY")
    return s


def replace_signature(db: Session, ctx, km, s: CheckSigner, data: bytes) -> CheckSigner:
    png, w, h = normalize_signature(data)
    before = _signer_snapshot(s)
    _store_image(km, s, png, w, h, ctx)
    db.flush()
    audit.record(db, ctx, "CHECK_SIGNATURE_UPLOADED", "check_signer", s.id, before, _signer_snapshot(s),
                 category="SECURITY")
    return s


def remove_signature(db: Session, ctx, s: CheckSigner) -> CheckSigner:
    if s.image_ciphertext:
        before = _signer_snapshot(s)
        s.image_ciphertext = s.image_sha256 = None
        s.image_width = s.image_height = None
        db.flush()
        audit.record(db, ctx, "CHECK_SIGNATURE_REMOVED", "check_signer", s.id, before, _signer_snapshot(s),
                     category="SECURITY")
    return s


def set_signer_active(db: Session, ctx, s: CheckSigner, active: bool) -> CheckSigner:
    if s.active != active:
        s.active = active
        db.flush()
        audit.record(db, ctx, "CHECK_SIGNER_ACTIVATED" if active else "CHECK_SIGNER_DEACTIVATED", "check_signer",
                     s.id, {"active": not active}, {"active": active}, category="SECURITY")
    return s


def signature_png(km, s: CheckSigner) -> bytes | None:
    """Decrypted image - only ever drawn into a check or an admin test print, never returned to a client."""
    if not s.image_ciphertext:
        return None
    return base64.b64decode(crypto.decrypt(km, s.image_ciphertext, aad=SIGNATURE_AAD))


def signature_preview(km, s: CheckSigner) -> bytes:
    """A low-resolution PNG marked SAMPLE for the setup screen. The original image is never returned."""
    png = signature_png(km, s)
    if png is None:
        raise not_found("Signature image")
    with Image.open(io.BytesIO(png)) as im:
        im = im.convert("RGBA")
        im.thumbnail((220, 80))
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        d = ImageDraw.Draw(bg)
        try:
            f = ImageFont.truetype(str(fonts.file_for("SANS", True)), max(12, im.size[1] // 3))
        except OSError:  # pragma: no cover
            f = ImageFont.load_default()
        tw = d.textlength("SAMPLE", font=f)
        d.text(((bg.size[0] - tw) / 2, bg.size[1] / 3), "SAMPLE", font=f, fill=(200, 30, 30, 170))
        for y in range(0, bg.size[1], 6):
            d.line([(0, y), (bg.size[0], y)], fill=(255, 255, 255, 90))
        out = io.BytesIO()
        bg.convert("RGB").save(out, "PNG")
    return out.getvalue()


# ------------------------------------------------------------------ per-account choice and sheet counter (#156)
def account_row(db: Session, ctx, account_id: int) -> CheckAccount | None:
    return db.scalar(select(CheckAccount).where(CheckAccount.workspace_id == ctx.workspace_id,
                                                CheckAccount.bank_account_id == account_id))


def set_account_style(db: Session, ctx, acct: BankAccount, style: CheckStyle,
                      sheet_remaining: int | None = None) -> CheckAccount:
    if not style.active:
        raise conflict("STYLE_INACTIVE", "That check style is deactivated.")
    per = len(style_config(style).stock.check_tops)
    if sheet_remaining is not None and not 1 <= sheet_remaining <= per:
        raise validation(f"Checks left on the sheet must be between 1 and {per}.", "sheet_remaining")
    row = account_row(db, ctx, acct.id)
    before = None if row is None else {"check_style_id": row.check_style_id, "sheet_remaining": row.sheet_remaining}
    if row is None:
        row = CheckAccount(workspace_id=ctx.workspace_id, bank_account_id=acct.id, check_style_id=style.id)
        db.add(row)
    if row.check_style_id != style.id:
        row.check_style_id = style.id
        row.sheet_remaining = None
    if sheet_remaining is not None:
        row.sheet_remaining = sheet_remaining
    row.updated_by_user_id = ctx.user.id
    row.updated_at = utcnow()
    db.flush()
    after = {"check_style_id": row.check_style_id, "sheet_remaining": row.sheet_remaining}
    if after != before:
        audit.record(db, ctx, "CHECK_ACCOUNT_SETTINGS", "bank_account", acct.id, before, after)
    return row


def remaining(row: CheckAccount | None, cfg: cfgmod.StyleConfig) -> int:
    per = len(cfg.stock.check_tops)
    if row is None or row.sheet_remaining is None or not 1 <= row.sheet_remaining <= per:
        return per
    return row.sheet_remaining


def suggested_feed(cfg: cfgmod.StyleConfig, left: int) -> cfgmod.FeedMode:
    per = len(cfg.stock.check_tops)
    sheet_modes = [m for m in cfg.feed_modes if m.kind == "SHEET"]
    singles = [m for m in cfg.feed_modes if m.kind == "SINGLE"]
    if cfg.stock.sheet_usage == "TEAR_TOP":
        if left == 1 and per > 1 and singles:
            return singles[0]
        return next((m for m in sheet_modes if m.position == 0), sheet_modes[0])
    pos = per - left
    return next((m for m in sheet_modes if m.position == pos), sheet_modes[0])


def _consume(row: CheckAccount | None, cfg: cfgmod.StyleConfig) -> None:
    if row is None:
        return
    left = remaining(row, cfg) - 1
    row.sheet_remaining = left if left >= 1 else len(cfg.stock.check_tops)


# ------------------------------------------------------------------ personal printer settings (#162)
def printer_setting(db: Session, ctx, style_id: int, feed_key: str) -> CheckPrinterSetting | None:
    return db.scalar(select(CheckPrinterSetting).where(CheckPrinterSetting.user_id == ctx.user.id,
                                                       CheckPrinterSetting.check_style_id == style_id,
                                                       CheckPrinterSetting.feed_key == feed_key))


def printer_out(p: CheckPrinterSetting | None, feed: cfgmod.FeedMode) -> dict:
    return {"feed_key": feed.key, "page": (p.page if p and p.page else feed.page) if feed.kind == "SINGLE" else None,
            "guide": (p.guide if p and p.guide else feed.guide) if feed.kind == "SINGLE" else None,
            "dx": (p.dx_mils / 1000.0) if p else 0.0, "dy": (p.dy_mils / 1000.0) if p else 0.0,
            "customized": p is not None}


def user_adjustment(p: CheckPrinterSetting | None) -> dict:
    if p is None:
        return {}
    return {"page": p.page, "guide": p.guide, "dx": p.dx_mils / 1000.0, "dy": p.dy_mils / 1000.0}


def save_printer_setting(db: Session, ctx, style: CheckStyle, feed_key: str, page: str | None, guide: str | None,
                         dx: float, dy: float) -> CheckPrinterSetting:
    cfg = style_config(style)
    feed = cfg.feed(feed_key)
    if feed is None:
        raise validation("Unknown feed mode.", "feed_key")
    for v, name in ((dx, "dx"), (dy, "dy")):
        if not -cfgmod.PERSONAL_MAX - 1e-9 <= v <= cfgmod.PERSONAL_MAX + 1e-9:
            raise validation("A personal adjustment may be at most 1/4 inch in each direction.", name)
    if feed.kind != "SINGLE":
        page = guide = None
    if page not in (None, "LETTER", "CHECK"):
        raise validation("Unknown page option.", "page")
    if guide not in (None, "CENTER", "LEFT", "RIGHT"):
        raise validation("Unknown guide position.", "guide")
    p = printer_setting(db, ctx, style.id, feed_key)
    before = None if p is None else {"page": p.page, "guide": p.guide, "dx_mils": p.dx_mils, "dy_mils": p.dy_mils}
    if p is None:
        p = CheckPrinterSetting(workspace_id=ctx.workspace_id, user_id=ctx.user.id, check_style_id=style.id,
                                feed_key=feed_key)
        db.add(p)
    p.page, p.guide = page, guide
    p.dx_mils, p.dy_mils = int(round(dx * 1000)), int(round(dy * 1000))
    p.updated_at = utcnow()
    db.flush()
    after = {"page": p.page, "guide": p.guide, "dx_mils": p.dx_mils, "dy_mils": p.dy_mils}
    if after != before:
        audit.record(db, ctx, "CHECK_PRINTER_SETTINGS", "check_printer_setting", p.id, before,
                     {**after, "check_style_id": style.id, "feed_key": feed_key})
    return p


def reset_printer_setting(db: Session, ctx, style: CheckStyle, feed_key: str) -> None:
    p = printer_setting(db, ctx, style.id, feed_key)
    if p is not None:
        audit.record(db, ctx, "CHECK_PRINTER_SETTINGS_RESET", "check_printer_setting", p.id,
                     {"page": p.page, "guide": p.guide, "dx_mils": p.dx_mils, "dy_mils": p.dy_mils}, None)
        db.delete(p)
        db.flush()


# ------------------------------------------------------------------ transaction data
def _budget_parts(db: Session, b: Budget) -> tuple[str, str]:
    parent = db.get(Budget, b.parent_budget_id) if b.parent_budget_id else None
    if b.is_other and parent is not None:
        from .. import budgets as bsvc
        explicit, _ = bsvc.children_of(db, parent)
        if not explicit:   # a simple budget is shown as its parent (BR-020)
            return parent.parent_code, parent.name
    return budget_display_code(b, parent), b.name


def format_date(d: dt.date, fmt_key: str) -> str:
    if fmt_key == "MONTH D, YYYY":
        return f"{d.strftime('%B')} {d.day}, {d.year}"
    return d.strftime(cfgmod.DATE_FORMATS[fmt_key])


def variable_values(db: Session, t: RegisterTransaction, cfg: cfgmod.StyleConfig) -> dict[str, str]:
    allocs = t.live_allocations
    budgets = [_budget_parts(db, a.budget) for a in allocs]
    ws = db.get(Workspace, t.workspace_id)
    acct = db.get(BankAccount, t.bank_account_id)
    return {
        "PAYEE": t.parent_entity.display_name if t.parent_entity else "",
        "DATE": format_date(t.transaction_date, cfg.date_format),
        "AMOUNT": f"{t.total_cents // 100:,}.{t.total_cents % 100:02d}",
        "BUDGET": patterns.first_and_others([n for _c, n in budgets]),
        "BUDGET_CODE": patterns.first_and_others([c for c, _n in budgets]),
        "INVOICE": patterns.first_and_others([a.invoice_number for a in allocs]),
        "DESCRIPTION": patterns.first_and_others([a.description for a in allocs]),
        "NOTES": " ".join((t.notes or "").split()),
        "CHECK_NUMBER": t.check_number or "",
        "ORG": ws.name if ws else "",
        "ACCOUNT": acct.account_name if acct else "",
    }


def get_printable(db: Session, ctx, txn_id: int) -> RegisterTransaction:
    """BR-065-072, BR-057: only an active withdrawal over zero, not in a Closed Fiscal Year, can be printed."""
    t = get_scoped(db, RegisterTransaction, txn_id, ctx, "Transaction")
    if t.status != "ACTIVE":
        raise conflict("NOT_PRINTABLE", "Only active transactions can be printed as checks.")
    if t.transaction_type != "WITHDRAWAL":
        raise conflict("NOT_PRINTABLE", "Only withdrawals can be printed as checks.")
    if t.total_cents <= 0:
        raise conflict("NOT_PRINTABLE", "A check must be for more than zero.")
    if reg.is_closed_protected(db, t):
        raise conflict("FISCAL_YEAR_CLOSED", "The transaction belongs to a Closed Fiscal Year and cannot be printed.")
    return t


def record_copies(db: Session, t: RegisterTransaction) -> list[Attachment]:
    return list(db.scalars(select(Attachment).where(Attachment.transaction_id == t.id,
                                                    Attachment.document_type == CHECK_COPY,
                                                    Attachment.system_generated.is_(True))
                           .order_by(Attachment.id)))


def print_status(db: Session, t: RegisterTransaction) -> dict | None:
    copies = record_copies(db, t)
    if not copies:
        return None
    first = copies[0]
    from ...models import User
    u = db.get(User, first.uploaded_by_user_id) if first.uploaded_by_user_id else None
    return {"printed_at": first.uploaded_at.isoformat(), "printed_by": (u.display_name or u.username) if u else None,
            "copies": len(copies)}


def next_check_number(db: Session, ctx, account_id: int) -> str | None:
    nums = [checknum.numeric(n) for n in db.scalars(
        select(RegisterTransaction.check_number).where(RegisterTransaction.workspace_id == ctx.workspace_id,
                                                       RegisterTransaction.bank_account_id == account_id,
                                                       RegisterTransaction.check_number.is_not(None)))]
    nums = [n for n in nums if n is not None]
    return str(max(nums) + 1) if nums else None


# ------------------------------------------------------------------ prepare: what will print, warnings, problems
class Job(SimpleNamespace):
    """Everything needed to draw one check: the style, the placement, the fitted layout and the signature choice."""


def _signer_choice(db: Session, ctx, cfg: cfgmod.StyleConfig, cents: int, signer_id: int | None,
                   no_signature: bool) -> tuple[CheckSigner | None, str, str | None]:
    """(signer to draw or None, record-copy signature text, a notice for the print screen)."""
    over = cfg.signature_limit_cents is not None and cents > cfg.signature_limit_cents
    if over:
        return None, "NO SIGNATURE PRINTED (OVER LIMIT)", (
            f"The amount is over ${fmt(cfg.signature_limit_cents)}: the signature will not print. "
            f"Sign the check by hand.")
    if no_signature or signer_id is None:
        return None, "NO SIGNATURE PRINTED", None
    s = get_signer(db, ctx, signer_id)
    if not s.active:
        raise conflict("SIGNER_INACTIVE", "That signer is deactivated.")
    if not s.image_ciphertext:
        raise conflict("NO_SIGNATURE_IMAGE", "That signer has no signature image.")
    return s, f"SIGNATURE ON FILE: {s.name.upper()}", None


def prepare(db: Session, ctx, t: RegisterTransaction, style: CheckStyle, feed_key: str, *, memo_pattern: str | None,
            payee_text: str | None, memo_text: str | None, signer_id: int | None, no_signature: bool,
            page: str | None = None, guide: str | None = None) -> Job:
    if not style.active:
        raise conflict("STYLE_INACTIVE", "That check style is deactivated.")
    cfg = style_config(style)
    feed = cfg.feed(feed_key)
    if feed is None:
        raise validation("Unknown feed mode.", "feed_key")
    values = variable_values(db, t, cfg)
    if not values["PAYEE"]:
        raise conflict("NO_PAYEE", "The transaction has no payee. Add the payee entity in the register first.")
    pattern = cfg.memo_default if memo_pattern is None else memo_pattern
    try:
        memo = patterns.resolve(pattern, values, patterns.CHECK)
    except patterns.PatternError as e:
        raise AppError(422, "PATTERN_INVALID", f"Memo: {e}", variable=e.variable, suggestion=e.suggestion) from None
    payee_final = values["PAYEE"] if payee_text is None else " ".join(payee_text.split())
    memo_final = memo.text if memo_text is None else " ".join(memo_text.split())
    for v, name, lim in ((payee_final, "payee_text", 200), (memo_final, "memo_text", 200)):
        if len(v) > lim or any(ord(ch) < 32 for ch in v):
            raise validation("The text is too long or contains control characters.", name)
    if not payee_final:
        raise validation("The payee cannot be blank.", "payee_text")
    content = render.Content(t.total_cents, format_date(t.transaction_date, cfg.date_format), payee_final, memo_final)
    lay = render.layout(cfg, content)
    signer, sig_text, sig_notice = _signer_choice(db, ctx, cfg, t.total_cents, signer_id, no_signature)
    user = user_adjustment(printer_setting(db, ctx, style.id, feed.key))
    if page in ("LETTER", "CHECK"):
        user["page"] = page
    if guide in ("CENTER", "LEFT", "RIGHT"):
        user["guide"] = guide
    pl = render.placement_for(cfg, feed, user)
    warnings: list[Warning_] = []
    if memo.empty and memo_text is None:
        warnings.append(Warning_("EMPTY_VARIABLES", "These variables have no data for this transaction: " +
                                 ", ".join("{" + v + "}" for v in memo.empty) + ". Print the memo as shown?",
                                 variables=memo.empty, memo=memo.text))
    if t.clear_date is not None:
        warnings.append(Warning_("CLEARED", "This check has already cleared the bank. Print it anyway?"))
    return Job(t=t, style=style, cfg=cfg, feed=feed, placement=pl, layout=lay, values=values, memo=memo,
               memo_pattern=pattern, payee=payee_final, memo_text=memo_final, signer=signer, sig_text=sig_text,
               sig_notice=sig_notice, warnings=warnings, payee_overridden=payee_final != values["PAYEE"],
               memo_overridden=memo_text is not None and memo_final != memo.text)


def job_out(db: Session, job: Job) -> dict:
    fields = {}
    for name, ff in job.layout.fields.items():
        fields[name] = {"text": ff.text, "size": ff.size, "fits": ff.fits, "shrunk": ff.shrunk,
                        "suggestion": ff.suggestion, "editable": ff.editable}
    return {"fields": fields, "memo_pattern": job.memo_pattern, "memo_resolved": job.memo.text,
            "empty_variables": job.memo.empty, "payee_entity": job.values["PAYEE"],
            "signature": job.sig_text, "signature_notice": job.sig_notice,
            "warnings": [w.as_dict() for w in job.warnings], "can_print": not job.layout.problems,
            "placement": {"feed_key": job.feed.key, "page": job.placement.page, "guide": job.placement.guide,
                          "dx": round(job.placement.dx, 3), "dy": round(job.placement.dy, 3)}}


def _problems_error(job: Job) -> AppError:
    probs = [{"field": p.name, "label": cfgmod.FIELD_LABELS[p.name], "text": p.text, "suggestion": p.suggestion,
              "editable": p.editable} for p in job.layout.problems]
    names = ", ".join(p["label"] for p in probs)
    return AppError(409, "TEXT_DOES_NOT_FIT", f"Some text does not fit on the check: {names}. Accept the shortened "
                    f"version or edit it before printing.", problems=probs)


# ------------------------------------------------------------------ print, reprint, spoil (#161)
def _audit_print(job: Job) -> dict:
    return {"transaction_id": job.t.id, "check_number": job.t.check_number, "check_style_id": job.style.id,
            "feed_key": job.feed.key, "page": job.placement.page, "guide": job.placement.guide,
            "payee": job.payee, "payee_overridden": job.payee_overridden, "memo": job.memo_text,
            "memo_pattern": job.memo_pattern, "memo_overridden": job.memo_overridden,
            "amount": fmt(job.t.total_cents), "signature": job.sig_text,
            "signer_id": job.signer.id if job.signer else None}


def _record_copy(db: Session, job: Job) -> bytes:
    acct = db.get(BankAccount, job.t.bank_account_id)
    footer = [f"Record copy of check #{job.t.check_number} - transaction #{job.t.id} - "
              f"bank account {acct.account_name if acct else ''}",
              f"Check style: {job.style.name}. This copy is not a check; the signature is never stored."]
    return render.record_copy_pdf(job.cfg, job.layout, job.sig_text, footer)


def set_check_number(db: Session, ctx, t: RegisterTransaction, number: str) -> None:
    number = (number or "").strip()
    if not number or len(number) > 20:
        raise validation("Enter the check number printed on the check (up to 20 characters).", "check_number")
    if checknum.check_key(number) == checknum.check_key(t.check_number):
        return
    checknum.assert_unused(db, ctx.workspace_id, t.bank_account_id, number, exclude_id=t.id)
    before = reg.snapshot(t)
    t.check_number = number
    t.updated_by_user_id = ctx.user.id
    db.flush()
    audit.record(db, ctx, "TRANSACTION_UPDATED", "register_transaction", t.id, before,
                 {**reg.snapshot(t), "via": "check printing"})


def last_printed_number(db: Session, t: RegisterTransaction) -> str | None:
    """The check number of the latest print of this transaction (from the audit trail), or None if never printed."""
    from ...models import AuditEvent
    ev = db.scalar(select(AuditEvent).where(AuditEvent.workspace_id == t.workspace_id,
                                            AuditEvent.object_type == "register_transaction",
                                            AuditEvent.object_id == str(t.id),
                                            AuditEvent.action.in_(("CHECK_PRINTED", "CHECK_REPRINTED")))
                   .order_by(AuditEvent.id.desc()).limit(1))
    return (ev.after_snapshot or {}).get("check_number") if ev else None


def is_reprint(db: Session, t: RegisterTransaction) -> bool:
    last = last_printed_number(db, t)
    return last is not None and checknum.check_key(last) == checknum.check_key(t.check_number)


def print_check(db: Session, ctx, settings, km, job: Job, *, check_number: str | None, confirm_check_number: str,
                reprint_reason: str | None, confirmations: list[str]) -> bytes:
    """Produces the check PDF (signature included when allowed; never stored) and attaches the record copy when its
    content is new. A reprint - the same check number printed again on the same, undamaged check - needs a reason
    and does not use up a check; a damaged check is marked spoiled instead (spoil())."""
    t = job.t
    require_confirmations(job.warnings, confirmations)
    if job.layout.problems:
        raise _problems_error(job)
    if check_number is not None and checknum.check_key(check_number) != checknum.check_key(t.check_number):
        if is_reprint(db, t):
            raise conflict("CHECK_NUMBER_LOCKED", "This check was already printed with this number. If that check "
                           "was damaged, mark it spoiled to move to the next number.")
        set_check_number(db, ctx, t, check_number)
    if not t.check_number:
        raise validation("Enter the check number printed on the check loaded in the printer.", "check_number")
    if checknum.check_key(confirm_check_number) != checknum.check_key(t.check_number):
        raise AppError(409, "CHECK_NUMBER_MISMATCH", f"The number you confirmed does not match check #"
                       f"{t.check_number}. Load check #{t.check_number}, or change the check number first.")
    reprint = is_reprint(db, t)
    reason = (reprint_reason or "").strip()
    if reprint and not reason:
        raise AppError(409, "REPRINT_REASON_REQUIRED", "This check was already printed. To print it again on the "
                       "same, undamaged check, give a reason (for example \"printer jam, check undamaged\"). If the "
                       "check was damaged, mark it spoiled instead.")
    if len(reason) > 500:
        raise validation("The reason may be at most 500 characters.", "reprint_reason")
    sig_png = signature_png(km, job.signer) if job.signer else None
    pdf = render.check_pdf(job.cfg, job.placement, job.layout, sig_png)
    copy_pdf = _record_copy(db, job)
    copies = record_copies(db, t)
    new_copy = not copies or copies[-1].sha256 != hashlib.sha256(copy_pdf).hexdigest()
    path = None
    if new_copy:
        _att, path = store_transaction_document(db, ctx, settings, t, f"check-{t.check_number}-record-copy.pdf",
                                                copy_pdf)
    detail = _audit_print(job)
    if reprint:
        audit.record(db, ctx, "CHECK_REPRINTED", "register_transaction", t.id, None,
                     {**detail, "reason": reason, "new_record_copy": new_copy})
    else:
        _consume(account_row(db, ctx, t.bank_account_id), job.cfg)   # a new check was used
        audit.record(db, ctx, "CHECK_PRINTED", "register_transaction", t.id, None, detail)
    try:
        db.commit()
    except Exception:
        db.rollback()
        if path is not None:
            try:
                path.unlink()
            except OSError:
                pass
        raise
    return pdf


def store_transaction_document(db: Session, ctx, settings, t: RegisterTransaction, filename: str, data: bytes):
    key, path = att_svc._write_file(settings, data)
    att = Attachment(workspace_id=ctx.workspace_id, original_filename=att_svc.sanitize_filename(filename),
                     storage_key=key, mime_type="application/pdf", size_bytes=len(data),
                     sha256=hashlib.sha256(data).hexdigest(), uploaded_by_user_id=ctx.user.id, active=True,
                     transaction_id=t.id, document_type=CHECK_COPY, system_generated=True)
    db.add(att)
    db.flush()
    audit.record(db, ctx, "ATTACHMENT_ADDED", "attachment", att.id, None, att_svc.snapshot(att))
    if t.no_attachment:
        t.no_attachment, t.no_attachment_reason = False, None
        t.no_attachment_set_at = t.no_attachment_set_by_user_id = None
        audit.record(db, ctx, "TRANSACTION_NO_ATTACHMENT_CLEARED", "register_transaction", t.id,
                     {"no_attachment": True}, {"no_attachment": False, "attachment_id": att.id})
    return att, path


def spoil(db: Session, ctx, t: RegisterTransaction, reason: str, new_check_number: str) -> RegisterTransaction:
    """Mark the current check spoiled (damaged, or printed in the wrong place): its number becomes a zero-dollar VOID
    record in the same account (BR-072) so it is never reused, and the transaction moves to the next number."""
    reason = (reason or "").strip()
    if not reason:
        raise validation("Give a reason, for example \"misaligned print\" or \"torn in printer\".", "reason")
    if len(reason) > 400:
        raise validation("The reason may be at most 400 characters.", "reason")
    old = t.check_number
    if not old:
        raise conflict("NO_CHECK_NUMBER", "The transaction has no check number to mark spoiled.")
    new = (new_check_number or "").strip()
    if not new or checknum.check_key(new) == checknum.check_key(old):
        raise validation("Enter the number of the next check.", "new_check_number")
    set_check_number(db, ctx, t, new)
    fy_id = t.live_allocations[0].budget.fiscal_year_id if t.live_allocations else None
    void = RegisterTransaction(workspace_id=ctx.workspace_id, bank_account_id=t.bank_account_id,
                               transaction_type="WITHDRAWAL", transaction_date=t.transaction_date,
                               entry_timestamp=utcnow(), parent_entity_id=t.parent_entity_id, check_number=old,
                               status="ACTIVE", created_by_user_id=ctx.user.id, updated_by_user_id=ctx.user.id)
    checknum.assert_unused(db, ctx.workspace_id, t.bank_account_id, old)
    v = reg._create_zero_void(db, ctx, void, SimpleNamespace(
        void_reason=f"Spoiled check #{old} for transaction #{t.id}: {reason}", allocations=[], fiscal_year_id=fy_id))
    audit.record(db, ctx, "CHECK_SPOILED", "register_transaction", t.id, {"check_number": old},
                 {"check_number": new, "void_record_id": v.id, "reason": reason})
    return v


# ------------------------------------------------------------------ admin test prints (dummy data only)
SAMPLES = {
    "NORMAL": render.Content(319930, "", "SAMPLE PAYEE COMPANY INC", "51, INVOICE 12345"),
    # long enough to show shrinking, the fit warning and its suggestion on the default layout
    "LONG": render.Content(98765432, "", "THE VERY LONG NAMED SAMPLE PAYEE ORGANIZATION OF EXAMPLE COUNTY "
                           "INCORPORATED, ATTENTION ACCOUNTS PAYABLE DEPARTMENT",
                           "BUDGET 51, INVOICES 12345, 12346, 12347, 12348 AND OTHERS FOR SUPPLIES AND SERVICES "
                           "DELIVERED IN SEPTEMBER"),
}


def sample_layout(cfg: cfgmod.StyleConfig, sample: str) -> render.Layout:
    base = SAMPLES.get(sample, SAMPLES["NORMAL"])
    content = render.Content(base.cents, format_date(dt.date.today(), cfg.date_format), base.payee, base.memo)
    return render.layout(cfg, content)


def sample_out(cfg: cfgmod.StyleConfig, sample: str) -> dict:
    lay = sample_layout(cfg, sample)
    return {name: {"text": f.text, "size": f.size, "fits": f.fits, "shrunk": f.shrunk, "suggestion": f.suggestion}
            for name, f in lay.fields.items()}
