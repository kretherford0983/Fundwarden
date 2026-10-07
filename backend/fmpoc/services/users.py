"""User administration (Administrator only) with security-domain separation (BR-002)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..errors import AppError, conflict, validation
from ..models import Role, User, UserRole, utcnow
from ..permissions import ADMINISTRATOR, validate_role_set
from ..security.passwords import hash_password, policy_errors
from .auth import revoke_user_sessions
from .common import get_scoped


def snapshot(u: User) -> dict:
    return {"id": u.id, "username": u.username, "email": u.email, "display_name": u.display_name, "active": u.active,
            "security_domain": u.security_domain, "roles": sorted(u.role_codes)}


def out(u: User) -> dict:
    return {**snapshot(u), "created_at": u.created_at.isoformat() + "Z",
            "password_changed_at": u.password_changed_at.isoformat() + "Z" if u.password_changed_at else None}


def _active_admin_count(db: Session, ws_id: int) -> int:
    return db.scalar(select(func.count(User.id)).join(UserRole, UserRole.user_id == User.id)
                     .join(Role, Role.id == UserRole.role_id)
                     .where(User.workspace_id == ws_id, User.active.is_(True), Role.code == ADMINISTRATOR)) or 0


def _set_roles(db: Session, u: User, codes: set[str]) -> None:
    roles = {r.code: r for r in db.scalars(select(Role))}
    for ur in db.scalars(select(UserRole).where(UserRole.user_id == u.id)):
        db.delete(ur)  # role assignment rows are security configuration, not business records; changes audited
    db.flush()
    for c in sorted(codes):
        db.add(UserRole(user_id=u.id, role_id=roles[c].id))
    db.flush()
    db.expire(u, ["roles"])


def _pw_check(pw: str, username: str) -> None:
    errs = policy_errors(pw, username)
    if errs:
        raise AppError(422, "PASSWORD_POLICY", " ".join(errs), errors=[{"field": "password", "message": e} for e in errs])


DISPLAY_NAME_MIN = 3


def clean_display_name(value: str | None) -> str:
    """1.7.1 (#47): every user has a display name - trimmed, at least 3 characters (the database enforces the same
    rule, migration 0017). It is what the top bar shows for the signed-in user (#46)."""
    name = (value or "").strip()
    if not name:
        raise validation("Display name is required.", "display_name")
    if len(name) < DISPLAY_NAME_MIN:
        raise validation(f"Display name must be at least {DISPLAY_NAME_MIN} characters.", "display_name")
    return name


def create(db: Session, ctx, data) -> User:
    display_name = clean_display_name(data.display_name)
    err = validate_role_set(data.security_domain, set(data.roles))
    if err:
        raise validation(err, "roles")
    if db.scalar(select(User.id).where(User.workspace_id == ctx.workspace_id,
                                       User.username_normalized == data.username.lower())):
        raise conflict("DUPLICATE_USERNAME", "That username is already in use.")
    _pw_check(data.password, data.username)
    u = User(workspace_id=ctx.workspace_id, username=data.username, username_normalized=data.username.lower(),
             email=data.email, display_name=display_name, password_hash=hash_password(data.password),
             active=True, security_domain=data.security_domain, theme="light", password_changed_at=utcnow(),
             created_by_user_id=ctx.user.id, updated_by_user_id=ctx.user.id)
    db.add(u)
    db.flush()
    _set_roles(db, u, set(data.roles))
    audit.record(db, ctx, "USER_CREATED", "user", u.id, None, snapshot(u), category="SECURITY")
    return u


def update(db: Session, ctx, u: User, data) -> User:
    before = snapshot(u)
    f = data.model_fields_set
    if "email" in f:
        if not data.email:
            raise validation("Email is required.", "email")
        u.email = data.email
    if "display_name" in f:   # sent empty = an attempt to remove it
        u.display_name = clean_display_name(data.display_name)
    domain = data.security_domain if "security_domain" in f and data.security_domain else u.security_domain
    roles_changed = False
    if "roles" in f or domain != u.security_domain:
        codes = set(data.roles) if data.roles is not None else u.role_codes
        err = validate_role_set(domain, codes)
        if err:
            raise validation(err, "roles")
        if codes != u.role_codes or domain != u.security_domain:
            roles_changed = True
            u.security_domain = domain
            _set_roles(db, u, codes)
    if "active" in f and data.active is not None and data.active != u.active:
        u.active = data.active
        if not u.active:
            revoke_user_sessions(db, u.id)  # disabled users lose authorization immediately
    db.flush()
    if _active_admin_count(db, ctx.workspace_id) < 1:
        raise conflict("LAST_ADMINISTRATOR", "At least one active Administrator must remain.")
    u.updated_by_user_id = ctx.user.id
    action = "USER_UPDATED"
    if roles_changed:
        action = "USER_ROLES_CHANGED"
    if "active" in f and data.active is False and before["active"]:
        action = "USER_DISABLED"
    audit.record(db, ctx, action, "user", u.id, before, snapshot(u), category="SECURITY")
    return u


def reset_password(db: Session, ctx, u: User, new_password: str) -> None:
    _pw_check(new_password, u.username)
    u.password_hash = hash_password(new_password)
    u.password_changed_at = utcnow()
    u.updated_by_user_id = ctx.user.id
    n = revoke_user_sessions(db, u.id)
    from .mfa import revoke_trusted
    revoke_trusted(db, u.id)  # v1.4.1 CR-018: a password reset also ends "trusted browser" sign-ins
    audit.record(db, ctx, "USER_PASSWORD_RESET", "user", u.id, None, {"reset_by_administrator": True,
                                                                     "sessions_revoked": n}, category="SECURITY")


def get(db: Session, ctx, uid: int) -> User:
    return get_scoped(db, User, uid, ctx, "User")
