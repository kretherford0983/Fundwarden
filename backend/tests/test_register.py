"""Register transactions & allocations. AC-REG-001..019."""
import datetime as dt


def test_ac_reg_001_parent_allocation_model(env, base):
    t = env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "10.00"}])
    assert len(t["allocations"]) == 1 and t["is_split"] is False
    r = env.ru.post("/api/transactions", {"bank_account_id": base["acct"]["id"], "transaction_type": "WITHDRAWAL",
                                          "allocations": []})
    assert r.status_code == 422


def test_ac_reg_002_dates(env, base):
    r = env.ru.post("/api/transactions", {"bank_account_id": base["acct"]["id"], "transaction_type": "DEPOSIT",
                                          "allocations": [{"budget_id": base["inc_leaf"], "amount": "1.00"}],
                                          "confirmations": ["CROSS_FY_ALLOCATION", "NO_FISCAL_YEAR"]})
    assert r.status_code == 201
    t = r.json()
    assert t["transaction_date"] == dt.date.today().isoformat()
    ts = t["entry_timestamp"]
    # entry timestamp is not user-settable
    r = env.ru.patch(f"/api/transactions/{t['id']}", {"entry_timestamp": "2000-01-01T00:00:00"})
    assert r.status_code == 422
    r = env.ru.post("/api/transactions", {"bank_account_id": base["acct"]["id"], "transaction_type": "DEPOSIT",
                                          "entry_timestamp": "2000-01-01T00:00:00",
                                          "allocations": [{"budget_id": base["inc_leaf"], "amount": "1.00"}]})
    assert r.status_code == 422
    # transaction date is editable
    r = env.ru.patch(f"/api/transactions/{t['id']}", {"transaction_date": "2026-09-01"})
    assert r.status_code == 200 and r.json()["transaction_date"] == "2026-09-01" and r.json()["entry_timestamp"] == ts


def test_ac_reg_003_budget_type_filtering(env, base):
    fy = base["fy"]["id"]
    dep = [o for o in env.selectable(fy, "DEPOSIT") if not o["is_budget_zero"]]
    wd = [o for o in env.selectable(fy, "WITHDRAWAL") if not o["is_budget_zero"]]
    assert {o["budget_type"] for o in dep} == {"INCOME"} and {o["budget_type"] for o in wd} == {"EXPENSE"}
    r = env.ru.post("/api/transactions", {"bank_account_id": base["acct"]["id"], "transaction_type": "DEPOSIT",
                                          "transaction_date": "2026-08-01",
                                          "allocations": [{"budget_id": base["exp_leaf"], "amount": "1.00"}]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BUDGET_TYPE_MISMATCH"
    # Budget 0 explicit system exception - requires confirmation when chosen manually
    b0 = [o for o in env.selectable(fy, "DEPOSIT") if o["is_budget_zero"]][0]
    body = {"bank_account_id": base["acct"]["id"], "transaction_type": "DEPOSIT", "transaction_date": "2026-08-01",
            "notes": "micro-deposit verification", "allocations": [{"budget_id": b0["id"], "amount": "0.12"}]}
    r = env.ru.post("/api/transactions", body)
    assert r.status_code == 409 and r.json()["error"]["warnings"][0]["code"] == "BUDGET_ZERO"
    assert env.ru.post("/api/transactions", {**body, "confirmations": ["BUDGET_ZERO"]}).status_code == 201


def test_ac_reg_004_006_cross_fy_confirmation_and_review(env, base):
    nxt = env.fy("2028", "2027-07-01", "2028-06-30")
    env.budget(nxt["id"], "1000", "Operations Next", "EXPENSE", "10.00")
    leaf_next = env.selectable(nxt["id"], "WITHDRAWAL")[0]["id"]
    body = {"bank_account_id": base["acct"]["id"], "transaction_type": "WITHDRAWAL", "transaction_date": "2027-06-20",
            "allocations": [{"budget_id": leaf_next, "amount": "7.00"}]}
    r = env.ru.post("/api/transactions", body)
    assert r.status_code == 409
    w = r.json()["error"]["warnings"][0]
    assert w["code"] == "CROSS_FY_ALLOCATION" and w["details"]["budget_fiscal_year"]["display_name"] == "FY2028"
    t = env.ru.post("/api/transactions", {**body, "confirmations": ["CROSS_FY_ALLOCATION"]}).json()
    rv = t["allocations"][0]["reviews"][0]
    assert rv["category"] == "CROSS_FY" and rv["status"] == "PENDING" and t["has_pending_review"]
    pending = env.bm.get("/api/fiscal-year-reviews").json()
    assert [p["id"] for p in pending] == [rv["id"]]
    assert env.bu.post(f"/api/fiscal-year-reviews/{rv['id']}/confirm", {}).status_code == 403
    assert env.ru.post(f"/api/fiscal-year-reviews/{rv['id']}/confirm", {"note": "prepaid"}).status_code == 200
    # AC-REG-006: remains valid, no longer unresolved
    assert env.bm.get("/api/fiscal-year-reviews").json() == []
    t2 = env.ru.get(f"/api/transactions/{t['id']}").json()
    assert t2["status"] == "ACTIVE" and t2["allocations"][0]["reviews"][0]["status"] == "REVIEWED"
    assert env.bm.get(f"/api/budgets?fiscal_year_id={nxt['id']}").json()["expense"][0]["actual"] == "7.00"


def test_ac_reg_005_missing_natural_fiscal_year(env, base):
    nat = env.ru.get("/api/fiscal-years/natural?date=2028-02-01").json()
    assert nat["no_fiscal_year"] and nat["closest"]["display_name"] == "FY2027" and nat["default_fiscal_year_id"] is None
    body = {"bank_account_id": base["acct"]["id"], "transaction_type": "WITHDRAWAL", "transaction_date": "2028-02-01",
            "allocations": [{"budget_id": base["exp_leaf"], "amount": "3.00"}]}
    r = env.ru.post("/api/transactions", body)
    assert r.status_code == 409
    w = r.json()["error"]["warnings"][0]
    assert w["code"] == "NO_FISCAL_YEAR" and w["details"]["closest_fiscal_year"]["display_name"] == "FY2027"
    t = env.ru.post("/api/transactions", {**body, "confirmations": ["NO_FISCAL_YEAR"]}).json()
    assert t["allocations"][0]["reviews"][0]["category"] == "NO_FISCAL_YEAR"
    # when an appropriate FY is later created the pending review is still listed
    env.fy("2028", "2027-07-01", "2028-06-30")
    assert len(env.bm.get("/api/fiscal-year-reviews").json()) == 1


def test_review_reassignment_resolves(env, base):
    nxt = env.fy("2028", "2027-07-01", "2028-06-30")
    env.budget(nxt["id"], "1000", "Ops 28")
    leaf_next = env.selectable(nxt["id"], "WITHDRAWAL")[0]["id"]
    t = env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "3.00"}],
                date="2027-08-01", confirmations=["CROSS_FY_ALLOCATION"])
    aid = t["allocations"][0]["id"]
    r = env.ru.patch(f"/api/transactions/{t['id']}", {"allocations": [{"id": aid, "budget_id": leaf_next, "amount": "3.00"}]})
    assert r.status_code == 200
    assert r.json()["allocations"][0]["reviews"][0]["status"] == "REASSIGNED"
    assert env.bm.get("/api/fiscal-year-reviews").json() == []


def test_ac_reg_007_split_withdrawal(env, base):
    fy = base["fy"]["id"]
    p = env.budget(fy, "2000", "Programs", "EXPENSE", "1000.00")
    env.budget(fy, "01", "Supplies", amount="300.00", parent=p["id"])
    opts = {o["label"]: o["id"] for o in env.selectable(fy, "WITHDRAWAL")}
    payee = env.entity("Office Depot")
    other = env.entity("Someone Else")
    allocs = [{"budget_id": base["exp_leaf"], "amount": "600.00", "invoice_number": "INV-1", "description": "Rent",
               "notes": "n1"},
              {"budget_id": opts["2000-01 Supplies"], "amount": "400.00", "invoice_number": "INV-2", "description": "Paper"}]
    t = env.txn(base["acct"]["id"], "WITHDRAWAL", allocs, entity_id=payee["id"], check_number="1042")
    assert t["is_split"] and t["entity"]["id"] == payee["id"]
    assert all(a["entity"]["id"] == payee["id"] for a in t["allocations"])
    assert [a["invoice_number"] for a in t["allocations"]] == ["INV-1", "INV-2"]
    bad = [dict(allocs[0]), dict(allocs[1], entity_id=other["id"])]
    r = env.ru.post("/api/transactions", {"bank_account_id": base["acct"]["id"], "transaction_type": "WITHDRAWAL",
                                          "transaction_date": "2026-08-01", "entity_id": payee["id"], "allocations": bad})
    assert r.status_code == 422


def test_ac_reg_008_split_deposit_multiple(env, base):
    fy = base["fy"]["id"]
    inc2 = env.budget(fy, "4100", "Dues", "INCOME", "100.00")
    opts = {o["label"]: o["id"] for o in env.selectable(fy, "DEPOSIT")}
    a, b = env.entity("Donor A", "INDIVIDUAL"), env.entity("Donor B", "INDIVIDUAL")
    t = env.txn(base["acct"]["id"], "DEPOSIT", [
        {"budget_id": opts["4000 Donations"], "entity_id": a["id"], "amount": "50.00", "description": "gift"},
        {"budget_id": opts["4100 Dues"], "entity_id": b["id"], "amount": "25.00"}])
    assert t["entity"]["display_name"] == "Multiple" and t["entity"]["is_system"] is True
    assert [x["entity"]["display_name"] for x in t["allocations"]] == ["Donor A", "Donor B"]
    assert t["deposit"] == "75.00"
    # Multiple cannot be selected manually
    mult_id = t["entity"]["id"]
    r = env.ru.post("/api/transactions", {"bank_account_id": base["acct"]["id"], "transaction_type": "DEPOSIT",
                                          "transaction_date": "2026-08-01", "entity_id": mult_id,
                                          "allocations": [{"budget_id": opts["4100 Dues"], "amount": "1.00"}]})
    assert r.status_code == 422
    assert inc2


def test_ac_reg_009_010_011_derived_total_and_single_count(env, base):
    fy = base["fy"]["id"]
    p = env.budget(fy, "2000", "Programs", "EXPENSE", "5000.00")
    env.budget(fy, "01", "Supplies", amount="3000.00", parent=p["id"])
    opts = {o["label"]: o["id"] for o in env.selectable(fy, "WITHDRAWAL")}
    t = env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "600.00"},
                                                    {"budget_id": opts["2000-01 Supplies"], "amount": "400.00"}])
    assert t["total"] == "1000.00"
    a1, a2 = t["allocations"]
    r = env.ru.patch(f"/api/transactions/{t['id']}", {"allocations": [
        {"id": a1["id"], "budget_id": a1["budget_id"], "amount": "600.00"},
        {"id": a2["id"], "budget_id": a2["budget_id"], "amount": "500.00"}]})
    assert r.status_code == 200 and r.json()["total"] == "1100.00"
    # a client-supplied parent amount is not accepted
    assert env.ru.patch(f"/api/transactions/{t['id']}", {"total": "5.00"}).status_code == 422
    # AC-REG-010: the balance decreases by exactly 1100 (Available until it clears; 1.7.2, #56)
    assert env.bu.get(f"/api/register?bank_account_id={base['acct']['id']}").json()["available_balance"] == "-100.00"
    env.ru.patch(f"/api/transactions/{t['id']}", {"clear_date": "2026-08-02"})
    assert env.bu.get(f"/api/bank-accounts/{base['acct']['id']}").json()["current_balance"] == "-100.00"
    # AC-REG-011: each allocation affects only its own budget; parent roll-up derives from children
    tree = env.bu.get(f"/api/budgets?fiscal_year_id={fy}").json()["expense"]
    ops = [x for x in tree if x["display_code"] == "1000"][0]
    prog = [x for x in tree if x["display_code"] == "2000"][0]
    assert ops["actual"] == "600.00"
    assert prog["actual"] == "500.00" and prog["children"][0]["actual"] == "500.00"


def test_ac_reg_012_cleared_edit_confirmation(env, base):
    t = env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "10.00"}],
                clear_date="2026-08-02")
    aid = t["allocations"][0]["id"]
    body = {"allocations": [{"id": aid, "budget_id": base["exp_leaf"], "amount": "12.00"}]}
    r = env.ru.patch(f"/api/transactions/{t['id']}", body)
    assert r.status_code == 409 and r.json()["error"]["warnings"][0]["code"] == "CLEARED_EDIT"
    assert env.ru.get(f"/api/transactions/{t['id']}").json()["total"] == "10.00"
    r = env.ru.patch(f"/api/transactions/{t['id']}", {**body, "confirmations": ["CLEARED_EDIT"]})
    assert r.status_code == 200 and r.json()["total"] == "12.00"
    ev = env.auditor.get(f"/api/audit-events?action=TRANSACTION_UPDATED&object_id={t['id']}").json()["items"][0]
    assert ev["before"]["total"] == "10.00" and ev["after"]["total"] == "12.00"
    assert "CLEARED_EDIT" in ev["after"]["confirmed_warnings"]


def test_ac_reg_013_type_change_protected(env, base):
    t = env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "10.00"}],
                check_number="555")
    aid = t["allocations"][0]["id"]
    # allocations must be re-selected
    assert env.ru.patch(f"/api/transactions/{t['id']}", {"transaction_type": "DEPOSIT",
                                                         "confirmations": ["TYPE_CHANGE"]}).status_code == 422
    # incompatible budget rejected
    r = env.ru.patch(f"/api/transactions/{t['id']}", {"transaction_type": "DEPOSIT", "check_number": None,
                                                      "allocations": [{"id": aid, "budget_id": base["exp_leaf"], "amount": "10.00"}],
                                                      "confirmations": ["TYPE_CHANGE"]})
    assert r.status_code == 422
    # check number must be cleared
    r = env.ru.patch(f"/api/transactions/{t['id']}", {"transaction_type": "DEPOSIT",
                                                      "allocations": [{"id": aid, "budget_id": base["inc_leaf"], "amount": "10.00"}],
                                                      "confirmations": ["TYPE_CHANGE"]})
    assert r.status_code == 422
    body = {"transaction_type": "DEPOSIT", "check_number": None,
            "allocations": [{"id": aid, "budget_id": base["inc_leaf"], "amount": "10.00"}]}
    r = env.ru.patch(f"/api/transactions/{t['id']}", body)
    assert r.status_code == 409 and r.json()["error"]["warnings"][0]["code"] == "TYPE_CHANGE"
    r = env.ru.patch(f"/api/transactions/{t['id']}", {**body, "confirmations": ["TYPE_CHANGE"]})
    assert r.status_code == 200 and r.json()["transaction_type"] == "DEPOSIT"
    assert env.bu.get(f"/api/register?bank_account_id={base['acct']['id']}").json()["available_balance"] == "1010.00"


def test_ac_reg_014_no_hard_delete(env, base):
    t = env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "10.00"}])
    for c in (env.ru, env.bm, env.admin, env.auditor):
        assert c.delete(f"/api/transactions/{t['id']}").status_code in (403, 404, 405)
    assert env.ru.get(f"/api/transactions/{t['id']}").status_code == 200


def test_ac_reg_015_016_017_void(env, base):
    t = env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "250.00"}])
    assert env.ru.post(f"/api/transactions/{t['id']}/void", {"reason": "", "confirm_irreversible": True}).status_code == 422
    assert env.ru.post(f"/api/transactions/{t['id']}/void", {"reason": "dup", "confirm_irreversible": False}).status_code == 409
    assert env.bm.post(f"/api/transactions/{t['id']}/void", {"reason": "dup", "confirm_irreversible": True}).status_code == 403
    r = env.ru.post(f"/api/transactions/{t['id']}/void", {"reason": "Duplicate entry", "confirm_irreversible": True})
    assert r.status_code == 200 and r.json()["status"] == "VOID" and r.json()["void_reason"] == "Duplicate entry"
    assert env.bu.get(f"/api/bank-accounts/{base['acct']['id']}").json()["current_balance"] == "1000.00"
    assert env.bu.get(f"/api/budgets?fiscal_year_id={base['fy']['id']}").json()["expense"][0]["actual"] == "0.00"
    reg = env.bu.get(f"/api/register?bank_account_id={base['acct']['id']}").json()["transactions"]
    assert reg[0]["status"] == "VOID" and reg[0]["allocations"][0]["amount"] == "250.00"
    # irreversible
    assert env.ru.post(f"/api/transactions/{t['id']}/void", {"reason": "x", "confirm_irreversible": True}).status_code == 409
    assert env.ru.patch(f"/api/transactions/{t['id']}", {"status": "ACTIVE"}).status_code == 422
    assert env.ru.patch(f"/api/transactions/{t['id']}", {"notes": "x"}).status_code == 409
    assert env.ru.post(f"/api/transactions/{t['id']}/unvoid", {}).status_code == 404


def test_ac_reg_018_void_attachments(env, base):
    from conftest import PDF_BYTES, png_bytes
    t = env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "5.00"}])
    up = lambda name, data: env.ru.c.post(f"/api/attachments?owner_type=transaction&owner_id={t['id']}",
                                          files={"file": (name, data)}, headers={"X-CSRF-Token": env.ru.csrf})
    a1 = up("receipt.pdf", PDF_BYTES).json()
    env.ru.post(f"/api/transactions/{t['id']}/void", {"reason": "error", "confirm_irreversible": True})
    assert env.ru.post(f"/api/attachments/{a1['id']}/remove").status_code == 409
    assert up("followup.png", png_bytes()).status_code == 201
    assert env.ru.post(f"/api/transactions/{t['id']}/notes", {"note": "Bank confirmed reversal"}).status_code == 200
    t2 = env.ru.get(f"/api/transactions/{t['id']}").json()
    assert t2["attachment_count"] == 2 and "Bank confirmed reversal" in t2["notes"] and t2["total"] == "5.00"


def test_ac_reg_019_zero_dollar_void(env, base):
    # active zero-dollar transaction is not permitted
    r = env.ru.post("/api/transactions", {"bank_account_id": base["acct"]["id"], "transaction_type": "WITHDRAWAL",
                                          "transaction_date": "2026-08-01",
                                          "allocations": [{"budget_id": base["exp_leaf"], "amount": "0.00"}]})
    assert r.status_code == 422
    body = {"bank_account_id": base["acct"]["id"], "transaction_type": "WITHDRAWAL", "transaction_date": "2026-08-01",
            "check_number": "1001", "create_as_void": True}
    assert env.ru.post("/api/transactions", body).status_code == 422  # reason required
    r = env.ru.post("/api/transactions", {**body, "void_reason": "Check physically damaged; unused"})
    assert r.status_code == 201
    t = r.json()
    assert t["status"] == "VOID" and t["total"] == "0.00"
    assert t["allocations"][0]["budget"]["is_budget_zero"] is True
    assert env.bu.get(f"/api/bank-accounts/{base['acct']['id']}").json()["current_balance"] == "1000.00"


def test_register_filters_and_search(env, base):
    a = base["acct"]["id"]
    v = env.entity("Zeta Plumbing")
    env.txn(a, "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "10.00", "invoice_number": "Z-77"}],
            entity_id=v["id"], check_number="2001", clear_date="2026-08-02")
    env.txn(a, "DEPOSIT", [{"budget_id": base["inc_leaf"], "amount": "20.00", "description": "bake sale"}],
            date="2026-09-01")
    q = lambda s: env.bu.get(f"/api/register?bank_account_id={a}&{s}").json()["transactions"]
    assert len(q("transaction_type=DEPOSIT")) == 1
    assert len(q("status=cleared")) == 1 and len(q("status=uncleared")) == 1
    assert len(q("search=zeta")) == 1 and len(q("search=Z-77")) == 1 and len(q("search=2001")) == 1
    assert len(q("search=bake")) == 1 and len(q("search=20.00")) == 1
    assert len(q("date_from=2026-08-15&date_to=2026-12-31")) == 1
    assert len(q(f"fiscal_year_id={base['fy']['id']}")) == 2
    assert q("sort=amount&direction=desc")[0]["total"] == "20.00"
