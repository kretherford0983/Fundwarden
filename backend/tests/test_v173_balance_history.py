"""1.7.3 (#88): balance history for manually updated (non-register) accounts - every update is a dated entry
(append-only), the current balance is the entry with the latest date, balances on past dates carry forward, the
balances chart includes these accounts, and existing accounts get their history from the audit log."""
import datetime as dt
import json
import sqlite3

import pytest


@pytest.fixture
def inv(env):
    r = env.bm.post("/api/bank-accounts", {"account_name": "Brokerage", "financial_institution_entity_id": env.fi()["id"],
                                           "account_type": "INVESTMENT", "account_number": "5550001234", "register_enabled": False,
                                           "current_balance": "1000.00"})
    assert r.status_code == 201, r.text
    return r.json()


def _bal(env, a, value, as_of=None, reason=None, client=None):
    body = {"current_balance": value, "reason": reason}
    if as_of:
        body["as_of_date"] = as_of
    return (client or env.bm).post(f"/api/bank-accounts/{a['id']}/balance", body)


def _hist(env, a, client=None):
    r = (client or env.bm).get(f"/api/bank-accounts/{a['id']}/balance-history")
    assert r.status_code == 200, r.text
    return r.json()


def test_creation_is_the_first_entry(env, inv):
    h = _hist(env, inv)
    assert len(h) == 1 and h[0]["balance"] == "1000.00" and h[0]["source"] == "OPENING" and h[0]["change"] is None
    assert h[0]["as_of_date"] == dt.date.today().isoformat() and h[0]["entered_by"] == "Budgetmgr Person"


def test_updates_add_entries_and_keep_the_old_ones(env, inv):
    today = dt.date.today()
    assert _bal(env, inv, "1100.00", (today - dt.timedelta(days=40)).isoformat(), "statement").status_code == 200
    assert _bal(env, inv, "1250.50", reason="month end").status_code == 200
    h = _hist(env, inv)
    assert [x["balance"] for x in h] == ["1250.50", "1000.00", "1100.00"]          # newest first by date
    assert h[0]["change"] == "250.50" and h[1]["change"] == "-100.00" and h[2]["change"] is None
    assert h[0]["reason"] == "month end"
    assert env.bm.get(f"/api/bank-accounts/{inv['id']}").json()["current_balance"] == "1250.50"


def test_back_dated_entry_does_not_replace_the_current_balance(env, inv):
    assert _bal(env, inv, "900.00", (dt.date.today() - dt.timedelta(days=10)).isoformat()).status_code == 200
    assert env.bm.get(f"/api/bank-accounts/{inv['id']}").json()["current_balance"] == "1000.00"


def test_same_date_the_one_entered_last_counts(env, inv):
    today = dt.date.today().isoformat()
    _bal(env, inv, "1500.00", today, "typo")
    _bal(env, inv, "1050.00", today, "correction")
    assert env.bm.get(f"/api/bank-accounts/{inv['id']}").json()["current_balance"] == "1050.00"
    assert len(_hist(env, inv)) == 3                                                   # nothing was overwritten


def test_dates_are_validated(env, inv):
    r = _bal(env, inv, "1.00", (dt.date.today() + dt.timedelta(days=1)).isoformat())
    assert r.status_code == 422 and r.json()["error"]["errors"][0]["field"] == "as_of_date"


def test_entry_in_a_closed_fiscal_year_is_refused(env, base, inv):
    fy = base["fy"]["id"]
    env.approve(fy)
    env.fy_doc(fy, "AUDIT_SIGNOFF")
    assert env.bm.post(f"/api/fiscal-years/{fy}/close", {"confirm_reviewed": True}).status_code == 200
    r = _bal(env, inv, "1.00", "2026-08-15")
    if dt.date.today() >= dt.date(2026, 8, 15):
        assert r.status_code == 409 and r.json()["error"]["code"] == "FISCAL_YEAR_CLOSED"


def test_balance_as_of_a_date_carries_forward(env, inv):
    from fmpoc.models import BankAccount
    from fmpoc.services import bank_accounts as bank
    today = dt.date.today()
    _bal(env, inv, "1200.00", (today - dt.timedelta(days=30)).isoformat())
    with env.app.state.session_factory() as db:
        a = db.get(BankAccount, inv["id"])
        assert bank.manual_as_of(db, a, today - dt.timedelta(days=31)) is None        # before the first entry
        assert bank.current_cents(db, a, today - dt.timedelta(days=15)) == 120000    # carried forward
        assert bank.current_cents(db, a, today) == 100000
        assert bank.available_cents(db, a, today - dt.timedelta(days=15)) == 120000


def test_chart_includes_non_register_accounts(env, base, inv):
    fy = base["fy"]["id"]
    d = env.bu.get(f"/api/dashboard/charts?fiscal_year_id={fy}").json()["balances"]
    labels = [x["label"].split(" - ")[0] for x in d["accounts"]]
    assert "Brokerage" in labels


def test_register_accounts_have_no_history(env, base):
    r = env.bm.get(f"/api/bank-accounts/{base['acct']['id']}/balance-history")
    assert r.status_code == 422


def test_permissions_and_audit(env, inv):
    for c in (env.bu, env.ru, env.auditor):
        assert c.get(f"/api/bank-accounts/{inv['id']}/balance-history").status_code == 200
        assert _bal(env, inv, "1.00", client=c).status_code == 403
    assert env.admin.get(f"/api/bank-accounts/{inv['id']}/balance-history").status_code == 403
    _bal(env, inv, "1300.00", reason="Q3 statement")
    ev = env.auditor.get(f"/api/audit-events?action=BANK_ACCOUNT_BALANCE_UPDATED&object_id={inv['id']}").json()["items"]
    assert ev[0]["after"]["as_of_date"] == dt.date.today().isoformat() and ev[0]["after"]["entry_balance"] == "1300.00"


def test_closing_needs_a_zero_entry(env, inv):
    r = env.bm.post(f"/api/bank-accounts/{inv['id']}/close", {"reason": "sold"})
    assert r.status_code == 409
    _bal(env, inv, "0.00", reason="liquidated")
    assert env.bm.post(f"/api/bank-accounts/{inv['id']}/close", {"reason": "sold"}).status_code == 200
    assert len(_hist(env, inv)) == 2                                                    # history kept


def test_switching_to_non_register_starts_history(env):
    a = env.account(account_name="Was register", opening="250.00")
    r = env.bm.patch(f"/api/bank-accounts/{a['id']}", {"register_enabled": False})
    assert r.status_code == 200, r.text
    h = _hist(env, a)
    assert len(h) == 1 and h[0]["balance"] == "250.00"


def test_migration_rebuilds_history_from_the_audit_log(tmp_path):
    from alembic import command

    from fmpoc.db import alembic_config
    url = f"sqlite:///{tmp_path / 'm.sqlite3'}"
    command.upgrade(alembic_config(url), "0019_admin_roles_deleted_status")
    c = sqlite3.connect(tmp_path / "m.sqlite3")
    c.execute("pragma foreign_keys=off")
    cols = [r[1] for r in c.execute("pragma table_info(bank_account)")]

    def acct(i, register, manual, created):
        row = {k: None for k in cols}
        row.update(id=i, workspace_id=1, financial_institution_entity_id=1, account_name=f"A{i}", account_type="INVESTMENT",
                   account_number_ciphertext="x", account_number_fingerprint=f"fp{i}", account_number_visible_suffix="1234",
                   register_enabled=register, is_primary=0, status="ACTIVE", sort_order=i, manual_current_balance_cents=manual,
                   created_at=created, updated_at=created)
        c.execute(f"insert into bank_account ({','.join(row)}) values ({','.join('?' * len(row))})", list(row.values()))

    def ev(i, action, ts, before, after, user=7):
        c.execute("insert into audit_event (workspace_id, actor_user_id, timestamp, action, object_type, object_id, category, "
                  "before_snapshot, after_snapshot) values (1, ?, ?, ?, 'bank_account', ?, 'BUSINESS', ?, ?)",
                  (user, ts, action, str(i), json.dumps(before) if before is not None else None, json.dumps(after)))
    acct(1, 0, 130000, "2026-01-05 10:00:00")       # created 1000, updated twice (1200, 1300)
    ev(1, "BANK_ACCOUNT_CREATED", "2026-01-05 10:00:00", None, {"register_enabled": False, "manual_current_balance": "1000.00"})
    ev(1, "BANK_ACCOUNT_UPDATED", "2026-02-01 09:00:00", {"register_enabled": False, "manual_current_balance": "1000.00"},
       {"register_enabled": False, "manual_current_balance": "1000.00", "notes": "renamed"})    # no balance change
    ev(1, "BANK_ACCOUNT_BALANCE_UPDATED", "2026-03-31 12:00:00", {"manual_current_balance": "1000.00"},
       {"register_enabled": False, "manual_current_balance": "1200.00", "reason": "Q1 statement"})
    ev(1, "BANK_ACCOUNT_BALANCE_UPDATED", "2026-06-30 12:00:00", {"manual_current_balance": "1200.00"},
       {"register_enabled": False, "manual_current_balance": "1300.00", "reason": None})
    acct(2, 0, 50000, "2026-04-01 08:00:00")        # no audit events at all
    acct(3, 1, None, "2026-04-01 08:00:00")         # register-enabled: no history
    acct(4, 0, 77700, "2026-02-01 08:00:00")        # history does not end at the current balance
    ev(4, "BANK_ACCOUNT_CREATED", "2026-02-01 08:00:00", None, {"register_enabled": False, "manual_current_balance": "500.00"})
    c.commit(); c.close()
    command.upgrade(alembic_config(url), "head")
    c = sqlite3.connect(tmp_path / "m.sqlite3")
    rows = c.execute("select bank_account_id, as_of_date, balance_cents, reason, source, entered_by_user_id "
                     "from bank_account_balance order by bank_account_id, as_of_date, id").fetchall()
    one = [r for r in rows if r[0] == 1]
    assert [(r[1], r[2], r[4]) for r in one] == [("2026-01-05", 100000, "OPENING"), ("2026-03-31", 120000, "UPDATE"),
                                                 ("2026-06-30", 130000, "UPDATE")]
    assert one[1][3] == "Q1 statement" and one[0][5] == 7
    assert [(r[1], r[2], r[4]) for r in rows if r[0] == 2] == [("2026-04-01", 50000, "UPGRADE")]
    assert [r for r in rows if r[0] == 3] == []
    four = [r for r in rows if r[0] == 4]
    assert [r[2] for r in four] == [50000, 77700] and four[1][4] == "UPGRADE"
    # the current balances are unchanged
    assert dict(c.execute("select id, manual_current_balance_cents from bank_account").fetchall()) == {1: 130000, 2: 50000, 3: None, 4: 77700}
