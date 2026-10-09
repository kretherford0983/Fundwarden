"""1.10.0 (#58): the update notification."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..deps import Ctx, auth_ctx, get_db, require
from ..schemas import UpdateSettingsIn
from ..services import updates as svc

router = APIRouter(prefix="/api/updates", tags=["updates"])


@router.get("")
def status(request: Request, db: Session = Depends(get_db), ctx: Ctx = Depends(auth_ctx)):
    """Every signed-in user: whether a newer release is available, with the notes of every newer release."""
    return svc.status(db, request.app.state.settings)


@router.put("/settings")
def settings(body: UpdateSettingsIn, request: Request, db: Session = Depends(get_db),
             ctx: Ctx = Depends(require("users.manage"))):
    svc.set_enabled(db, ctx, body.enabled)
    db.commit()
    return svc.status(db, request.app.state.settings)


@router.post("/check")
def check_now(request: Request, db: Session = Depends(get_db), ctx: Ctx = Depends(require("users.manage"))):
    """Administrators: check now (when the check is on)."""
    svc.check(request.app, force=True)
    db.expire_all()
    return svc.status(db, request.app.state.settings)
