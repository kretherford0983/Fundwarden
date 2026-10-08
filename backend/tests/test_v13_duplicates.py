"""v1.3 CR-011: duplicate-transaction protection and check-number rules."""
import threading

from conftest import Api

KEY = "0123456789abcdef0123456789abcdef"


def body(base, **kw):
    b = {"bank_account_id": base["acct"]["id"], "transaction_type": "WITHDRAWAL", "transaction_date": "2026-08-05",
         "allocations": [{"budget_id": base["exp_leaf"], "amount": "25.00", "description": "Supplies"}]}
    b.update(kw)
    return b


def txns(env, base):
    return env.bu.get(f"/api/register?bank_account_id={base['acct']['id']}").json()["transactions"]


def test_cr011_request_key_replay_returns_same_transaction(env, base):
    r1 = env.ru.post("/api/transactions", body(base, request_key=KEY))
    r2 = env.ru.post("/api/transactions", body(base, request_key=KEY))
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert len(txns(env, base)) == 1
    assert env.auditor.get("/api/audit-events?action=TRANSACTION_CREATED").json()["total"] == 1
    # a key used for a transaction cannot be replayed as a different kind of request
    dst = env.account(opening="0.00")
    r = env.ru.post("/api/transfers", {"from_account_id": base["acct"]["id"], "to_account_id": dst["id"],
                                       "amount": "1.00", "request_key": KEY})
    assert r.status_code == 409 and r.json()["error"]["code"] == "REQUEST_KEY_REUSED"
    # malformed keys are rejected by validation
    assert env.ru.post("/api/transactions", body(base, request_key="short")).status_code == 422
    assert env.ru.post("/api/transactions", body(base, request_key="x" * 16 + "<>")).status_code == 422


def test_cr011_failed_submit_does_not_consume_key(env, base):
    # first submit needs a confirmation (no covering FY) -> nothing stored, the same key works on resubmit
    b = body(base, request_key=KEY, transaction_date="2029-01-01")
    r = env.ru.post("/api/transactions", b)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFIRMATION_REQUIRED"
    r = env.ru.post("/api/transactions", {**b, "confirmations": ["NO_FISCAL_YEAR"]})
    assert r.status_code == 201, r.text
    assert len(txns(env, base)) == 1


def test_cr011_concurrent_double_submit_creates_one(env, base):
    other = Api(env.app)
    other.login("reguser")
    results = []

    def go(client):
        results.append(client.post("/api/transactions", body(base, request_key=KEY)))

    threads = [threading.Thread(target=go, args=(c,)) for c in (env.ru, other, env.ru, other)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [r.status_code for r in results] == [201] * 4, [r.text for r in results]
    assert len({r.json()["id"] for r in results}) == 1
    assert len(txns(env, base)) == 1


def test_cr011_transfer_request_key(env, base):
    dst = env.account(opening="0.00")
    b = {"from_account_id": base["acct"]["id"], "to_account_id": dst["id"], "amount": "10.00", "request_key": KEY}
    r1, r2 = env.ru.post("/api/transfers", b), env.ru.post("/api/transfers", b)
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["withdrawal"]["id"] == r2.json()["withdrawal"]["id"]
    assert env.bu.get(f"/api/register?bank_account_id={dst['id']}").json()["available_balance"] == "10.00"  # once


def test_cr011_possible_duplicate_warning(env, base):
    vendor = env.entity("Paper Co")
    assert env.ru.post("/api/transactions", body(base, entity_id=vendor["id"])).status_code == 201
    r = env.ru.post("/api/transactions", body(base, entity_id=vendor["id"]))
    assert r.status_code == 409
    w = r.json()["error"]["warnings"][0]
    assert w["code"] == "POSSIBLE_DUPLICATE" and "#1" in w["message"]
    # different amount, date, type or entity -> no warning
    assert env.ru.post("/api/transactions", body(base, entity_id=vendor["id"], transaction_date="2026-08-06")).status_code == 201
    assert env.ru.post("/api/transactions", body(base)).status_code == 201  # no entity
    alloc = [{"budget_id": base["exp_leaf"], "amount": "25.01"}]
    assert env.ru.post("/api/transactions", body(base, entity_id=vendor["id"], allocations=alloc)).status_code == 201
    # confirming saves the genuine second transaction
    r = env.ru.post("/api/transactions", body(base, entity_id=vendor["id"], confirmations=["POSSIBLE_DUPLICATE"]))
    assert r.status_code == 201
    # VOID transactions don't count
    env.ru.post(f"/api/transactions/{r.json()['id']}/void", {"reason": "dup", "confirm_irreversible": True})
    env.ru.post("/api/transactions/1/void", {"reason": "dup", "confirm_irreversible": True})
    assert env.ru.post("/api/transactions", body(base, entity_id=vendor["id"])).status_code == 201


def test_cr011_check_number_hard_block(env, base):
    a = base["acct"]["id"]
    t = env.ru.post("/api/transactions", body(base, check_number="1045")).json()
    for num in ("1045", "01045"):
        r = env.ru.post("/api/transactions", body(base, check_number=num, transaction_date="2026-08-09"))
        assert r.status_code == 409 and r.json()["error"]["code"] == "DUPLICATE_CHECK_NUMBER"
        assert r.json()["error"]["transaction_id"] == t["id"]
    # other accounts have their own checkbooks
    other = env.account(opening="100.00")
    assert env.ru.post("/api/transactions", body(base, bank_account_id=other["id"], check_number="1045")).status_code == 201
    # editing another transaction onto a used number is blocked; keeping your own number is fine
    t2 = env.ru.post("/api/transactions", body(base, check_number="1046", transaction_date="2026-08-10")).json()
    r = env.ru.patch(f"/api/transactions/{t2['id']}", {"check_number": "1045"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "DUPLICATE_CHECK_NUMBER"
    assert env.ru.patch(f"/api/transactions/{t2['id']}", {"check_number": "1046", "notes": "x"}).status_code == 200
    # a VOID transaction keeps its number reserved (lost check is never reused)
    env.ru.post(f"/api/transactions/{t['id']}/void", {"reason": "Check lost", "confirm_irreversible": True})
    r = env.ru.post("/api/transactions", body(base, check_number="1045", transaction_date="2026-08-11"))
    assert r.status_code == 409
    # a zero-dollar VOID record reserves its number too, and cannot take a used one
    z = {"bank_account_id": a, "transaction_type": "WITHDRAWAL", "transaction_date": "2026-08-12",
         "create_as_void": True, "void_reason": "Spoiled"}
    assert env.ru.post("/api/transactions", {**z, "check_number": "1046"}).status_code == 409
    assert env.ru.post("/api/transactions", {**z, "check_number": "1047"}).status_code == 201
    assert env.ru.post("/api/transactions", body(base, check_number="1047", transaction_date="2026-08-13")).status_code == 409


def test_cr011_void_check_number_correction(env, base):
    wrong = env.ru.post("/api/transactions", body(base, check_number="2001")).json()
    env.ru.post(f"/api/transactions/{wrong['id']}/void", {"reason": "Wrong check number", "confirm_irreversible": True})
    env.ru.post("/api/transactions", body(base, check_number="2002", transaction_date="2026-08-07"))
    url = f"/api/transactions/{wrong['id']}/void-check-number"
    # reason required; permissions; CSRF
    assert env.ru.post(url, {"check_number": None}).status_code == 422
    assert env.bu.post(url, {"check_number": None, "reason": "x"}).status_code == 403
    assert env.ru.c.post(url, json={"check_number": None, "reason": "x"}).status_code == 403
    # changing to a number used elsewhere is blocked
    r = env.ru.post(url, {"check_number": "2002", "reason": "typo"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "DUPLICATE_CHECK_NUMBER"
    # clearing frees the number
    r = env.ru.post(url, {"check_number": None, "reason": "Entered the wrong check number"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["check_number"] is None and v["status"] == "VOID" and v["total"] == "25.00"
    assert "Check number corrected from 2001 to (none): Entered the wrong check number" in v["notes"]
    assert env.ru.post("/api/transactions", body(base, check_number="2001", transaction_date="2026-08-08")).status_code == 201
    # changing to a free number works; unchanged is refused
    assert env.ru.post(url, {"check_number": "2010", "reason": "actual number"}).json()["check_number"] == "2010"
    assert env.ru.post(url, {"check_number": "2010", "reason": "again"}).status_code == 409
    ev = env.auditor.get(f"/api/audit-events?action=TRANSACTION_VOID_CHECK_NUMBER_CORRECTED&object_id={wrong['id']}").json()
    assert ev["total"] == 2 and ev["items"][-1]["after"]["old_check_number"] == "2001"
    # only VOID records; active ones are edited normally
    active = env.ru.post("/api/transactions", body(base, check_number="2020", transaction_date="2026-08-20")).json()
    assert env.ru.post(f"/api/transactions/{active['id']}/void-check-number",
                       {"check_number": None, "reason": "x"}).json()["error"]["code"] == "NOT_VOID"


def test_cr011_void_check_number_closed_fiscal_year(env, base):
    fy = base["fy"]["id"]
    t = env.ru.post("/api/transactions", {"bank_account_id": base["acct"]["id"], "transaction_type": "WITHDRAWAL",
                                          "transaction_date": "2026-08-01", "check_number": "3001",
                                          "create_as_void": True, "void_reason": "Spoiled"}).json()
    env.approve(fy)
    env.fy_doc(fy, "AUDIT_SIGNOFF")
    assert env.bm.post(f"/api/fiscal-years/{fy}/close", {"confirm_reviewed": True}).status_code == 200
    r = env.ru.post(f"/api/transactions/{t['id']}/void-check-number", {"check_number": None, "reason": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "FISCAL_YEAR_CLOSED"
