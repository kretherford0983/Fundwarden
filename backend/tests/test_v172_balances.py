"""1.7.2 (#56, #57): Current Balance = the bank balance (cleared transactions, by Clear/Post Date) everywhere;
Available Balance = everything written or deposited (by Transaction Date), shown in the Register only. The Fiscal
Year starting balance is the Available Balance, shown with the bank balance and the outstanding items. A Clear/Post
Date cannot be earlier than the Transaction Date."""
import pytest


@pytest.fixture
def book(env, base):
    """Opening 1000.00 (2026-01-01). FY2027 = 2026-07-01..2027-06-30, FY2028 = 2027-07-01..2028-06-30.
    FY2027: deposit 500 (cleared in the year), check #101 for 200 on 2027-06-28 and a deposit of 100 on 2027-06-30,
    both not cleared yet."""
    fy28 = env.fy("2028", "2027-07-01", "2028-06-30")
    env.budget(fy28["id"], "1000", "Operations", "EXPENSE", "5000.00")
    exp28 = {o["label"]: o["id"] for o in env.selectable(fy28["id"], "WITHDRAWAL")}["1000 Operations"]
    a = base["acct"]["id"]
    d = env.txn(a, "DEPOSIT", [{"budget_id": base["inc_leaf"], "amount": "500.00"}], date="2026-08-01",
                clear_date="2026-08-03")
    chk = env.txn(a, "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "200.00"}], date="2027-06-28",
                  check_number="101", entity_id=env.entity("Paper Co")["id"])
    dep = env.txn(a, "DEPOSIT", [{"budget_id": base["inc_leaf"], "amount": "100.00"}], date="2027-06-30")
    return {"a": a, "fy27": base["fy"]["id"], "fy28": fy28["id"], "exp28": exp28, "dep500": d, "chk": chk, "dep100": dep}


def _reg(env, b, fy=None, client=None, **q):
    url = f"/api/register?bank_account_id={b['a']}" + (f"&fiscal_year_id={fy}" if fy else "")
    url += "".join(f"&{k}={v}" for k, v in q.items())
    r = (client or env.ru).get(url)
    assert r.status_code == 200, r.text
    return r.json()


def _clear(env, t, when):
    r = env.ru.patch(f"/api/transactions/{t['id']}", {"clear_date": when, "confirmations": ["CLEARED_EDIT"]})
    assert r.status_code == 200, r.text


def test_current_counts_cleared_only_available_counts_everything(env, book):
    r = _reg(env, book)
    assert r["current_balance"] == "1500.00"        # 1000 + 500 (the only cleared one)
    assert r["available_balance"] == "1400.00"      # 1000 + 500 - 200 + 100
    _clear(env, book["chk"], "2027-07-03")
    _clear(env, book["dep100"], "2027-07-02")
    r = _reg(env, book)
    assert r["current_balance"] == r["available_balance"] == "1400.00"


def test_current_balance_is_shown_everywhere_outside_the_register(env, book):
    acct = env.bu.get(f"/api/bank-accounts/{book['a']}").json()
    assert acct["current_balance"] == "1500.00" and "available_balance" not in acct
    assert {a["id"]: a["current_balance"] for a in env.bm.get("/api/bank-accounts").json()}[book["a"]] == "1500.00"
    d = env.bm.get("/api/dashboard").json()
    assert d["bank_accounts"][0]["current_balance"] == "1500.00" and d["bank_accounts_total"] == "1500.00"
    assert next(g for g in d["bank_account_groups"] if g["key"] == "CHECKING_SAVINGS")["total"] == "1500.00"


def test_void_counts_in_neither(env, book):
    r = env.ru.post(f"/api/transactions/{book['dep500']['id']}/void", {"reason": "entered twice", "confirm_irreversible": True})
    assert r.status_code == 200, r.text
    r = _reg(env, book)
    assert r["current_balance"] == "1000.00" and r["available_balance"] == "900.00"


def test_fiscal_year_opening_balance_is_available_with_bank_reconciliation(env, book):
    r = _reg(env, book, book["fy28"])
    assert r["starting_balance"] == "1400.00"
    rec = r["opening_reconciliation"]
    assert rec["as_of"] == "2027-06-30" and rec["bank_balance"] == "1500.00" and rec["balance"] == "1400.00"
    assert [(o["transaction_date"], o["check_number"], o["amount"]) for o in rec["outstanding"]] == \
        [("2027-06-28", "101", "-200.00"), ("2027-06-30", None, "100.00")]
    assert rec["outstanding"][0]["entity"] == "Paper Co" and rec["outstanding"][0]["clear_date"] is None


def test_clearing_last_years_items_later_changes_nothing(env, book):
    before = _reg(env, book, book["fy28"])
    _clear(env, book["chk"], "2027-07-03")
    _clear(env, book["dep100"], "2027-07-02")
    after = _reg(env, book, book["fy28"])
    assert after["starting_balance"] == before["starting_balance"] == "1400.00"
    assert after["opening_reconciliation"]["bank_balance"] == "1500.00"     # the bank had not posted them by Jun 30
    assert [o["clear_date"] for o in after["opening_reconciliation"]["outstanding"]] == ["2027-07-03", "2027-07-02"]
    # a clear date on or before the end of the year does move the bank balance on that date - the record is corrected
    _clear(env, book["dep100"], "2027-06-30")
    rec = _reg(env, book, book["fy28"])["opening_reconciliation"]
    assert rec["bank_balance"] == "1600.00" and len(rec["outstanding"]) == 1 and rec["balance"] == "1400.00"


def test_opening_balance_changes_only_with_last_years_transactions(env, book, base):
    env.txn(book["a"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "25.00"}], date="2027-06-29")
    assert _reg(env, book, book["fy28"])["starting_balance"] == "1375.00"


def test_open_year_has_no_ending_reconciliation_unless_a_to_date_is_chosen(env, book):
    r = _reg(env, book, book["fy28"])
    assert r["fiscal_year"]["status"] != "CLOSED"
    assert r["ending_reconciliation"] is not None   # the year's end is known; the page shows it only for a Closed year
    r = _reg(env, book)                              # all dates: no start or end
    assert r["opening_reconciliation"] is None and r["ending_reconciliation"] is None
    assert r["starting_balance"] == "1000.00"
    r = _reg(env, book, date_from="2026-08-02", date_to="2027-06-29")
    assert r["starting_balance"] == "1500.00" and r["opening_reconciliation"]["bank_balance"] == "1000.00"
    assert r["opening_reconciliation"]["outstanding"][0]["amount"] == "500.00"     # cleared Aug 3, after Aug 1
    assert r["ending_balance"] == "1300.00" and r["ending_reconciliation"]["bank_balance"] == "1500.00"


def test_closed_year_opening_and_ending(env, book):
    _clear(env, book["chk"], "2027-07-03")
    _clear(env, book["dep100"], "2027-07-02")
    env.approve(book["fy27"])
    env.fy_doc(book["fy27"], "AUDIT_SIGNOFF")
    r = env.bm.post(f"/api/fiscal-years/{book['fy27']}/close", {"confirm_reviewed": True})
    assert r.status_code == 200, r.text
    r = _reg(env, book, book["fy27"])
    assert r["fiscal_year"]["status"] == "CLOSED"
    assert r["starting_balance"] == "1000.00" and r["ending_balance"] == "1400.00"
    end = r["ending_reconciliation"]
    assert end["as_of"] == "2027-06-30" and end["bank_balance"] == "1500.00" and len(end["outstanding"]) == 2
    # the next year's opening balance can no longer change: last year's transactions are immutable
    r = env.ru.post("/api/transactions", {"bank_account_id": book["a"], "transaction_type": "WITHDRAWAL",
                                          "transaction_date": "2027-06-29",
                                          "allocations": [{"budget_id": book["exp28"], "amount": "1.00"}]})
    assert r.status_code in (409, 422)
    assert _reg(env, book, book["fy28"])["starting_balance"] == "1400.00"


@pytest.mark.parametrize("bad", ["2026-07-31", "2026-01-01"])
def test_clear_date_cannot_be_before_the_transaction_date(env, base, bad):
    a = base["acct"]["id"]
    r = env.ru.post("/api/transactions", {"bank_account_id": a, "transaction_type": "DEPOSIT", "transaction_date": "2026-08-01",
                                          "clear_date": bad, "allocations": [{"budget_id": base["inc_leaf"], "amount": "5.00"}]})
    assert r.status_code == 422, r.text
    e = r.json()["error"]
    assert e["message"] == "The Clear/Post Date cannot be earlier than the Transaction Date."
    assert e["errors"][0]["field"] == "clear_date"


def test_clear_date_rule_on_edit_and_same_day_allowed(env, base):
    a = base["acct"]["id"]
    t = env.txn(a, "DEPOSIT", [{"budget_id": base["inc_leaf"], "amount": "5.00"}], date="2026-08-01", clear_date="2026-08-01")
    assert t["clear_date"] == "2026-08-01"                                   # the same day is fine
    r = env.ru.patch(f"/api/transactions/{t['id']}", {"clear_date": "2026-07-30"})
    assert r.status_code == 422
    # moving the transaction date past its clear date is refused too
    r = env.ru.patch(f"/api/transactions/{t['id']}", {"transaction_date": "2026-08-05", "confirmations": ["CLEARED_EDIT"]})
    assert r.status_code == 422 and r.json()["error"]["errors"][0]["field"] == "clear_date"


def test_clear_date_rule_on_transfers(env, base):
    dst = env.account(account_name="Savings", atype="SAVINGS")
    r = env.ru.post("/api/transfers", {"from_account_id": base["acct"]["id"], "to_account_id": dst["id"], "amount": "10.00",
                                       "transaction_date": "2026-08-10", "clear_date": "2026-08-09"})
    assert r.status_code == 422 and r.json()["error"]["errors"][0]["field"] == "clear_date"


def test_auditor_reads_both_administrator_neither(env, book):
    r = _reg(env, book, book["fy28"], client=env.auditor)
    assert r["available_balance"] == "1400.00" and r["current_balance"] == "1500.00"
    assert env.admin.get(f"/api/register?bank_account_id={book['a']}").status_code == 403
