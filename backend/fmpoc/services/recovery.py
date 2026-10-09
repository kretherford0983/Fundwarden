"""1.8.0 (#113): forgotten password - security questions, the Forgot password flow, the persistent per-account count
of failed attempts with escalating locks (sign-in and Forgot password together), and the notices that make a reset
or a run of failed attempts visible to the user and to the Administrators."""
from __future__ import annotations

import datetime as dt
import secrets
import threading
import time
import unicodedata

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import audit
from ..errors import AppError, conflict, not_found, validation
from ..models import SecurityNotice, User, UserSecurityQuestion, utcnow
from ..security.passwords import hash_password, policy_errors, verify_password
from . import mfa

QUESTION_COUNT = 3
QUESTION_MINUTES = 15          # Forgot password shows the same question until a failed attempt or this timeout
LOCKED_MESSAGE = "Too many failed attempts. Try again later."
WRONG_MESSAGE = "The answer or the code is not correct."

# A fixed list (decided 2026-10-08): answers that are easy to remember but not easy to find out about someone.
QUESTIONS: dict[str, str] = {
    "FIRST_TEACHER": "What was the name of your first teacher?",
    "FIRST_PET": "What was the name of your first pet?",
    "FIRST_CAR": "What was the make and model of your first car?",
    "CHILDHOOD_NICKNAME": "What was your childhood nickname?",
    "FIRST_CONCERT": "What was the first concert you went to?",
    "CHILDHOOD_FRIEND": "What was the first name of your best friend as a child?",
    "CHILDHOOD_FOOD": "What was your favorite food as a child?",
    "FIRST_TOY": "What was the name of your favorite toy or stuffed animal?",
    "FIRST_BOOK": "What was the first book you remember reading?",
    "DREAM_JOB": "What did you want to be when you grew up?",
    "FAVORITE_TEACHER": "What was the last name of your favorite teacher in high school?",
    "GRANDPARENT_TOWN": "In what town or city did your grandparents live?",
}

METHODS = {"totp": "question_and_authenticator", "recovery": "question_and_recovery_code", None: "question_only"}
METHOD_TEXT = {"question_and_authenticator": "your security question and your authenticator app",
               "question_and_recovery_code": "your security question and a recovery code",
               "question_only": "your security question"}


def catalog() -> list[dict]:
    return [{"code": k, "text": v} for k, v in QUESTIONS.items()]


def normalize_answer(answer: str | None) -> str:
    """Case, spaces and punctuation do not matter: "Rex", " rex " and "REX!" are the same answer."""
    t = unicodedata.normalize("NFKC", answer or "").casefold()
    return "".join(ch for ch in t if ch.isalnum())


def _name(u: User) -> str:
    return u.display_name or u.username


# ------------------------------------------------------------------ security questions
def questions_of(db: Session, user_id: int) -> list[UserSecurityQuestion]:
    return list(db.scalars(select(UserSecurityQuestion).where(UserSecurityQuestion.user_id == user_id)
                           .order_by(UserSecurityQuestion.slot)))


def has_questions(db: Session, user: User) -> bool:
    return len(questions_of(db, user.id)) >= QUESTION_COUNT


def my_questions(db: Session, user: User) -> dict:
    qs = questions_of(db, user.id)
    return {"set": len(qs) >= QUESTION_COUNT,
            "set_at": qs[0].created_at.isoformat() + "Z" if qs else None,
            "questions": [{"slot": q.slot, "code": q.question_code, "text": QUESTIONS.get(q.question_code, q.question_code)}
                          for q in qs]}


def set_questions(db: Session, ctx, user: User, items, how: str) -> None:
    """Replaces the user's questions and answers (exactly 3, different questions from the list, non-empty answers)."""
    if len(items) != QUESTION_COUNT:
        raise validation(f"Choose {QUESTION_COUNT} questions.", "questions")
    codes = [i.question for i in items]
    for n, i in enumerate(items):
        if i.question not in QUESTIONS:
            raise validation("Choose a question from the list.", f"questions.{n}.question")
        if len(normalize_answer(i.answer)) < 2:
            raise validation("Enter an answer (at least 2 letters or digits).", f"questions.{n}.answer")
    if len(set(codes)) != QUESTION_COUNT:
        raise validation("Choose three different questions.", "questions")
    db.execute(delete(UserSecurityQuestion).where(UserSecurityQuestion.user_id == user.id))
    now = utcnow()
    for n, i in enumerate(items, start=1):
        db.add(UserSecurityQuestion(user_id=user.id, slot=n, question_code=i.question,
                                    answer_hash=hash_password(normalize_answer(i.answer)), created_at=now))
    user.reset_question_slot = user.reset_question_at = None
    audit.record(db, ctx, "SECURITY_QUESTIONS_SET", "user", user.id, None, {"questions": codes, "how": how},
                 category="SECURITY")


def admin_reset_questions(db: Session, ctx, user: User, reason: str) -> None:
    reason = (reason or "").strip()
    if not reason:
        raise validation("A reason is required.", "reason")
    n = db.execute(delete(UserSecurityQuestion).where(UserSecurityQuestion.user_id == user.id)).rowcount or 0
    user.reset_question_slot = user.reset_question_at = None
    audit.record(db, ctx, "SECURITY_QUESTIONS_RESET", "user", user.id, {"questions_set": n >= QUESTION_COUNT},
                 {"questions_set": False, "reason": reason[:500]}, category="SECURITY")


# ------------------------------------------------------------------ sign-in gates
def gate_for(db: Session, user: User) -> str | None:
    """Steps after the password (and two-step verification) before the application: a temporary password from the
    host command line must be changed, then the security questions must be set up."""
    if user.must_change_password:
        return "PASSWORD"
    if not has_questions(db, user):
        return "QUESTIONS"
    return None


# ------------------------------------------------------------------ failed attempts and locks
def _steps(settings) -> list[tuple[int, int]]:
    return sorted([(settings.lockout_1_failures, settings.lockout_1_minutes),
                   (settings.lockout_2_failures, settings.lockout_2_minutes),
                   (settings.lockout_3_failures, settings.lockout_3_minutes)])


def is_locked(user: User) -> bool:
    return user.locked_until is not None and user.locked_until > utcnow()


def clear_failures(user: User) -> None:
    user.failed_attempts = 0
    user.locked_until = None


def add_notice(db: Session, ws_id: int, user: User | None, kind: str, message: str) -> None:
    db.add(SecurityNotice(workspace_id=ws_id, subject_user_id=user.id if user else None, kind=kind,
                          message=message[:500], created_at=utcnow()))


def register_failure(db: Session, settings, ctx, user: User, stage: str) -> None:
    """One more failed attempt in a row. Locks at the configured counts, disables the account at the last one."""
    from .auth import revoke_user_sessions
    user.failed_attempts = (user.failed_attempts or 0) + 1
    n, now = user.failed_attempts, utcnow()
    if n >= settings.lockout_disable_failures:
        user.active = False
        user.locked_until = None
        user.notice_failed_attempts_at = now
        revoke_user_sessions(db, user.id)
        audit.record(db, ctx, "ACCOUNT_DISABLED_FAILED_ATTEMPTS", "user", user.id, {"active": True},
                     {"active": False, "failed_attempts": n, "stage": stage}, category="SECURITY")
        add_notice(db, user.workspace_id, user, "ACCOUNT_DISABLED",
                   f"{_name(user)}'s account was disabled after {n} failed sign-in or password reset attempts in a "
                   "row. Re-enable it on the Users page when you know it was them.")
        return
    for i, (count, minutes) in enumerate(_steps(settings)):
        if n == count:
            user.locked_until = now + dt.timedelta(minutes=minutes)
            user.notice_failed_attempts_at = now
            audit.record(db, ctx, "ACCOUNT_LOCKED", "user", user.id, None,
                         {"failed_attempts": n, "minutes": minutes, "until": user.locked_until.isoformat() + "Z",
                          "stage": stage}, category="SECURITY")
            if i >= 1:   # early warning from the second (by default 1-hour) lock on
                add_notice(db, user.workspace_id, user, "ACCOUNT_LOCKED",
                           f"Several failed sign-in attempts on {_name(user)}'s account: {n} in a row. The account is "
                           f"locked until {user.locked_until:%Y-%m-%d %H:%M} UTC; at "
                           f"{settings.lockout_disable_failures} it is disabled.")
            break


# ------------------------------------------------------------------ unknown usernames behave like real ones
class _Decoys:
    """A question for a username that does not exist (or cannot reset), kept like a real user's: the same until a
    failed attempt or the timeout. In memory, bounded."""

    def __init__(self, limit: int = 5000):
        self._d: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()
        self.limit = limit

    def question(self, uname: str) -> str:
        now = time.monotonic()
        with self._lock:
            q = self._d.get(uname)
            if q is None or now - q[1] > QUESTION_MINUTES * 60:
                if len(self._d) >= self.limit:
                    self._d.clear()
                q = (secrets.choice(list(QUESTIONS)), now)
                self._d[uname] = q
            return q[0]

    def current(self, uname: str) -> str | None:
        with self._lock:
            q = self._d.get(uname)
            return q[0] if q and time.monotonic() - q[1] <= QUESTION_MINUTES * 60 else None

    def drop(self, uname: str) -> None:
        with self._lock:
            self._d.pop(uname, None)


decoys = _Decoys()


def _lookup(db: Session, uname: str) -> User | None:
    u = db.scalar(select(User).where(User.username_normalized == uname))
    if u is None or not u.active or not has_questions(db, u):
        return None   # unknown, disabled or never set up: behaves like an unknown username and never succeeds
    return u


def _needs_code(db: Session, settings, user: User | None) -> bool:
    return mfa.required(settings) or (user is not None and mfa.enabled(db, user))


def _current_slot(user: User) -> int | None:
    if user.reset_question_slot and user.reset_question_at and \
            user.reset_question_at > utcnow() - dt.timedelta(minutes=QUESTION_MINUTES):
        return user.reset_question_slot
    return None


def forgot_start(db: Session, settings, limiter, ctx, username: str) -> dict:
    uname = (username or "").strip().lower()[:64]
    user = _lookup(db, uname)
    ipk = f"ip:{ctx.ip}"
    if limiter.blocked(ipk) or (user is not None and is_locked(user)) or \
            (user is None and limiter.blocked(f"u:{uname}")):
        raise AppError(429, "RATE_LIMITED", LOCKED_MESSAGE)
    if user is None:
        code = decoys.question(uname)
    else:
        slot = _current_slot(user)
        qs = {q.slot: q for q in questions_of(db, user.id)}
        if slot not in qs:
            slot = secrets.choice(sorted(qs))
            user.reset_question_slot, user.reset_question_at = slot, utcnow()
            audit.record(db, ctx, "PASSWORD_RESET_STARTED", "user", user.id, None, {"slot": slot}, category="SECURITY")
            db.commit()
        code = qs[slot].question_code
    return {"username": uname, "question": {"code": code, "text": QUESTIONS[code]},
            "needs_code": _needs_code(db, settings, user)}


def forgot_complete(db: Session, settings, km, limiter, ctx, data) -> dict:
    uname = (data.username or "").strip().lower()[:64]
    if data.new_password != data.new_password_confirmation:
        raise AppError(422, "VALIDATION_ERROR", "New password and confirmation do not match.",
                       errors=[{"field": "new_password_confirmation", "message": "Passwords do not match."}])
    errs = policy_errors(data.new_password, uname)
    if errs:
        raise AppError(422, "PASSWORD_POLICY", " ".join(errs),
                       errors=[{"field": "new_password", "message": e} for e in errs])
    user = _lookup(db, uname)
    ipk = f"ip:{ctx.ip}"
    if limiter.blocked(ipk) or (user is not None and is_locked(user)) or \
            (user is None and limiter.blocked(f"u:{uname}")):
        raise AppError(429, "RATE_LIMITED", LOCKED_MESSAGE)
    expired = AppError(409, "QUESTION_EXPIRED", "The question has expired. Start again.")
    if user is None:
        if decoys.current(uname) is None:
            raise expired
        decoys.drop(uname)
        limiter.fail(ipk, f"u:{uname}")
        audit.record(db, ctx, "PASSWORD_RESET_FAILED", "user", None, None, {"username": uname}, category="SECURITY")
        db.commit()
        raise AppError(400, "RESET_FAILED", WRONG_MESSAGE)
    slot = _current_slot(user)
    q = next((x for x in questions_of(db, user.id) if x.slot == slot), None)
    if q is None:
        raise expired
    ok = verify_password(q.answer_hash, normalize_answer(data.answer))
    used = None
    if ok and _needs_code(db, settings, user):
        used = mfa.verify(db, km, user, (data.code or "").strip()) if data.code else None
        ok = used is not None
    if not ok:
        user.reset_question_slot = user.reset_question_at = None   # a new question next time
        limiter.fail(ipk)
        register_failure(db, settings, ctx, user, "password_reset")
        audit.record(db, ctx, "PASSWORD_RESET_FAILED", "user", user.id, None,
                     {"failed_attempts": user.failed_attempts}, category="SECURITY")
        db.commit()
        raise AppError(400, "RESET_FAILED", WRONG_MESSAGE)
    from .auth import revoke_user_sessions
    method = METHODS[used]
    now = utcnow()
    user.password_hash = hash_password(data.new_password)
    user.password_changed_at = now
    user.must_change_password = False
    user.reset_question_slot = user.reset_question_at = None
    clear_failures(user)
    user.notice_password_reset_at, user.notice_password_reset_method = now, method
    sessions = revoke_user_sessions(db, user.id)
    trusted = mfa.revoke_trusted(db, user.id)
    limiter.reset(ipk)
    if used == "recovery":
        audit.record(db, ctx, "MFA_RECOVERY_CODE_USED", "user", user.id, None, {"stage": "password_reset"},
                     category="SECURITY")
    audit.record(db, ctx, "PASSWORD_RESET_SELF_SERVICE", "user", user.id, None,
                 {"method": method, "sessions_revoked": sessions, "trusted_browsers_revoked": trusted},
                 category="SECURITY")
    add_notice(db, user.workspace_id, user, "PASSWORD_RESET",
               f"{_name(user)} reset their password with {METHOD_TEXT[method]} on {now:%Y-%m-%d %H:%M} UTC.")
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ notices
def sign_in_notices(user: User) -> list[dict]:
    out = []
    if user.notice_password_reset_at:
        out.append({"kind": "PASSWORD_RESET",
                    "message": f"Your password was reset on {user.notice_password_reset_at:%Y-%m-%d %H:%M} UTC using "
                               f"{METHOD_TEXT.get(user.notice_password_reset_method or '', 'your security questions')}."
                               " If this was not you, tell an Administrator at once."})
    if user.notice_failed_attempts_at:
        out.append({"kind": "FAILED_ATTEMPTS",
                    "message": "There were several failed sign-in attempts on your account since your last sign-in. "
                               "If they were not yours, tell an Administrator."})
    return out


def dismiss_sign_in_notices(user: User) -> None:
    user.notice_password_reset_at = user.notice_password_reset_method = None
    user.notice_failed_attempts_at = None


def admin_notices(db: Session, ws_id: int) -> list[dict]:
    rows = db.scalars(select(SecurityNotice).where(SecurityNotice.workspace_id == ws_id,
                                                   SecurityNotice.dismissed_at.is_(None))
                      .order_by(SecurityNotice.created_at.desc(), SecurityNotice.id.desc()))
    return [{"id": n.id, "kind": n.kind, "message": n.message, "subject_user_id": n.subject_user_id,
             "created_at": n.created_at.isoformat() + "Z"} for n in rows]


def dismiss_admin_notice(db: Session, ctx, notice_id: int) -> None:
    n = db.get(SecurityNotice, notice_id)
    if n is None or n.workspace_id != ctx.workspace_id:
        raise not_found("Notice")
    if n.dismissed_at is not None:
        raise conflict("ALREADY_DISMISSED", "The notice was already dismissed.")
    n.dismissed_at, n.dismissed_by_user_id = utcnow(), ctx.user.id
    audit.record(db, ctx, "SECURITY_NOTICE_DISMISSED", "security_notice", n.id, None,
                 {"kind": n.kind, "subject_user_id": n.subject_user_id}, category="SECURITY")
