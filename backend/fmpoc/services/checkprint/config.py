"""2.0.0 (#156): the check style settings document. A check style has three parts:

1. stock     - the paper, where each check sits on the sheet, how the sheet is used, the outline of what is pre-printed
               (for the setup preview only, never printed);
2. fields    - where each field prints, measured once from the check's top-left corner in inches, with its font;
3. feed modes - how the paper goes into the printer, chosen at print time, each with its own small offset.

Everything is validated here, server-side (BR-094/BR-097). Positions are inches from the check's top-left corner
(x to the right, y down). Nothing may be placed in the bottom 5/8" of the check (the bank-number clear zone).
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import fonts

CLEAR_ZONE = 0.625            # bottom 5/8" of a check: the MICR (bank-number) clear band
FEED_OFFSET_MAX = 0.5         # an Administrator's per-feed-mode offset, inches
PERSONAL_MAX = 0.25           # a user's personal adjustment, inches
LETTER = (8.5, 11.0)
TEXT_FIELDS = ("date", "payee", "amount_number", "amount_words", "memo")
FIELD_LABELS = {"date": "Date", "payee": "Pay to", "amount_number": "Amount (number)",
                "amount_words": "Amount (words)", "memo": "Memo", "signature": "Signature"}
DATE_FORMATS = {"MM/DD/YYYY": "%m/%d/%Y", "MM/DD/YY": "%m/%d/%y", "YYYY-MM-DD": "%Y-%m-%d",
                "MONTH D, YYYY": "MONTH"}

Inch = Field(ge=0, le=11)


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")   # BR-098: unknown settings are refused, never stored


def _r(v: float) -> float:
    return round(float(v), 3)


class OutlineItem(_M):
    """Something pre-printed on the stock (a line, a label, a box), drawn in the setup preview only."""
    kind: Literal["LINE", "TEXT", "BOX"]
    x: float = Inch
    y: float = Inch
    x2: float | None = Field(default=None, ge=0, le=11)
    y2: float | None = Field(default=None, ge=0, le=11)
    text: str | None = Field(default=None, max_length=40)
    size: float | None = Field(default=None, ge=4, le=24)


class Stock(_M):
    paper_width: float = 8.5
    paper_height: float = 11.0
    check_width: float = Field(ge=2, le=8.5)
    check_height: float = Field(ge=1, le=11)
    check_tops: list[float] = Field(min_length=1, max_length=3)    # top of each check on the sheet, from the top edge
    sheet_usage: Literal["TEAR_TOP", "POSITIONS"] = "TEAR_TOP"
    signature_lines: Literal[1] = 1
    stock_note: str | None = Field(default=None, max_length=200)
    outline: list[OutlineItem] = Field(default_factory=list, max_length=80)

    @model_validator(mode="after")
    def _check(self):
        if (self.paper_width, self.paper_height) != LETTER:
            raise ValueError("Only Letter (8.5 x 11 in) check sheets are supported.")
        if self.check_width > self.paper_width:
            raise ValueError("The check is wider than the sheet.")
        prev_end = 0.0
        for top in self.check_tops:
            if top < prev_end - 1e-6:
                raise ValueError("Checks on the sheet overlap or are out of order.")
            if top + self.check_height > self.paper_height + 1e-6:
                raise ValueError("A check runs past the bottom of the sheet.")
            prev_end = top + self.check_height
        self.check_tops = [_r(t) for t in self.check_tops]
        return self


class Defaults(_M):
    font: str = "SANS"
    size: float = Field(default=10, ge=fonts.MIN_SIZE, le=fonts.MAX_SIZE)
    upper: bool = True

    @field_validator("font")
    @classmethod
    def _font(cls, v):
        if v not in fonts.FONTS:
            raise ValueError("Unknown font: choose one of the built-in fonts.")
        return v


class Box(_M):
    x: float = Inch
    y: float = Inch
    w: float = Field(ge=0.2, le=8.5)
    h: float = Field(ge=0.1, le=3)


class TextField(Box):
    font: str | None = None
    size: float | None = Field(default=None, ge=fonts.MIN_SIZE, le=fonts.MAX_SIZE)
    bold: bool = False
    upper: bool | None = None
    align: Literal["LEFT", "CENTER", "RIGHT"] = "LEFT"
    shrink: bool = True                                  # step the size down to fit before warning
    min_size: float = Field(default=8, ge=fonts.MIN_SIZE, le=fonts.MAX_SIZE)

    @field_validator("font")
    @classmethod
    def _font(cls, v):
        if v is not None and v not in fonts.FONTS:
            raise ValueError("Unknown font: choose one of the built-in fonts.")
        return v


class Fields(_M):
    date: TextField
    payee: TextField
    amount_number: TextField
    amount_words: TextField
    memo: TextField
    signature: Box


class AmountWords(_M):
    and_mode: Literal["CENTS", "HUNDREDS"] = "CENTS"      # bank convention: AND only before the cents
    hyphens: bool = True
    case: Literal["UPPER", "TITLE", "LOWER"] = "UPPER"
    cents: Literal["NN", "NO"] = "NN"                     # whole dollars: 00/100 or NO/100
    fill: Literal["DOTS", "DASHES", "LINE", "STARS"] = "DOTS"
    fill_placement: Literal["BETWEEN", "AFTER"] = "BETWEEN"
    trailing_word: str = Field(default="", max_length=20)

    @field_validator("trailing_word")
    @classmethod
    def _tw(cls, v):
        v = v.strip()
        if v and not re.fullmatch(r"[A-Za-z]+", v):
            raise ValueError("The trailing word may contain letters only.")
        return v


class AmountNumber(_M):
    commas: bool = True
    dollar_sign: bool = False
    lead_fill: Literal["", "*", "**", "***"] = "**"


class FeedMode(_M):
    key: str = Field(pattern=r"^[a-z0-9_]{1,20}$")
    label: str = Field(min_length=1, max_length=60)
    kind: Literal["SHEET", "SINGLE"]
    position: int = Field(default=0, ge=0, le=2)                       # SHEET: which check on the sheet (0 = top)
    lead: Literal["DATE_END", "PAYTO_END"] = "DATE_END"              # SINGLE: which end feeds first
    page: Literal["LETTER", "CHECK"] = "LETTER"                      # SINGLE: page size sent to the printer
    guide: Literal["CENTER", "LEFT", "RIGHT"] = "CENTER"             # SINGLE + LETTER: where the guides hold it
    dx: float = Field(default=0, ge=-FEED_OFFSET_MAX, le=FEED_OFFSET_MAX)   # offset in check coordinates
    dy: float = Field(default=0, ge=-FEED_OFFSET_MAX, le=FEED_OFFSET_MAX)
    note: str | None = Field(default=None, max_length=200)           # printer note, e.g. which driver profile


class StyleConfig(_M):
    stock: Stock
    defaults: Defaults = Field(default_factory=Defaults)
    fields: Fields
    amount_words: AmountWords = Field(default_factory=AmountWords)
    amount_number: AmountNumber = Field(default_factory=AmountNumber)
    date_format: Literal["MM/DD/YYYY", "MM/DD/YY", "YYYY-MM-DD", "MONTH D, YYYY"] = "MM/DD/YYYY"
    memo_default: str = Field(default="", max_length=200)
    signature_limit_cents: int | None = Field(default=None, ge=1, le=99_999_999_999)
    default_signer_id: int | None = None
    feed_modes: list[FeedMode] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def _check(self):
        cw, ch = self.stock.check_width, self.stock.check_height
        limit = ch - CLEAR_ZONE
        for name in (*TEXT_FIELDS, "signature"):
            b = getattr(self.fields, name)
            label = FIELD_LABELS[name]
            if b.x + b.w > cw + 1e-6:
                raise ValueError(f"{label}: the field runs past the right edge of the check.")
            if b.y + b.h > limit + 1e-6:
                raise ValueError(f"{label}: the field reaches into the bottom 5/8 inch of the check, which must "
                                 f"stay clear for the bank numbers.")
            for k in ("x", "y", "w", "h"):
                setattr(b, k, _r(getattr(b, k)))
            if name != "signature" and b.min_size > (b.size or self.defaults.size):
                raise ValueError(f"{label}: the smallest size is larger than the font size.")
        keys = [m.key for m in self.feed_modes]
        if len(set(keys)) != len(keys):
            raise ValueError("Each feed mode needs its own key.")
        for m in self.feed_modes:
            if m.kind == "SHEET" and m.position >= len(self.stock.check_tops):
                raise ValueError(f"Feed mode '{m.label}': there is no check at that position on the sheet.")
            if m.kind == "SINGLE" and ch > 8.5:
                raise ValueError(f"Feed mode '{m.label}': the check is too long to feed on its own.")
            m.dx, m.dy = _r(m.dx), _r(m.dy)
        if not any(m.kind == "SHEET" for m in self.feed_modes):
            raise ValueError("At least one sheet feed mode is required.")
        for o in self.stock.outline:
            for v, lim in ((o.x, cw), (o.x2, cw), (o.y, ch), (o.y2, ch)):
                if v is not None and v > lim + 1e-6:
                    raise ValueError("A stock outline item lies outside the check.")
        return self

    # --------------------------------------------------------------- helpers
    def feed(self, key: str) -> FeedMode | None:
        return next((m for m in self.feed_modes if m.key == key), None)

    def field_font(self, name: str) -> tuple[str, float, bool, bool]:
        """(font key, size, bold, upper) of a text field, with the check-wide defaults filled in."""
        f: TextField = getattr(self.fields, name)
        return (f.font or self.defaults.font, f.size or self.defaults.size, f.bold,
                self.defaults.upper if f.upper is None else f.upper)


def parse(data: dict) -> StyleConfig:
    return StyleConfig.model_validate(data)
