"""1.6.7: phone numbers of Entities - typed in any common way, stored in one plain form, shown as (nnn) nnn-nnnn.

Stored form (column entity.phone):
  "5551234567"        a 10-digit number - however it was typed: 5551234567, 555-123-4567, 555.123.4567,
                      (555) 123-4567, 1 555 123 4567, +1 555 123 4567
  "5551234567x204"    the same with an extension (typed as x204, ext 204, ext. 204 or #204)
  "+442071234567"     a number from another country: typed with a leading +, kept as + and its digits
Shown as "(555) 123-4567", "(555) 123-4567 x204", "+442071234567".
"""
from __future__ import annotations

import re

HELP = ("Enter a 10-digit phone number, for example 555-123-4567. An extension (x204) and numbers from other "
        "countries starting with + are accepted.")
# 1.6.8 (#66, CodeQL "polynomial regular expression"): no leading \s* - with search() it made the match start at
# every space of a long run. Spaces left in front of the extension are dropped with the other separators below.
_EXT = re.compile(r"(?:ext\.?|x|#)\s*(\d{1,8})\s*$", re.I)
_STORED = re.compile(r"^(\d{10})(?:x(\d{1,8}))?$")


def normalize(raw: str | None) -> str | None:
    """The stored form of what was typed; None for nothing. Raises ValueError when it is not a phone number."""
    s = (raw or "").strip()
    if not s:
        return None
    ext = ""
    m = _EXT.search(s)
    if m:
        ext, s = "x" + m.group(1), s[:m.start()]
    if re.search(r"[^0-9+().\-\s]", s) or "+" in s.strip()[1:]:
        raise ValueError(HELP)
    plus = s.strip().startswith("+")
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits[0] == "1":      # US / Canada country code, with or without the +
        digits, plus = digits[1:], False
    if plus:
        if not 7 <= len(digits) <= 15 or ext:
            raise ValueError(HELP)
        return "+" + digits
    if len(digits) != 10:
        raise ValueError(HELP)
    return digits + ext


def display(stored: str | None) -> str | None:
    """(nnn) nnn-nnnn [xNNN] for a stored 10-digit number; anything else as it is stored."""
    if not stored:
        return None
    m = _STORED.match(stored)
    if not m:
        return stored
    d = m.group(1)
    return f"({d[:3]}) {d[3:6]}-{d[6:]}" + (f" x{m.group(2)}" if m.group(2) else "")
