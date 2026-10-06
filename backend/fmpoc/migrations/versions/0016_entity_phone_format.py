"""1.6.7: phone numbers of Entities are stored in one plain form (digits; see fmpoc/phone.py).

Rewrites the existing values that are clearly a 10-digit number ("555-123-4567", "(555) 123-4567", "555.123.4567",
"1 555 123 4567", with an optional extension) to that form. Every other value is left exactly as it is. No column
is added or removed. The rule is written out here so that this migration never changes with the application code.

Revision ID: 0016_entity_phone_format
Revises: 0015_reminder_repeat
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "0016_entity_phone_format"
down_revision = "0015_reminder_repeat"
branch_labels = None
depends_on = None

_EXT = re.compile(r"\s*(?:ext\.?|x|#)\s*(\d{1,8})\s*$", re.I)


def _plain(value: str) -> str | None:
    s, ext = value.strip(), ""
    m = _EXT.search(s)
    if m:
        ext, s = "x" + m.group(1), s[:m.start()]
    if not s or re.search(r"[^0-9+().\-\s]", s) or "+" in s.strip()[1:]:
        return None
    digits = re.sub(r"\D", "", s)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    elif s.strip().startswith("+"):
        return None
    return digits + ext if len(digits) == 10 else None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, phone FROM entity WHERE phone IS NOT NULL AND phone <> ''")).fetchall()
    for entity_id, phone in rows:
        plain = _plain(phone)
        if plain and plain != phone:
            bind.execute(sa.text("UPDATE entity SET phone = :p WHERE id = :i"), {"p": plain, "i": entity_id})


def downgrade() -> None:
    pass  # the earlier spelling of a number is not kept; older versions show the plain digits
