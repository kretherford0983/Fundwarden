"""1.7.3 (#88): balance history for manually updated (non-register) accounts.

Creates bank_account_balance and rebuilds the history of every existing non-register account from the audit log:
the balance recorded when it was created as non-register, every "Update balance" since, and a switch from register to
non-register - each an entry dated the day it was recorded, with its user and reason. If the last rebuilt entry does
not equal today's balance (or nothing is in the audit log), one more entry with today's balance is added: dated the
day the account was created when there is no history at all, otherwise today. The current balance does not change.
The rules are written out here so this migration never changes with the application code.

Revision ID: 0020_bank_account_balance_history
Revises: 0019_admin_roles_deleted_status
"""
import datetime as dt
import json
from decimal import Decimal, InvalidOperation

import sqlalchemy as sa
from alembic import op

revision = "0020_bank_account_balance_history"
down_revision = "0019_admin_roles_deleted_status"
branch_labels = None
depends_on = None


def _cents(v) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int((Decimal(str(v)) * 100).to_integral_value())
    except InvalidOperation:
        return None


def _snap(v) -> dict:
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v) or {}
    except (TypeError, ValueError):
        return {}


def _date(v) -> dt.date:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.datetime.fromisoformat(str(v).replace("Z", "")[:26]).date()


def upgrade() -> None:
    op.create_table(
        "bank_account_balance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("bank_account_id", sa.Integer(), sa.ForeignKey("bank_account.id"), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("balance_cents", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("source", sa.String(12), nullable=False),
        sa.Column("entered_at", sa.DateTime(), nullable=False),
        sa.Column("entered_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_bank_account_balance_workspace_id", "bank_account_balance", ["workspace_id"])
    op.create_index("ix_bank_account_balance_bank_account_id", "bank_account_balance", ["bank_account_id"])
    op.create_index("ix_bank_account_balance_account_date", "bank_account_balance", ["bank_account_id", "as_of_date"])

    bind = op.get_bind()
    now = dt.datetime.utcnow().replace(microsecond=0)
    accounts = bind.execute(sa.text(
        "SELECT id, workspace_id, manual_current_balance_cents, created_at, created_by_user_id FROM bank_account "
        "WHERE register_enabled = 0")).fetchall()
    ins = sa.text("INSERT INTO bank_account_balance (workspace_id, bank_account_id, as_of_date, balance_cents, reason, "
                  "source, entered_at, entered_by_user_id) VALUES (:w, :a, :d, :b, :r, :s, :t, :u)")
    for acct in accounts:
        events = bind.execute(sa.text(
            "SELECT action, timestamp, actor_user_id, before_snapshot, after_snapshot FROM audit_event "
            "WHERE object_type = 'bank_account' AND object_id = :i AND action IN "
            "('BANK_ACCOUNT_CREATED', 'BANK_ACCOUNT_BALANCE_UPDATED', 'BANK_ACCOUNT_UPDATED') ORDER BY timestamp, id"),
            {"i": str(acct.id)}).fetchall()
        last = None
        for ev in events:
            before, after = _snap(ev.before_snapshot), _snap(ev.after_snapshot)
            if after.get("register_enabled", False):
                continue
            value = _cents(after.get("manual_current_balance"))
            if value is None:
                continue
            if ev.action == "BANK_ACCOUNT_UPDATED" and _cents(before.get("manual_current_balance")) == value \
                    and not before.get("register_enabled", False):
                continue  # an edit that did not touch the balance
            bind.execute(ins, {"w": acct.workspace_id, "a": acct.id, "d": _date(ev.timestamp), "b": value,
                               "r": after.get("reason") if ev.action == "BANK_ACCOUNT_BALANCE_UPDATED" else None,
                               "s": "OPENING" if ev.action == "BANK_ACCOUNT_CREATED" else "UPDATE",
                               "t": ev.timestamp, "u": ev.actor_user_id})
            last = value
        current = acct.manual_current_balance_cents or 0
        if last is None or last != current:
            when = _date(acct.created_at) if last is None and acct.created_at else now.date()
            bind.execute(ins, {"w": acct.workspace_id, "a": acct.id, "d": when, "b": current,
                               "r": "Balance when balance history started (1.7.3)", "s": "UPGRADE", "t": now,
                               "u": None})


def downgrade() -> None:
    op.drop_index("ix_bank_account_balance_account_date", table_name="bank_account_balance")
    op.drop_index("ix_bank_account_balance_bank_account_id", table_name="bank_account_balance")
    op.drop_index("ix_bank_account_balance_workspace_id", table_name="bank_account_balance")
    op.drop_table("bank_account_balance")
