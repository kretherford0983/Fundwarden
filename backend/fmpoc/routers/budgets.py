from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import Ctx, get_db, require
from ..models import Budget, FiscalYear
from ..schemas import BudgetCreateIn, BudgetUpdateIn, ReasonIn
from ..services import budgets as svc
from ..services.common import get_scoped

router = APIRouter(prefix="/api/budgets", tags=["budgets"])


@router.get("")
def budget_tree(fiscal_year_id: int = Query(...), db: Session = Depends(get_db),
                ctx: Ctx = Depends(require("financial.view"))):
    return svc.tree(db, get_scoped(db, FiscalYear, fiscal_year_id, ctx, "Fiscal Year"),
                    include_deleted="AUDITOR" in ctx.roles)  # 1.7.3 (#52): Auditors also see deleted budgets


@router.get("/selectable")
def selectable(fiscal_year_id: int = Query(...), transaction_type: Literal["DEPOSIT", "WITHDRAWAL"] | None = None,
               db: Session = Depends(get_db), ctx: Ctx = Depends(require("financial.view"))):
    return svc.selectable(db, ctx.workspace_id, get_scoped(db, FiscalYear, fiscal_year_id, ctx, "Fiscal Year"),
                          transaction_type)


@router.get("/filter-options")
def filter_options(fiscal_year_id: int | None = None, db: Session = Depends(get_db),
                   ctx: Ctx = Depends(require("financial.view"))):
    """1.7.3 (#104): the Register's Budget filter - one Fiscal Year's budgets, or every year's."""
    fy = get_scoped(db, FiscalYear, fiscal_year_id, ctx, "Fiscal Year") if fiscal_year_id else None
    return svc.filter_options(db, ctx.workspace_id, fy)


@router.get("/continue-options")
def continue_options(fiscal_year_id: int = Query(...), budget_type: Literal["INCOME", "EXPENSE"] = Query(...),
                     level: Literal["budget", "sub-budget"] = "budget", budget_id: int | None = None,
                     db: Session = Depends(get_db), ctx: Ctx = Depends(require("financial.view"))):
    """1.8.0 (#89): budgets of earlier Fiscal Years that a budget can continue, grouped by Fiscal Year."""
    fy = get_scoped(db, FiscalYear, fiscal_year_id, ctx, "Fiscal Year")
    if budget_id is not None:
        get_scoped(db, Budget, budget_id, ctx, "Budget")
    return svc.continue_options(db, ctx.workspace_id, fy, budget_type, level == "sub-budget", budget_id)


@router.get("/{budget_id}/history")
def history(budget_id: int, db: Session = Depends(get_db), ctx: Ctx = Depends(require("financial.view"))):
    """1.8.0 (#89): the budget's lineage across Fiscal Years, oldest first."""
    return svc.lineage(db, get_scoped(db, Budget, budget_id, ctx, "Budget"))


@router.get("/{budget_id}")
def get_budget(budget_id: int, db: Session = Depends(get_db), ctx: Ctx = Depends(require("financial.view"))):
    b = get_scoped(db, Budget, budget_id, ctx, "Budget")
    return {**svc.snapshot(b), "state": svc.state(b)}


@router.post("", status_code=201)
def create(body: BudgetCreateIn, db: Session = Depends(get_db), ctx: Ctx = Depends(require("budget.manage"))):
    b = svc.create(db, ctx, body)
    db.commit()
    return {**svc.snapshot(b), "state": svc.state(b)}


def _mut(fn):
    def handler(budget_id: int, db: Session, ctx: Ctx, *args):
        b = fn(db, ctx, get_scoped(db, Budget, budget_id, ctx, "Budget"), *args)
        db.commit()
        return {**svc.snapshot(b), "state": svc.state(b)}
    return handler


@router.patch("/{budget_id}")
def update(budget_id: int, body: BudgetUpdateIn, db: Session = Depends(get_db), ctx: Ctx = Depends(require("budget.manage"))):
    return _mut(svc.update)(budget_id, db, ctx, body)


@router.post("/{budget_id}/delete")
def delete(budget_id: int, body: ReasonIn, db: Session = Depends(get_db), ctx: Ctx = Depends(require("budget.delete"))):
    """1.7.3 (#52): Budget Admin - status Deleted, only in a Fiscal Year that is not approved."""
    return _mut(svc.delete)(budget_id, db, ctx, body.reason)


@router.post("/{budget_id}/reject")
def reject(budget_id: int, body: ReasonIn, db: Session = Depends(get_db), ctx: Ctx = Depends(require("budget.manage"))):
    return _mut(svc.reject)(budget_id, db, ctx, body.reason)


@router.post("/{budget_id}/inactivate")
def inactivate(budget_id: int, body: ReasonIn, db: Session = Depends(get_db), ctx: Ctx = Depends(require("budget.manage"))):
    return _mut(svc.inactivate)(budget_id, db, ctx, body.reason)


@router.post("/{budget_id}/unlock")
def unlock(budget_id: int, body: ReasonIn, db: Session = Depends(get_db), ctx: Ctx = Depends(require("budget.manage"))):
    return _mut(svc.unlock)(budget_id, db, ctx, body.reason)


@router.post("/{budget_id}/lock")
def lock(budget_id: int, db: Session = Depends(get_db), ctx: Ctx = Depends(require("budget.manage"))):
    return _mut(svc.lock)(budget_id, db, ctx)
