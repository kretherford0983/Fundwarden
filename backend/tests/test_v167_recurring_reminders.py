"""1.6.7: recurring organization reminders (every N days / weeks / months / years, optionally until a date)."""
import datetime as dt

import pytest

from fmpoc.services import reminders as _reminders
from fmpoc.services.reminders import add_interval

# The reminder service's "today" is pinned to the date the tests were collected, so a run that crosses
# midnight (as a CI build in the evening, US time, crosses midnight UTC) still agrees with D().
TODAY = dt.date.today()
D = lambda n: (TODAY + dt.timedelta(days=n)).isoformat()  # noqa: E731


@pytest.fixture(autouse=True)
def _pinned_today(monkeypatch):
    monkeypatch.setattr(_reminders, "today", lambda: TODAY)


def mk(c, **kw):
    return c.post("/api/reminders", {"scope": "ORGANIZATION", "title": "Reconcile bank", "due_date": D(0), **kw})


def rows(c, view):
    return c.get(f"/api/reminders?view={view}").json()


def test_interval_arithmetic_keeps_the_day_and_clamps_month_ends():
    d = dt.date
    assert add_interval(d(2026, 1, 31), "MONTH", 1) == d(2026, 2, 28)
    assert add_interval(d(2026, 1, 31), "MONTH", 2) == d(2026, 3, 31)   # counted from the anchor: no drift to the 28th
    assert add_interval(d(2026, 11, 15), "MONTH", 3) == d(2027, 2, 15)
    assert add_interval(d(2024, 2, 29), "YEAR", 1) == d(2025, 2, 28)
    assert add_interval(d(2024, 2, 29), "YEAR", 4) == d(2028, 2, 29)
    assert add_interval(d(2026, 1, 1), "WEEK", 2) == d(2026, 1, 15)
    assert add_interval(d(2026, 1, 1), "DAY", 10) == d(2026, 1, 11)


def test_resolving_creates_the_next_occurrence_from_the_scheduled_date(env, base):
    r = mk(env.bm, due_date=D(-3), repeat_every=2, repeat_unit="WEEK", notify_days_before=1, details="Statement",
           link_type="BANK_ACCOUNT", link_id=base["acct"]["id"]).json()
    assert r["repeat_label"] == "Repeats every 2 weeks" and r["next_due"] == D(11) and r["state"] == "DUE"
    # a Register User resolves it three days late: the next one is still 14 days after the *scheduled* date
    x = env.ru.post(f"/api/reminders/{r['id']}/resolve", {"note": "Matched"}).json()
    assert x["state"] == "RESOLVED" and x["resolution_note"] == "Matched"
    nxt = rows(env.bm, "upcoming")
    assert len(nxt) == 1 and nxt[0]["due_date"] == D(11) and nxt[0]["show_date"] == D(10)
    n = nxt[0]
    assert (n["title"], n["details"], n["owner"], n["repeat_label"]) == ("Reconcile bank", "Statement", "budgetmgr", "Repeats every 2 weeks")
    assert n["link"]["label"].startswith("Bank account") and n["next_due"] == D(25) and n["resolution_note"] is None
    assert rows(env.ru, "upcoming") == []  # Register Users still only see it once it is due
    # resolving twice is refused and never makes a second copy
    assert env.ru.post(f"/api/reminders/{r['id']}/resolve", {}).status_code == 409
    assert len(rows(env.bm, "upcoming")) == 1
    acts = [(e["action"], int(e["object_id"])) for e in
            env.auditor.get("/api/audit-events?object_type=reminder&sort=id&direction=asc").json()["items"]]
    assert acts == [("REMINDER_CREATED", r["id"]), ("REMINDER_RESOLVED", r["id"]), ("REMINDER_CREATED", n["id"])]


def test_reopen_takes_the_next_occurrence_back(env, base):
    r = mk(env.bm, repeat_every=1, repeat_unit="DAY", due_date=D(-1)).json()
    env.bm.post(f"/api/reminders/{r['id']}/resolve", {})
    first_next = rows(env.bm, "due")
    assert [i["due_date"] for i in first_next] == [D(0)]            # daily: the next one is due at once
    # reopening the first removes the one it created ...
    assert env.bm.post(f"/api/reminders/{r['id']}/reopen").json()["state"] == "DUE"
    assert [i["id"] for i in rows(env.bm, "due")] == [r["id"]]
    # ... and it comes back when resolved again
    env.bm.post(f"/api/reminders/{r['id']}/resolve", {})
    second = rows(env.bm, "due")
    assert len(second) == 1 and second[0]["id"] != r["id"]
    # once the next occurrence is itself resolved, the earlier one can no longer be reopened
    env.bm.post(f"/api/reminders/{second[0]['id']}/resolve", {})
    x = env.bm.post(f"/api/reminders/{r['id']}/reopen")
    assert x.status_code == 409 and x.json()["error"]["code"] == "REMINDER_NEXT_RESOLVED"


def test_stop_repeating_and_end_date(env, base):
    r = mk(env.bm, repeat_every=1, repeat_unit="MONTH").json()
    env.bm.post(f"/api/reminders/{r['id']}/resolve", {"stop_repeating": True})
    assert rows(env.bm, "upcoming") == [] and rows(env.bm, "due") == []
    # end date: the occurrence whose due date would pass it is not created
    r = mk(env.bm, title="Weekly count", repeat_every=1, repeat_unit="WEEK", due_date=D(-7), repeat_until=D(3)).json()
    assert r["repeat_label"] == f"Repeats every week until {D(3)}" and r["next_due"] == D(0)
    env.bm.post(f"/api/reminders/{r['id']}/resolve", {})
    last = rows(env.bm, "due")
    assert [i["due_date"] for i in last] == [D(0)] and last[0]["next_due"] is None
    env.bm.post(f"/api/reminders/{last[0]['id']}/resolve", {})
    assert rows(env.bm, "due") == [] and rows(env.bm, "upcoming") == []


def test_validation_and_editing(env, base):
    assert mk(env.ru, scope="PERSONAL", repeat_every=1, repeat_unit="MONTH").status_code == 422   # personal: one-time
    assert mk(env.bm, repeat_every=1).status_code == 422 and mk(env.bm, repeat_unit="MONTH").status_code == 422
    assert mk(env.bm, repeat_every=0, repeat_unit="DAY").status_code == 422
    assert mk(env.bm, repeat_every=1, repeat_unit="FORTNIGHT").status_code == 422
    assert mk(env.bm, repeat_until=D(5)).status_code == 422                                       # end date without a repeat
    assert mk(env.bm, repeat_every=1, repeat_unit="DAY", due_date=D(5), repeat_until=D(4)).status_code == 422
    one = mk(env.bm, title="Once").json()
    assert one["repeat_label"] is None and one["next_due"] is None
    # an upcoming occurrence can be changed: the new schedule applies from there; removing the repeat makes it one-time
    r = mk(env.bm, title="Quarterly review", due_date=D(40), repeat_every=3, repeat_unit="MONTH").json()
    body = {"scope": "ORGANIZATION", "title": "Quarterly review", "due_date": D(50), "notify_days_before": 0,
            "repeat_every": 1, "repeat_unit": "YEAR"}
    x = env.bm.put(f"/api/reminders/{r['id']}", body).json()
    assert x["repeat_label"] == "Repeats every year" and x["due_date"] == D(50)
    x = env.bm.put(f"/api/reminders/{r['id']}", {**body, "repeat_every": None, "repeat_unit": None}).json()
    assert x["repeat_label"] is None and x["next_due"] is None
    assert env.bm.delete(f"/api/reminders/{r['id']}").json() == {"deleted": True}
