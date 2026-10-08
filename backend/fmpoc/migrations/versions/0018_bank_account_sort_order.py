"""1.7.1 (#74): Budget Managers set the order in which bank accounts are listed.

Adds bank_account.sort_order. The order is kept separately for the two groups of the Bank Accounts page (Checking &
Savings; Investments and Other), so only the relative order within a group matters. The starting order of each group
is the Primary account first, then the others by name (then id), which is how the accounts were listed before, so
nothing looks different until a Budget Manager changes it. The group rule is written out here so that this migration
never changes with the application code.

Revision ID: 0018_bank_account_sort_order
Revises: 0017_user_display_name_required
"""
import sqlalchemy as sa
from alembic import op

revision = "0018_bank_account_sort_order"
down_revision = "0017_user_display_name_required"
branch_labels = None
depends_on = None

_CHECKING_SAVINGS = {"CHECKING", "SAVINGS"}


def upgrade() -> None:
    op.add_column("bank_account", sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, workspace_id, account_type, is_primary, account_name FROM bank_account")).fetchall()
    groups: dict[tuple[int, bool], list] = {}
    for r in rows:
        groups.setdefault((r.workspace_id, r.account_type in _CHECKING_SAVINGS), []).append(r)
    for members in groups.values():
        members.sort(key=lambda r: (0 if r.is_primary else 1, r.account_name or "", r.id))
        for pos, r in enumerate(members, start=1):
            bind.execute(sa.text("UPDATE bank_account SET sort_order = :p WHERE id = :i"), {"p": pos, "i": r.id})


def downgrade() -> None:
    with op.batch_alter_table("bank_account") as b:
        b.drop_column("sort_order")
