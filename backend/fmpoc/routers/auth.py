from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session, object_session

from .. import audit
from ..deps import PRE_CSRF_COOKIE, SESSION_COOKIE, Ctx, auth_ctx, get_ctx, get_db, pre_mfa_ctx
from ..errors import AppError
from ..permissions import permissions_for
from ..schemas import ChangePasswordIn, LoginIn, MfaCodeIn, MfaEnrollStartIn, MfaVerifyIn, PreferencesIn
from ..services import auth as svc
from ..services import mfa
from ..services.charts import charts_for
from ..services.dashboard_layout import encode as encode_layout
from ..services.dashboard_layout import is_customized, layout_for
from ..services.fundraisers import module_enabled

router = APIRouter(prefix="/api", tags=["auth"])
_PRE_CSRF_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}")  # secrets.token_urlsafe(32)


def _secure(request: Request) -> bool:
    mode = request.app.state.settings.secure_cookies
    return mode == "true" or (mode == "auto" and request.url.scheme == "https")


def set_session_cookie(request: Request, response: Response, token: str) -> None:
    s = request.app.state.settings
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict", secure=_secure(request), path="/",
                        max_age=s.session_absolute_hours * 3600)


@router.get("/auth/csrf")
def pre_auth_csrf(request: Request, response: Response):
    """Double-submit token for the unauthenticated login/initialize forms.

    1.6.8 (#66, CodeQL "construction of a cookie using user-supplied input"): the cookie is only ever written with a
    token generated here. A browser that already has one gets it back in the answer and no cookie is set; a cookie
    that does not look like one of our tokens is replaced."""
    token = request.cookies.get(PRE_CSRF_COOKIE) or ""
    if not _PRE_CSRF_TOKEN.fullmatch(token):
        token = secrets.token_urlsafe(32)
        response.set_cookie(PRE_CSRF_COOKIE, token, httponly=False, samesite="strict", secure=_secure(request),
                            path="/")
    return {"csrf_token": token}


def me_payload(ctx: Ctx) -> dict:
    u = ctx.user
    if ctx.mfa_pending:  # v1.4.1 CR-018: only what the two-step screen needs
        return {"id": u.id, "username": u.username, "email": u.email, "display_name": u.display_name,
                "security_domain": u.security_domain, "roles": [], "permissions": [], "theme": u.theme,
                "nav_collapsed": bool(u.nav_collapsed), "mfa_pending": ctx.mfa_pending,
                "csrf_token": ctx.session.csrf_token}
    return {"mfa_pending": None,"id": u.id, "username": u.username, "email": u.email, "display_name": u.display_name,
            "security_domain": u.security_domain, "roles": sorted(ctx.roles), "permissions": sorted(ctx.perms),
            "theme": u.theme, "nav_collapsed": bool(u.nav_collapsed), "dashboard_charts": charts_for(u),
            "dashboard_layout": layout_for(u), "dashboard_layout_customized": is_customized(u),
            "modules": {"fundraisers": module_enabled(object_session(u), u.workspace_id)},  # v1.6.0 CR-033
            "csrf_token": ctx.session.csrf_token}


@router.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db), ctx: Ctx = Depends(get_ctx)):
    s = request.app.state.settings
    user, token, sess = svc.login(db, s, request.app.state.limiter, ctx, body.username, body.password,
                                  request.cookies.get(SESSION_COOKIE), request.cookies.get(mfa.TRUST_COOKIE))
    db.commit()
    set_session_cookie(request, response, token)
    response.delete_cookie(PRE_CSRF_COOKIE, path="/")
    ctx.session, ctx.mfa_pending = sess, sess.mfa_pending
    if not sess.mfa_pending:
        ctx.roles = user.role_codes
        ctx.perms = permissions_for(ctx.roles)
    return me_payload(ctx)


@router.post("/auth/logout")
def logout(response: Response, db: Session = Depends(get_db), ctx: Ctx = Depends(pre_mfa_ctx)):
    svc.logout(db, ctx)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(ctx: Ctx = Depends(pre_mfa_ctx)):
    return me_payload(ctx)


# ------------------------------------------------------------------ v1.4.1 CR-018: two-step verification
def _set_trusted_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(mfa.TRUST_COOKIE, token, httponly=True, samesite="strict", secure=_secure(request), path="/",
                        max_age=mfa.TRUST_DAYS * 86400)


def _finish(request: Request, response: Response, db: Session, ctx: Ctx, how: str, trust: bool) -> dict:
    s = request.app.state.settings
    token, _sess = svc.complete_mfa(db, s, ctx, how)
    if trust:
        t, _exp = mfa.issue_trusted(db, ctx, ctx.user, request.headers.get("user-agent"))
        _set_trusted_cookie(request, response, t)
    db.commit()
    set_session_cookie(request, response, token)
    ctx.roles = ctx.user.role_codes
    ctx.perms = permissions_for(ctx.roles)
    return me_payload(ctx)


def _mfa_limited(request: Request, ctx: Ctx):
    keys = (f"mfa:{ctx.user.id}", f"mfaip:{ctx.ip}")
    lim = request.app.state.limiter
    if lim.blocked(*keys):
        raise AppError(429, "RATE_LIMITED", "Too many incorrect codes. Try again later.")
    return lim, keys


@router.post("/auth/mfa/verify")
def mfa_verify(body: MfaVerifyIn, request: Request, response: Response, db: Session = Depends(get_db),
               ctx: Ctx = Depends(pre_mfa_ctx)):
    if ctx.mfa_pending != "VERIFY":
        raise AppError(409, "MFA_NOT_PENDING", "No two-step verification is waiting for this session.")
    lim, keys = _mfa_limited(request, ctx)
    used = mfa.verify(db, request.app.state.key, ctx.user, body.code)
    if used is None:
        lim.fail(*keys)
        audit.record(db, ctx, "MFA_FAILED", "user", ctx.user.id, None, {"stage": "sign_in"}, category="SECURITY")
        db.commit()
        raise AppError(400, "MFA_INVALID_CODE", "The code is not valid. Enter the current 6-digit code from your "
                                                "authenticator app, or a recovery code.")
    lim.reset(*keys)
    if used == "recovery":
        audit.record(db, ctx, "MFA_RECOVERY_CODE_USED", "user", ctx.user.id, None, {"stage": "sign_in"},
                     category="SECURITY")
    return _finish(request, response, db, ctx, "recovery_code" if used == "recovery" else "totp", body.trust_browser)


@router.post("/auth/mfa/enroll/start")
def mfa_enroll_start(body: MfaEnrollStartIn, request: Request, db: Session = Depends(get_db),
                     ctx: Ctx = Depends(pre_mfa_ctx)):
    """First setup (at sign-in when required, or from My Account) or change of authenticator (current code needed)."""
    if ctx.mfa_pending == "VERIFY":
        raise AppError(401, "MFA_REQUIRED", "Complete two-step verification first.")
    lim, keys = _mfa_limited(request, ctx)
    try:
        return mfa.start_enrollment(db, request.app.state.key, ctx, body.current_code)
    except AppError as e:
        if e.code == "MFA_INVALID_CODE":
            lim.fail(*keys)
        raise


@router.post("/auth/mfa/enroll/confirm")
def mfa_enroll_confirm(body: MfaCodeIn, request: Request, response: Response, db: Session = Depends(get_db),
                       ctx: Ctx = Depends(pre_mfa_ctx)):
    if ctx.mfa_pending == "VERIFY":
        raise AppError(401, "MFA_REQUIRED", "Complete two-step verification first.")
    lim, keys = _mfa_limited(request, ctx)
    try:
        codes = mfa.confirm_enrollment(db, request.app.state.key, ctx, body.code)
    except AppError as e:
        if e.code == "MFA_INVALID_CODE":
            lim.fail(*keys)
        raise
    lim.reset(*keys)
    if ctx.mfa_pending == "ENROLL":
        me = _finish(request, response, db, ctx, "enrolled", False)
    else:
        db.commit()
        me = me_payload(ctx)
    return {"recovery_codes": codes, "me": me}


@router.get("/me/mfa")
def mfa_status(request: Request, db: Session = Depends(get_db), ctx: Ctx = Depends(auth_ctx)):
    return mfa.status(db, request.app.state.settings, ctx.user)


@router.post("/me/mfa/trusted-browsers/{device_id}/revoke")
def mfa_revoke_browser(device_id: int, request: Request, db: Session = Depends(get_db), ctx: Ctx = Depends(auth_ctx)):
    n = mfa.revoke_trusted(db, ctx.user.id, device_id)
    if n:
        audit.record(db, ctx, "MFA_TRUSTED_BROWSER_REVOKED", "user", ctx.user.id, None,
                     {"trusted_browser_id": device_id}, category="SECURITY")
    db.commit()
    return mfa.status(db, request.app.state.settings, ctx.user)


@router.post("/me/mfa/trusted-browsers/revoke-all")
def mfa_revoke_all(request: Request, db: Session = Depends(get_db), ctx: Ctx = Depends(auth_ctx)):
    n = mfa.revoke_trusted(db, ctx.user.id)
    audit.record(db, ctx, "MFA_TRUSTED_BROWSER_REVOKED", "user", ctx.user.id, None, {"all": True, "count": n},
                 category="SECURITY")
    db.commit()
    return mfa.status(db, request.app.state.settings, ctx.user)


@router.post("/me/mfa/disable")
def mfa_disable(body: MfaCodeIn, request: Request, db: Session = Depends(get_db), ctx: Ctx = Depends(auth_ctx)):
    mfa.disable(db, request.app.state.key, request.app.state.settings, ctx, body.code)
    db.commit()
    return mfa.status(db, request.app.state.settings, ctx.user)


@router.post("/auth/change-password")
def change_password(body: ChangePasswordIn, db: Session = Depends(get_db), ctx: Ctx = Depends(auth_ctx)):
    svc.change_own_password(db, ctx, body.current_password, body.new_password, body.new_password_confirmation)
    return {"ok": True, "other_sessions_revoked": True}


@router.put("/me/preferences")
def preferences(body: PreferencesIn, db: Session = Depends(get_db), ctx: Ctx = Depends(auth_ctx)):
    if body.theme is not None:
        ctx.user.theme = body.theme  # persisted per user (BR-UI-THEME-002)
    if body.nav_collapsed is not None:
        ctx.user.nav_collapsed = body.nav_collapsed  # v1.3 CR-014
    if body.dashboard_charts is not None:  # v1.4.1 CR-020
        ctx.user.dashboard_charts = ",".join(dict.fromkeys(body.dashboard_charts))
    if body.reset_dashboard_layout:  # v1.5.0 CR-031
        ctx.user.dashboard_layout = None
    elif body.dashboard_layout is not None:
        ctx.user.dashboard_layout = encode_layout(body.dashboard_layout)
    db.commit()
    return {"theme": ctx.user.theme, "nav_collapsed": bool(ctx.user.nav_collapsed),
            "dashboard_charts": charts_for(ctx.user), "dashboard_layout": layout_for(ctx.user),
            "dashboard_layout_customized": is_customized(ctx.user)}
