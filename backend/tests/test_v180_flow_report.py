"""1.8.0 (#106): Financial Flow Report - review lines, sections per account, totals and Difference, exclusions with
reasons (audit only), line notes, account balances with a Compare Date, access and validation."""
import datetime as dt
import io

import pytest
from pypdf import PdfReader

from conftest import Api

MINUS = "−"


@pytest.fixture
def book(env, base):
    a = base["acct"]["id"]                                    # Checking, opening 1000.00 on 2026-01-01
    sav = env.account(atype="SAVINGS", opening="500.00", account_name="Reserve")
    acme, jo, ann, kim = (env.entity(n) for n in ("Acme Supply", "Jo Donor", "Ann Donor", "Kim Donor"))
    ops, don = base["exp_leaf"], base["inc_leaf"]
    split_w = env.txn(a, "WITHDRAWAL", [{"budget_id": ops, "amount": "60.00", "description": "paper"},
                                        {"budget_id": ops, "amount": "40.00", "description": "ink"}],
                      date="2026-08-03", entity_id=acme["id"], clear_date="2026-08-05", notes="SECRET-TXN-NOTE")
    split_d = env.txn(a, "DEPOSIT", [{"budget_id": don, "amount": "100.00", "entity_id": jo["id"], "description": "gift"},
                                     {"budget_id": don, "amount": "150.00", "entity_id": ann["id"], "description": "gift"},
                                     {"budget_id": don, "amount": "50.00", "entity_id": kim["id"], "description": "gift"}],
                      date="2026-08-04", clear_date="2026-08-04")
    check = env.txn(a, "WITHDRAWAL", [{"budget_id": ops, "amount": "25.00", "description": "check 101"}],
                    date="2026-08-30", check_number="101")                     # uncleared
    void = env.txn(a, "WITHDRAWAL", [{"budget_id": ops, "amount": "999.00"}], date="2026-08-10")
    env.ru.post(f"/api/transactions/{void['id']}/void", {"reason": "dup", "confirm_irreversible": True})
    env.txn(a, "WITHDRAWAL", [{"budget_id": ops, "amount": "5.00"}], date="2026-07-31")          # before the period
    tr = env.ru.post("/api/transfers", {"from_account_id": a, "to_account_id": sav["id"], "amount": "70.00",
                                        "transaction_date": "2026-08-12"})
    assert tr.status_code == 201, tr.text
    return {"a": a, "sav": sav["id"], "split_w": split_w, "split_d": split_d, "check": check, "void": void}


def _body(book, **kw):
    return {"title": "August 2026", "date_from": "2026-08-01", "date_to": "2026-08-31", "bank_account_ids": [book["a"]], **kw}


def _review(env, body, client=None):
    r = (client or env.bu).post("/api/reports/financial-flow/review", body)
    assert r.status_code == 200, r.text
    return r.json()


def _pdf(env, body, client=None):
    r = (client or env.bu).post("/api/reports/financial-flow", body)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    return text


def test_lines_follow_the_rules(env, book):
    r = _review(env, _body(book))
    s = r["sections"][0]
    exp = [(x["date"], x["amount"], x["description"]) for x in s["expense"]]
    assert exp == [("2026-08-03", "100.00", "Acme Supply — paper; ink"),          # split withdrawal: one line
                   ("2026-08-30", "25.00", "check 101")]                               # uncleared check included
    inc = [(x["amount"], x["description"]) for x in s["income"]]
    assert inc == [("100.00", "Jo Donor — gift"), ("150.00", "Ann Donor — gift"), ("50.00", "Kim Donor — gift")]
    assert s["income_total"] == "300.00" and s["expense_total"] == "125.00" and s["difference"] == "175.00"
    assert r["summary"] is None and r["period"] == "08/01/2026 – 08/31/2026"
    assert set(s["expense"][0]) == {"key", "transaction_id", "allocation_id", "date", "amount", "description"}


def test_pdf_lists_lines_and_hides_transaction_notes(env, book):
    t = _pdf(env, _body(book))
    assert "August 2026" in t and "08/01/2026 – 08/31/2026" in t
    assert "$999.00" not in t and "$70.00" not in t and "$5.00" not in t      # void, transfer, outside the period
    assert "SECRET-TXN-NOTE" not in t and "Notes" not in t
    assert "+$175.00" in t and "$100.00" in t


def test_current_when_no_through_date(env, book):
    r = _review(env, _body(book, date_to=None))
    assert r["current"] is True and r["period"].endswith("– Current") and r["date_to"] == dt.date.today().isoformat()
    assert "Current" in _pdf(env, _body(book, date_to=None))


def test_two_accounts_sections_and_summary(env, book):
    other = env.account(opening="0.00")
    r = _review(env, _body(book, bank_account_ids=[other["id"], book["a"]]))
    assert [s["id"] for s in r["sections"]] == [book["a"], other["id"]]       # Bank Accounts order, not the request's
    empty = r["sections"][1]
    assert empty["income"] == [] and empty["expense"] == [] and empty["difference"] == "0.00"
    assert r["summary"] == {"income_total": "300.00", "expense_total": "125.00", "difference": "175.00"}
    t = _pdf(env, _body(book, bank_account_ids=[other["id"], book["a"]]))
    assert "No income in this period" in t and "No expenses in this period" in t and "Summary of all selected accounts" in t


def test_exclusion_needs_a_reason_and_is_audited_not_printed(env, book):
    r = _review(env, _body(book))
    w = r["sections"][0]["expense"][0]
    bad = env.bu.post("/api/reports/financial-flow", {**_body(book), "exclusions": [{"key": w["key"], "reason": "  "}]})
    assert bad.status_code == 422 and bad.json()["error"]["errors"][0]["field"] == "exclusions"
    unknown = env.bu.post("/api/reports/financial-flow", {**_body(book), "exclusions": [{"key": "t999999", "reason": "x"}]})
    assert unknown.status_code == 422
    t = _pdf(env, {**_body(book), "exclusions": [{"key": w["key"], "reason": "REASON-entered as two transactions"}]})
    assert "Acme Supply" not in t and "REASON-entered" not in t and "+$275.00" in t
    ev = env.auditor.get("/api/audit-events?action=REPORT_GENERATED").json()["items"][0]["after"]
    assert ev["report"] == "FINANCIAL_FLOW" and ev["title"] == "August 2026" and ev["bank_account_ids"] == [book["a"]]
    assert ev["exclusions"] == [{"key": w["key"], "transaction_id": book["split_w"]["id"], "allocation_id": None,
                                 "date": "2026-08-03", "amount": "100.00", "description": w["description"],
                                 "reason": "REASON-entered as two transactions"}]


def test_line_notes_add_the_column_everywhere_and_are_plain_text(env, book):
    other = env.account(opening="0.00")
    r = _review(env, _body(book, bank_account_ids=[book["a"], other["id"]]))
    inc = r["sections"][0]["income"][1]
    t = _pdf(env, {**_body(book, bank_account_ids=[book["a"], other["id"]]),
                   "line_notes": [{"key": inc["key"], "note": "<b>matching</b> <script>x</script>"}]})
    assert t.count("Notes") >= 4                                              # every table (2 accounts x 2 lists)
    assert "<b>matching</b> <script>x</script>" in t.replace("\n", " ")
    after = env.ru.get(f"/api/transactions/{book['split_d']['id']}").json()
    assert all("matching" not in (x.get("notes") or "") for x in after["allocations"])


def test_difference_negative_in_red_with_minus(env, base):
    a = base["acct"]["id"]
    env.txn(a, "DEPOSIT", [{"budget_id": base["inc_leaf"], "amount": "10.00"}], date="2026-08-02")
    env.txn(a, "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "30.00"}], date="2026-08-02")
    r = _review(env, {"title": "T", "date_from": "2026-08-01", "date_to": "2026-08-31", "bank_account_ids": [a]})
    assert r["sections"][0]["difference"] == "-20.00"
    t = _pdf(env, {"title": "T", "date_from": "2026-08-01", "date_to": "2026-08-31", "bank_account_ids": [a]})
    assert MINUS + "$20.00" in t


def test_balances_current_on_the_through_date_with_compare(env, book):
    inv = env.bm.post("/api/bank-accounts", {"account_name": "Brokerage", "financial_institution_entity_id": env.fi()["id"],
                                             "account_type": "INVESTMENT", "account_number": "5550001234",
                                             "register_enabled": False, "current_balance": "2000.00",
                                             "interest_rate": "4.25"})
    assert inv.status_code == 201, inv.text
    inv = inv.json()
    today = dt.date.today()
    env.bm.post(f"/api/bank-accounts/{inv['id']}/balance", {"current_balance": "1800.00", "as_of_date": (today - dt.timedelta(days=30)).isoformat()})
    body = _body(book, date_to=None, include_balances=True, compare_date=(today - dt.timedelta(days=10)).isoformat())
    r = _review(env, body)["balances"]
    secs = {s["key"]: s for s in r["sections"]}
    chk = secs["CHECKING"]["accounts"][0]
    # Checking: 1000 + 300 (cleared deposit) - 100 (cleared) - 70 (transfer, uncleared -> not counted) - 25 uncleared check
    assert chk["id"] == book["a"] and chk["balance"] == "1200.00"
    assert secs["SAVINGS"]["accounts"][0]["balance"] == "500.00"
    i = secs["INVESTMENTS"]["accounts"][0]
    assert (i["balance"], i["compare_balance"], i["change"], i["interest_rate"]) == ("2000.00", "1800.00", "200.00", "4.25")
    totals = {t["label"]: t for t in r["totals"]}
    assert totals["Total Checking & Savings"]["total"] == "1700.00" and totals["Total Assets"]["total"] == "3700.00"
    assert totals["Total Investments"]["change"] == "200.00"
    t = _pdf(env, body)
    assert "Total Assets" in t and "$3,700.00" in t and "+$200.00" in t and "4.25%" in t


def test_check_cleared_after_the_through_date_not_in_the_balance(env, book):
    env.ru.patch(f"/api/transactions/{book['check']['id']}", {"clear_date": "2026-09-02"})
    r = _review(env, _body(book, include_balances=True))
    s = r["sections"][0]
    assert any(x["transaction_id"] == book["check"]["id"] for x in s["expense"])
    chk = r["balances"]["sections"][0]["accounts"][0]
    assert chk["balance"] == "1200.00"                       # on 08/31: the check had not cleared (#56)


def test_closed_account_left_out_of_balances(env, book):
    gone = env.account(opening="0.00", account_name="Old checking")
    assert env.bm.post(f"/api/bank-accounts/{gone['id']}/close", {"reason": "moved"}).status_code == 200
    r = _review(env, _body(book, date_to=None, include_balances=True))
    ids = [a["id"] for s in r["balances"]["sections"] for a in s["accounts"]]
    assert gone["id"] not in ids and book["a"] in ids


def test_validation(env, book):
    def field(body):
        r = env.bu.post("/api/reports/financial-flow/review", body)
        assert r.status_code == 422, r.text
        return r.json()["error"]["errors"][0]["field"]
    assert field(_body(book, compare_date="2026-08-31", include_balances=True)) == "compare_date"
    assert field(_body(book, compare_date="2026-09-30", include_balances=True)) == "compare_date"
    assert field(_body(book, compare_date="2026-07-31")) == "compare_date"            # needs Include Bank Balances
    assert field(_body(book, date_from="2026-09-01")) == "date_to"
    assert env.bu.post("/api/reports/financial-flow/review", _body(book, bank_account_ids=[])).status_code == 422
    assert env.bu.post("/api/reports/financial-flow/review", _body(book, title="")).status_code == 422


def test_notes_printed_as_plain_text(env, book):
    t = _pdf(env, _body(book, notes="$650.00 cash <i>re-deposited</i> & <script>alert(1)</script>"))
    assert "<i>re-deposited</i> & <script>alert(1)</script>" in t


def test_access(env, book):
    for c in (env.bm, env.bu, env.ru, env.auditor):
        _review(env, _body(book), client=c)
    assert env.admin.post("/api/reports/financial-flow/review", _body(book)).status_code == 403
    assert env.admin.post("/api/reports/financial-flow", _body(book)).status_code == 403
    assert Api(env.app).post("/api/reports/financial-flow", _body(book)).status_code == 401
    assert env.bu.post("/api/reports/financial-flow/review", _body(book, bank_account_ids=[999999])).status_code == 404
    inv = env.bm.post("/api/bank-accounts", {"account_name": "Brokerage", "financial_institution_entity_id": env.fi()["id"],
                                             "account_type": "INVESTMENT", "account_number": "5550009999",
                                             "register_enabled": False, "current_balance": "1.00"}).json()
    r = env.bu.post("/api/reports/financial-flow/review", _body(book, bank_account_ids=[inv["id"]]))
    assert r.status_code == 422 and r.json()["error"]["errors"][0]["field"] == "bank_account_ids"


def test_other_workspace_account_refused(env, book, app):
    from fmpoc.models import BankAccount, Workspace
    with app.state.session_factory() as db:
        ws = Workspace(name="Other org")
        db.add(ws)
        db.flush()
        src = db.get(BankAccount, book["a"])
        o = BankAccount(workspace_id=ws.id, financial_institution_entity_id=src.financial_institution_entity_id,
                        account_name="Theirs", account_type="CHECKING", account_number_ciphertext="x",
                        account_number_fingerprint="fp-other", account_number_visible_suffix="0000")
        db.add(o)
        db.commit()
        oid = o.id
    assert env.bu.post("/api/reports/financial-flow/review", _body(book, bank_account_ids=[oid])).status_code == 404
