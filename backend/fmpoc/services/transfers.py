"""v1.2 account-to-account transfers (change request CR-003).

A transfer is recorded as two linked Register Transactions sharing `transfer_group`:
  * a WITHDRAWAL in the source account:      "Transfer to <mask of destination> for <entity>"
  * a DEPOSIT in the destination account:    "Transfer from <mask of source> for <entity>"
<entity> is the Entity selected on the transfer (v1.2.1); when none is selected the organization (workspace) name.
Both legs allocate the full amount to the protected Budget 0 of the Fiscal Year covering the date (a transfer is
non-budget activity), so budget actuals are unaffected while each account balance moves by exactly the amount.
Legs are created, voided and audited together; only Clear Date, Notes and the no-attachment flag are editable per leg.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..errors import validation
from ..models import RegisterTransaction, TransactionAllocation, Workspace, utcnow
from ..money import parse_amount
from . import bank_accounts as bank
from . import budgets as bsvc
from .register import _account_for_register, _entity, budget_zero_fiscal_year, check_clear_date, snapshot

TRANSFER_NO_ATTACHMENT_REASON = "Internal transfer between accounts"


def description(direction: str, other_mask: str, organization: str) -> str:
    return f"Transfer {direction} {other_mask} for {organization}"


def create(db: Session, ctx, data) -> list[RegisterTransaction]:
    if data.from_account_id == data.to_account_id:
        raise validation("Choose two different accounts.", "to_account_id")
    src = _account_for_register(db, ctx, data.from_account_id)
    dst = _account_for_register(db, ctx, data.to_account_id)
    try:
        cents = parse_amount(data.amount, allow_zero=False)
    except ValueError as e:
        raise validation(str(e), "amount") from None
    when = data.transaction_date or dt.date.today()
    check_clear_date(when, data.clear_date)
    fy = budget_zero_fiscal_year(db, ctx, when, data.fiscal_year_id)
    b0 = bsvc.budget_zero_for(db, fy)
    entity = _entity(db, ctx, data.entity_id, set())
    org = entity.display_name if entity is not None else db.get(Workspace, ctx.workspace_id).name
    entity_id = entity.id if entity is not None else None
    group = str(uuid.uuid4())
    legs = []
    for acct, ttype, direction, other in ((src, "WITHDRAWAL", "to", dst), (dst, "DEPOSIT", "from", src)):
        t = RegisterTransaction(
            workspace_id=ctx.workspace_id, bank_account_id=acct.id, transaction_type=ttype, transaction_date=when,
            entry_timestamp=utcnow(), clear_date=data.clear_date, parent_entity_id=entity_id, check_number=None,
            notes=data.notes, status="ACTIVE", transfer_group=group, no_attachment=True,
            no_attachment_reason=TRANSFER_NO_ATTACHMENT_REASON, no_attachment_set_at=utcnow(),
            no_attachment_set_by_user_id=ctx.user.id, created_by_user_id=ctx.user.id, updated_by_user_id=ctx.user.id)
        db.add(t)
        db.flush()
        db.add(TransactionAllocation(transaction_id=t.id, budget_id=b0.id, entity_id=entity_id, amount_cents=cents,
                                     description=description(direction, bank.masked(other), org),
                                     created_by_user_id=ctx.user.id, updated_by_user_id=ctx.user.id))
        db.flush()
        db.refresh(t)
        legs.append(t)
    for t in legs:
        audit.record(db, ctx, "TRANSFER_CREATED", "register_transaction", t.id, None,
                     {**snapshot(t), "from_account_id": src.id, "to_account_id": dst.id})
    return legs


def legs(db: Session, t: RegisterTransaction) -> list[RegisterTransaction]:
    if not t.transfer_group:
        return [t]
    return list(db.scalars(select(RegisterTransaction).where(RegisterTransaction.transfer_group == t.transfer_group,
                                                             RegisterTransaction.workspace_id == t.workspace_id)
                           .order_by(RegisterTransaction.id)))
