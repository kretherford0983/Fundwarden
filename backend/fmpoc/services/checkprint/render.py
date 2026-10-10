"""2.0.0 (#157): drawing check PDFs.

Coordinates: settings are inches from the check's top-left corner (x right, y down). Drawing happens in "check space":
points, origin at the check's bottom-left corner, y up (ReportLab's convention), after a page transform for the feed
mode:

- SHEET   Letter portrait; the check is drawn at its position on the sheet.
- SINGLE  the check is turned so the end that feeds first is at the top of the page: "date end first" turns it 90
          degrees counter-clockwise, "pay-to end first" 90 degrees clockwise. The page is either check-sized or
          Letter with the check placed where the manual-feed guides hold it (centered, left or right).

The feed mode's offset and the user's personal adjustment are applied last, in check coordinates (dx right, dy down).

Text sits on the bottom of its box: baseline = box bottom + the font's descent, so a box placed on a pre-printed
line puts the writing on the line. Nothing is drawn in the bottom 5/8" of the check (config.CLEAR_ZONE) except on
plain-paper test pages, which shade it.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from . import amounts, fonts
from .config import CLEAR_ZONE, FIELD_LABELS, TEXT_FIELDS, FeedMode, StyleConfig

PT = 72.0
ELLIPSIS = "…"
WORDS_GAP = 0.06          # inches between "AND" / the cents and the protective fill
MIN_FILL = 0.25           # the fill is never shorter than this
SHRINK_STEP = 0.5         # points


# ------------------------------------------------------------------ content and fitting
@dataclass
class Content:
    """What prints on the check. Amount texts are generated from `cents`; nothing here is typed by the user except
    payee/memo text the user accepted after a fit warning."""
    cents: int
    date_text: str
    payee: str
    memo: str


@dataclass
class FieldFit:
    name: str
    text: str
    size: float
    fits: bool
    shrunk: bool = False
    suggestion: str | None = None      # a shortened version that fits (payee and memo only)
    editable: bool = False


@dataclass
class Layout:
    fields: dict[str, FieldFit] = field(default_factory=dict)
    words: amounts.WordsParts | None = None
    number: str = ""

    @property
    def problems(self) -> list[FieldFit]:
        return [f for f in self.fields.values() if not f.fits]


def _cased(text: str, upper: bool) -> str:
    return text.upper() if upper else text


def _fits(text: str, key: str, size: float, bold: bool, width_pt: float) -> bool:
    return fonts.width(text, key, size, bold) <= width_pt + 0.01


def _sizes(f, size: float) -> list[float]:
    out = [size]
    if f.shrink:
        s = size - SHRINK_STEP
        while s >= f.min_size - 1e-6:
            out.append(round(s, 2))
            s -= SHRINK_STEP
    return out


def _shorten(text: str, key: str, size: float, bold: bool, width_pt: float) -> str:
    """Longest prefix (cut at a word boundary when possible) plus an ellipsis that fits."""
    words = text.split(" ")
    while len(words) > 1:
        words.pop()
        cand = " ".join(words).rstrip(" ,;:-") + ELLIPSIS
        if _fits(cand, key, size, bold, width_pt):
            return cand
    s = text
    while s:
        s = s[:-1]
        cand = s.rstrip() + ELLIPSIS
        if _fits(cand, key, size, bold, width_pt):
            return cand
    return ""


def _words_width(parts: amounts.WordsParts, key: str, size: float, bold: bool, placement: str) -> float:
    w = fonts.width(parts.words, key, size, bold) + fonts.width(parts.cents, key, size, bold)
    if parts.trailing:
        w += fonts.width(" " + parts.trailing, key, size, bold)
    if placement == "AFTER":
        w += fonts.width(" ", key, size, bold)
    return w + (2 * WORDS_GAP + MIN_FILL) * PT


def layout(cfg: StyleConfig, content: Content) -> Layout:
    """Fits every field into its box. A field that does not fit even at its smallest size is a problem: payee and
    memo get a suggested shortened version (the user accepts it or edits the text); the date and the amounts can
    never be changed, so printing is blocked."""
    out = Layout()
    for name in ("date", "payee", "memo", "amount_number"):
        f = getattr(cfg.fields, name)
        key, size, bold, upper = cfg.field_font(name)
        if name == "amount_number":
            text = amounts.number_text(content.cents, cfg.amount_number.model_dump())
            out.number = text
        else:
            text = _cased({"date": content.date_text, "payee": content.payee, "memo": content.memo}[name], upper)
        wpt = f.w * PT
        editable = name in ("payee", "memo")
        chosen = next((s for s in _sizes(f, size) if _fits(text, key, s, bold, wpt)), None)
        if chosen is not None:
            out.fields[name] = FieldFit(name, text, chosen, True, shrunk=chosen < size, editable=editable)
        else:
            smallest = _sizes(f, size)[-1]
            sug = _shorten(text, key, smallest, bold, wpt) if editable and text else None
            out.fields[name] = FieldFit(name, text, smallest, False, suggestion=sug, editable=editable)
    # amount in words
    f = cfg.fields.amount_words
    key, size, bold, upper = cfg.field_font("amount_words")
    parts = amounts.words_parts(content.cents, cfg.amount_words.model_dump())
    out.words = parts
    wpt = f.w * PT
    chosen = next((s for s in _sizes(f, size)
                   if _words_width(parts, key, s, bold, cfg.amount_words.fill_placement) <= wpt + 0.01), None)
    full = f"{parts.words} {parts.cents}" + (f" {parts.trailing}" if parts.trailing else "")
    out.fields["amount_words"] = FieldFit("amount_words", full, chosen or _sizes(f, size)[-1], chosen is not None,
                                          shrunk=bool(chosen and chosen < size))
    return out


# ------------------------------------------------------------------ page transforms
@dataclass
class Placement:
    feed: FeedMode
    page: str = "LETTER"           # SINGLE: LETTER | CHECK (after the user's printer settings)
    guide: str = "CENTER"
    dx: float = 0.0                # total offset in inches, check coordinates (feed offset + personal adjustment)
    dy: float = 0.0


def placement_for(cfg: StyleConfig, feed: FeedMode, user: dict | None = None) -> Placement:
    user = user or {}
    return Placement(feed, page=user.get("page") or feed.page, guide=user.get("guide") or feed.guide,
                     dx=feed.dx + user.get("dx", 0.0), dy=feed.dy + user.get("dy", 0.0))


def _begin_page(c, cfg: StyleConfig, pl: Placement) -> None:
    cw, ch = cfg.stock.check_width, cfg.stock.check_height
    pw, ph = cfg.stock.paper_width, cfg.stock.paper_height
    feed = pl.feed
    if feed.kind == "SHEET":
        c.setPageSize((pw * PT, ph * PT))
        top = cfg.stock.check_tops[feed.position]
        c.translate((pw - cw) / 2 * PT, (ph - top - ch) * PT)
    else:
        if pl.page == "CHECK":
            c.setPageSize((ch * PT, cw * PT))
            gx, strip_top = 0.0, cw
        else:
            c.setPageSize((pw * PT, ph * PT))
            gx = {"LEFT": 0.0, "RIGHT": pw - ch}.get(pl.guide, (pw - ch) / 2)
            strip_top = ph
        if feed.lead == "DATE_END":       # right end of the check at the top of the page
            c.translate((gx + ch) * PT, (strip_top - cw) * PT)
            c.rotate(90)
        else:                             # left end at the top
            c.translate(gx * PT, strip_top * PT)
            c.rotate(-90)
    c.translate(pl.dx * PT, -pl.dy * PT)


def _y(cfg: StyleConfig, y_in: float) -> float:
    """Check-space y (points, up) of a distance y_in measured down from the check's top edge."""
    return (cfg.stock.check_height - y_in) * PT


# ------------------------------------------------------------------ drawing helpers
def _baseline(cfg: StyleConfig, box, key: str, size: float, bold: bool) -> float:
    return _y(cfg, box.y + box.h) + fonts.descent(key, size, bold)


def _text(c, cfg, box, text: str, key: str, size: float, bold: bool, align: str) -> None:
    c.setFont(fonts.ps_name(key, bold), size)
    w = fonts.width(text, key, size, bold)
    x = box.x * PT
    if align == "RIGHT":
        x = (box.x + box.w) * PT - w
    elif align == "CENTER":
        x = box.x * PT + (box.w * PT - w) / 2
    c.drawString(x, _baseline(cfg, box, key, size, bold), text)


def _fill(c, style: str, x0: float, x1: float, y: float, size: float, key: str, bold: bool) -> None:
    """The protective fill, drawn (not typed) centered at half the capital height so nothing can be written above or
    below it. y is the baseline; x0..x1 in points."""
    if x1 - x0 <= 0:
        return
    mid = y + fonts.cap_height(key, size, bold) / 2
    c.saveState()
    if style == "LINE":
        c.setLineWidth(0.07 * size)
        c.line(x0, mid, x1, mid)
    elif style == "DASHES":
        dash, gap = 0.4 * size, 0.15 * size
        c.setLineWidth(0.08 * size)
        n = max(1, int((x1 - x0 + gap) // (dash + gap)))
        step = (x1 - x0 - n * dash) / max(n - 1, 1) + dash if n > 1 else 0
        for i in range(n):
            a = x0 + i * step
            c.line(a, mid, min(a + dash, x1), mid)
    elif style == "STARS":
        c.setFont(fonts.ps_name(key, bold), size)
        sw = fonts.width("*", key, size, bold)
        n = max(1, int((x1 - x0) // sw))
        # the asterisk glyph sits high; move it so its middle is at half the capital height
        c.drawString(x0 + ((x1 - x0) - n * sw) / 2, mid - 0.58 * size, "*" * n)
    else:  # DOTS: tighter than typed periods
        r, pitch = 0.045 * size, 0.22 * size
        n = max(2, int((x1 - x0 - 2 * r) // pitch) + 1)
        step = (x1 - x0 - 2 * r) / (n - 1)
        for i in range(n):
            c.circle(x0 + r + i * step, mid, r, stroke=0, fill=1)
    c.restoreState()


def _amount_words(c, cfg: StyleConfig, lay: Layout) -> None:
    f = cfg.fields.amount_words
    key, _size, bold, _upper = cfg.field_font("amount_words")
    size = lay.fields["amount_words"].size
    parts = lay.words
    c.setFont(fonts.ps_name(key, bold), size)
    base = _baseline(cfg, f, key, size, bold)
    left, right = f.x * PT, (f.x + f.w) * PT
    trailing_w = fonts.width(" " + parts.trailing, key, size, bold) if parts.trailing else 0.0
    cents_w = fonts.width(parts.cents, key, size, bold)
    words_w = fonts.width(parts.words, key, size, bold)
    gap = WORDS_GAP * PT
    if parts.trailing:
        c.drawString(right - trailing_w + fonts.width(" ", key, size, bold), base, parts.trailing)
    if cfg.amount_words.fill_placement == "BETWEEN":
        c.drawString(left, base, parts.words)
        cents_x = right - trailing_w - cents_w
        c.drawString(cents_x, base, parts.cents)
        _fill(c, cfg.amount_words.fill, left + words_w + gap, cents_x - gap, base, size, key, bold)
    else:
        text = f"{parts.words} {parts.cents}"
        c.drawString(left, base, text)
        _fill(c, cfg.amount_words.fill, left + fonts.width(text, key, size, bold) + gap, right - trailing_w - gap,
              base, size, key, bold)


def _fields(c, cfg: StyleConfig, lay: Layout) -> None:
    c.setFillGray(0)
    for name in ("date", "payee", "memo", "amount_number"):
        ff = lay.fields[name]
        key, _s, bold, _u = cfg.field_font(name)
        box = getattr(cfg.fields, name)
        if ff.text:
            _text(c, cfg, box, ff.text, key, ff.size, bold, box.align)
    _amount_words(c, cfg, lay)


def _signature_image(c, cfg: StyleConfig, png: bytes) -> None:
    box = cfg.fields.signature
    img = ImageReader(io.BytesIO(png))
    iw, ih = img.getSize()
    bw, bh = box.w * PT, box.h * PT
    scale = min(bw / iw, bh / ih)
    w, h = iw * scale, ih * scale
    x = box.x * PT + (bw - w) / 2
    y = _y(cfg, box.y + box.h) + (bh - h) / 2
    c.drawImage(img, x, y, w, h, mask="auto")


def _signature_text(c, cfg: StyleConfig, text: str) -> None:
    box = cfg.fields.signature
    c.saveState()
    c.setFont(fonts.ps_name("SANS", True), 8)
    w = fonts.width(text, "SANS", 8, True)
    size = 8 if w <= box.w * PT else max(5.0, 8 * box.w * PT / w)
    c.setFont(fonts.ps_name("SANS", True), size)
    c.drawCentredString((box.x + box.w / 2) * PT, _y(cfg, box.y + box.h / 2) - size / 3, text)
    c.restoreState()


def _signature_outline(c, cfg: StyleConfig) -> None:
    box = cfg.fields.signature
    c.saveState()
    c.setDash(3, 2)
    c.setLineWidth(0.6)
    c.rect(box.x * PT, _y(cfg, box.y + box.h), box.w * PT, box.h * PT, stroke=1, fill=0)
    c.setFont(fonts.ps_name("SANS"), 7)
    c.drawCentredString((box.x + box.w / 2) * PT, _y(cfg, box.y + box.h / 2) - 2.5, "SIGNATURE")
    c.restoreState()


def _check_outline(c, cfg: StyleConfig, gray: float = 0.55) -> None:
    c.saveState()
    c.setStrokeGray(gray)
    c.setLineWidth(0.5)
    c.rect(0, 0, cfg.stock.check_width * PT, cfg.stock.check_height * PT, stroke=1, fill=0)
    c.restoreState()


def _stock_outline(c, cfg: StyleConfig, gray: float = 0.7) -> None:
    """The pre-printed lines and labels of the stock (record copy only - never on a real check)."""
    c.saveState()
    c.setStrokeGray(gray)
    c.setFillGray(gray)
    c.setLineWidth(0.5)
    for o in cfg.stock.outline:
        if o.kind == "LINE" and o.x2 is not None and o.y2 is not None:
            c.line(o.x * PT, _y(cfg, o.y), o.x2 * PT, _y(cfg, o.y2))
        elif o.kind == "BOX" and o.x2 is not None and o.y2 is not None:
            c.rect(o.x * PT, _y(cfg, o.y2), (o.x2 - o.x) * PT, (o.y2 - o.y) * PT, stroke=1, fill=0)
        elif o.kind == "TEXT" and o.text:
            c.setFont(fonts.ps_name("SANS"), o.size or 8)
            c.drawString(o.x * PT, _y(cfg, o.y), o.text)
    c.restoreState()


def _clear_zone(c, cfg: StyleConfig) -> None:
    c.saveState()
    c.setFillGray(0.88)
    c.rect(0, 0, cfg.stock.check_width * PT, CLEAR_ZONE * PT, stroke=0, fill=1)
    c.setFillGray(0.35)
    c.setFont(fonts.ps_name("SANS"), 6.5)
    c.drawString(0.15 * PT, CLEAR_ZONE * PT - 9, "BANK NUMBER ZONE - NOTHING PRINTS HERE")
    c.restoreState()


def _crosshair(c, x: float, y: float, r: float = 6) -> None:
    c.line(x - r, y, x + r, y)
    c.line(x, y - r, x, y + r)


def _field_marks(c, cfg: StyleConfig, labels: bool) -> None:
    """Crosshairs at each field's bottom-left (where the writing starts) and a light box outline."""
    c.saveState()
    c.setLineWidth(0.4)
    for name in (*TEXT_FIELDS, "signature"):
        b = getattr(cfg.fields, name)
        c.setStrokeGray(0.6)
        c.setDash(1, 2)
        c.rect(b.x * PT, _y(cfg, b.y + b.h), b.w * PT, b.h * PT, stroke=1, fill=0)
        c.setDash()
        c.setStrokeGray(0)
        _crosshair(c, b.x * PT, _y(cfg, b.y + b.h))
        if labels:
            c.setFillGray(0.3)
            c.setFont(fonts.ps_name("SANS"), 5.5)
            c.drawString(b.x * PT + 2, _y(cfg, b.y) + 1.5, f"{FIELD_LABELS[name]}  x {b.x:.3f}  y {b.y:.3f}")
    c.restoreState()


def _rulers(c, cfg: StyleConfig) -> None:
    """Inch rulers along the check's top and left edges (1/8 inch ticks)."""
    cw, ch = cfg.stock.check_width, cfg.stock.check_height
    c.saveState()
    c.setLineWidth(0.4)
    c.setFont(fonts.ps_name("SANS"), 5.5)
    for i in range(int(cw * 8) + 1):
        x = i / 8 * PT
        ln = 9 if i % 8 == 0 else 5 if i % 4 == 0 else 3
        c.line(x, ch * PT, x, ch * PT - ln)
        if i % 8 == 0 and 0 < i < cw * 8:
            c.drawCentredString(x, ch * PT - 15, str(i // 8))
    for i in range(int(ch * 8) + 1):
        y = ch * PT - i / 8 * PT
        ln = 9 if i % 8 == 0 else 5 if i % 4 == 0 else 3
        c.line(0, y, ln, y)
        if i % 8 == 0 and 0 < i < ch * 8:
            c.drawString(11, y - 2, str(i // 8))
    c.restoreState()


SCALE_TEXT = "If this line is not exactly 5 inches, set the print scale to 100% / Actual size."


def _scale_check(c, x_in: float, y_from_bottom_in: float) -> None:
    """Two marks exactly 5.000 inches apart (in check space)."""
    x0, x1, y = x_in * PT, (x_in + 5) * PT, y_from_bottom_in * PT
    c.saveState()
    c.setLineWidth(0.8)
    c.line(x0, y, x1, y)
    c.line(x0, y - 6, x0, y + 6)
    c.line(x1, y - 6, x1, y + 6)
    c.setFont(fonts.ps_name("SANS", True), 6.5)
    c.drawCentredString((x0 + x1) / 2, y + 3, "5.000 in")
    c.setFont(fonts.ps_name("SANS"), 6)
    c.drawCentredString((x0 + x1) / 2, y - 9, SCALE_TEXT)
    c.restoreState()


def _diagonal(c, cfg: StyleConfig, text: str, gray: float = 0.75, size: float = 30) -> None:
    c.saveState()
    c.setFillGray(gray)
    c.setFont(fonts.ps_name("SANS", True), size)
    c.translate(cfg.stock.check_width / 2 * PT, cfg.stock.check_height / 2 * PT)
    c.rotate(18)
    c.drawCentredString(0, -size / 3, text)
    c.restoreState()


def _border_note(c, cfg: StyleConfig, text: str) -> None:
    c.saveState()
    c.setFont(fonts.ps_name("SANS", True), 7)
    c.setFillGray(0.2)
    c.drawRightString(cfg.stock.check_width * PT - 6, cfg.stock.check_height * PT - 8, text)
    c.restoreState()


def _new_canvas(buf, title: str):
    c = rl_canvas.Canvas(buf, pageCompression=1, invariant=1)
    c.setTitle(title)
    c.setCreator("PennyWarden")
    # Ask PDF viewers to print at actual size (Chromium and Adobe Reader honour it; the scale check covers the rest)
    try:
        c.setViewerPreference("PrintScaling", "None")
    except Exception:  # pragma: no cover - older ReportLab
        pass
    return c


# ------------------------------------------------------------------ public renderers
def check_pdf(cfg: StyleConfig, pl: Placement, lay: Layout, signature_png: bytes | None) -> bytes:
    """The real check: fields and (when allowed) the signature. Never stored."""
    _assert_fits(lay)
    buf = io.BytesIO()
    c = _new_canvas(buf, "Check")
    _begin_page(c, cfg, pl)
    _fields(c, cfg, lay)
    if signature_png:
        _signature_image(c, cfg, signature_png)
    c.showPage()
    c.save()
    return buf.getvalue()


def test_pdf(cfg: StyleConfig, pl: Placement, lay: Layout, signature_png: bytes | None) -> bytes:
    """Administrator test print with dummy data: like the real check plus TEST - NOT A CHECK, the scale check and
    the field marks. The signature is an outlined box unless a test signature was chosen."""
    buf = io.BytesIO()
    c = _new_canvas(buf, "Test print")
    _begin_page(c, cfg, pl)
    _check_outline(c, cfg)
    _diagonal(c, cfg, "TEST - NOT A CHECK", gray=0.8)
    _fields_safe(c, cfg, lay)
    if signature_png:
        _signature_image(c, cfg, signature_png)
        _diagonal(c, cfg, "TEST - NOT A CHECK", gray=0.55, size=22)   # crosses the signature too
    else:
        _signature_outline(c, cfg)
    _scale_check(c, 0.5, cfg.stock.check_height - 0.42)
    _border_note(c, cfg, "TEST - NOT A CHECK")
    c.showPage()
    c.save()
    return buf.getvalue()


def alignment_pdf(cfg: StyleConfig, pl: Placement, lay: Layout) -> bytes:
    """A Register User's test print of the actual check on plain paper: real field text, crosshairs, the check
    outline, the shaded clear zone and the scale check - never the signature image."""
    buf = io.BytesIO()
    c = _new_canvas(buf, "Alignment test")
    _begin_page(c, cfg, pl)
    _check_outline(c, cfg, 0.2)
    _clear_zone(c, cfg)
    _field_marks(c, cfg, labels=False)
    _fields_safe(c, cfg, lay)
    _signature_outline(c, cfg)
    _scale_check(c, 0.5, cfg.stock.check_height - 0.42)
    _border_note(c, cfg, "ALIGNMENT TEST - NOT A CHECK")
    c.showPage()
    c.save()
    return buf.getvalue()


def calibration_pdf(cfg: StyleConfig, pl: Placement) -> bytes:
    """Rulers, crosshairs and the field boxes with their positions, the clear zone and the scale check."""
    buf = io.BytesIO()
    c = _new_canvas(buf, "Calibration page")
    _begin_page(c, cfg, pl)
    _check_outline(c, cfg, 0.2)
    _clear_zone(c, cfg)
    _rulers(c, cfg)
    _field_marks(c, cfg, labels=True)
    _signature_outline(c, cfg)
    _scale_check(c, 0.5, cfg.stock.check_height - 0.42)
    _border_note(c, cfg, "CALIBRATION PAGE - NOT A CHECK")
    c.showPage()
    c.save()
    return buf.getvalue()


def scale_pdf() -> bytes:
    """Printer setup assistant step 1: a Letter page with the 5-inch scale check only."""
    buf = io.BytesIO()
    c = _new_canvas(buf, "Scale check")
    c.setPageSize((8.5 * PT, 11 * PT))
    c.setFont(fonts.ps_name("SANS", True), 14)
    c.drawCentredString(4.25 * PT, 9.5 * PT, "PennyWarden - print scale check")
    c.setFont(fonts.ps_name("SANS"), 10)
    c.drawCentredString(4.25 * PT, 9.15 * PT, "Measure the line below with a ruler.")
    _scale_check(c, 1.75, 8.0)
    c.setFont(fonts.ps_name("SANS"), 9)
    c.drawCentredString(4.25 * PT, 7.4 * PT, "Exactly 5 inches: your browser prints at actual size.")
    c.drawCentredString(4.25 * PT, 7.15 * PT, "Shorter or longer: change Scale to 100% / Actual size in the print "
                                              "dialog and print this page again.")
    c.showPage()
    c.save()
    return buf.getvalue()


def record_copy_pdf(cfg: StyleConfig, lay: Layout, signature_text: str, footer: list[str]) -> bytes:
    """The copy attached to the transaction: the check as printed (Letter page, check at the top, the stock outline in
    light grey), the signature replaced by text, and COPY - NOT NEGOTIABLE. Never contains the signature image."""
    buf = io.BytesIO()
    c = _new_canvas(buf, "Check record copy")
    c.setPageSize((8.5 * PT, 11 * PT))
    c.saveState()
    c.translate((8.5 - cfg.stock.check_width) / 2 * PT, (11 - 0.5 - cfg.stock.check_height) * PT)
    _check_outline(c, cfg, 0.4)
    _diagonal(c, cfg, "COPY - NOT NEGOTIABLE", gray=0.86, size=28)   # under the text, so the copy stays readable
    _stock_outline(c, cfg)
    _fields(c, cfg, lay)
    _signature_text(c, cfg, signature_text)
    c.restoreState()
    c.setFont(fonts.ps_name("SANS"), 8)
    y = (11 - 0.5 - cfg.stock.check_height - 0.35) * PT
    for line in footer:
        c.drawString(0.5 * PT, y, line)
        y -= 11
    c.showPage()
    c.save()
    return buf.getvalue()


def _fields_safe(c, cfg: StyleConfig, lay: Layout) -> None:
    """Fields for test pages: a field that does not fit is drawn at its smallest size so the overflow is visible."""
    _fields(c, cfg, lay)


class NotFitting(Exception):
    pass


def _assert_fits(lay: Layout) -> None:
    if lay.problems:
        raise NotFitting(", ".join(FIELD_LABELS[p.name] for p in lay.problems))
