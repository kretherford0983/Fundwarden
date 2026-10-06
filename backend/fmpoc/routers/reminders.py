"""v1.6.3 CR-036: reminders and notifications API."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import Ctx, get_db, require
from ..schemas import ReminderIn, ReminderResolveIn
from ..services import reminders as svc

router = APIRouter(prefix="/api/reminders", tags=["reminders"])
viewer = require("reminder.view")


@router.get("")
def list_reminders(view: Literal["due", "upcoming", "resolved"] = "due", db: Session = Depends(get_db),
                   ctx: Ctx = Depends(viewer)):
    return svc.listing(db, ctx, view)


@router.get("/count")
def count(db: Session = Depends(get_db), ctx: Ctx = Depends(viewer)):
    return {"due": svc.due_count(db, ctx)}


@router.post("", status_code=201)
def create(body: ReminderIn, db: Session = Depends(get_db), ctx: Ctx = Depends(viewer)):
    r = svc.create(db, ctx, body)
    db.commit()
    return svc.out(db, ctx, r)


@router.put("/{rid}")
def update(rid: int, body: ReminderIn, db: Session = Depends(get_db), ctx: Ctx = Depends(viewer)):
    r = svc.update(db, ctx, svc.get(db, ctx, rid), body)
    db.commit()
    return svc.out(db, ctx, r)


@router.delete("/{rid}")
def delete(rid: int, db: Session = Depends(get_db), ctx: Ctx = Depends(viewer)):
    svc.delete(db, ctx, svc.get(db, ctx, rid))
    db.commit()
    return {"deleted": True}


@router.post("/{rid}/resolve")
def resolve(rid: int, body: ReminderResolveIn, db: Session = Depends(get_db), ctx: Ctx = Depends(viewer)):
    r = svc.resolve(db, ctx, svc.get(db, ctx, rid), body.note, body.stop_repeating)
    db.commit()
    return svc.out(db, ctx, r)


@router.post("/{rid}/reopen")
def reopen(rid: int, db: Session = Depends(get_db), ctx: Ctx = Depends(viewer)):
    r = svc.reopen(db, ctx, svc.get(db, ctx, rid))
    db.commit()
    return svc.out(db, ctx, r)
