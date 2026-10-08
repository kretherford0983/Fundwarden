"""v1.4.1 CR-020: dashboard chart data and per-user chart selection."""


def _charts(client, fy):
    r = client.get(f"/api/dashboard/charts?fiscal_year_id={fy}")
    assert r.status_code == 200, r.text
    return r.json()


def test_chart_data(env, base):
    fy, a = base["fy"]["id"], base["acct"]["id"]
    inc2 = env.budget(fy, "4100", "Grants", "INCOME", "1000.00")
    small = env.budget(fy, "4200", "Interest", "INCOME", "10.00")
    opts = {o["label"]: o["id"] for o in env.selectable(fy, "DEPOSIT")}
    env.txn(a, "DEPOSIT", [{"budget_id": base["inc_leaf"], "amount": "600.00"}], date="2026-07-15")
    env.txn(a, "DEPOSIT", [{"budget_id": opts["4100 Grants"], "amount": "390.00"}], date="2026-08-10")
    env.txn(a, "DEPOSIT", [{"budget_id": opts["4200 Interest"], "amount": "10.00"}], date="2026-08-31")  # 1 % -> Other
    env.txn(a, "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "250.00"}], date="2026-08-20")
    v = env.txn(a, "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "999.00"}], date="2026-08-21")
    env.ru.post(f"/api/transactions/{v['id']}/void", {"reason": "x", "confirm_irreversible": True})
    b = env.account(opening="0.00")
    r = env.ru.post("/api/transfers", {"from_account_id": a, "to_account_id": b["id"], "transaction_date": "2026-08-05",
                                       "amount": "100.00"})
    assert r.status_code == 201, r.text
    d = _charts(env.bu, fy)
    assert d["months"][:2] == ["Jul 2026", "Aug 2026"] and len(d["months"]) == 12
    pie = d["income_by_budget"]
    assert pie["total"] == "1000.00"
    assert [s["label"] for s in pie["slices"]] == ["4000 Donations", "4100 Grants", "Other"]
    assert pie["slices"][0]["share"] == 0.6 and pie["slices"][-1]["amount"] == "10.00"
    assert d["expense_by_budget"]["slices"] == [{"label": "1000 Operations", "amount": "250.00", "share": 1.0}]
    # monthly: VOID and transfers (Budget 0) excluded
    assert d["monthly"][0] == {"month": "Jul 2026", "income": "600.00", "expense": "0.00"}
    assert d["monthly"][1] == {"month": "Aug 2026", "income": "400.00", "expense": "250.00"}
    assert d["cumulative_net"][1]["net"] == "750.00"
    import datetime as dt
    if dt.date.today() < dt.date(2027, 6, 1):  # months that have not started have no value
        assert d["cumulative_net"][-1]["net"] is None and d["monthly"][-1]["income"] is None
    assert d["expense_vs_budget"] == [{"label": "1000 Operations", "budgeted": "100000.00", "actual": "250.00",
                                       "over_budget": False}]
    bal = d["balances"]
    assert [x["label"].split(" - ")[0] for x in bal["accounts"]][0] == base["acct"]["account_name"]  # primary first
    # 1.7.2 (#56): the chart shows the bank (Current) balance - nothing has cleared yet, so the opening balances
    assert bal["accounts"][0]["values"][1] == "1000.00" and bal["accounts"][1]["values"][1] == "0.00"
    assert bal["total"][1] == "1000.00"
    assert inc2 and small


def test_chart_access(env, base):
    fy = base["fy"]["id"]
    for c in (env.bm, env.bu, env.ru, env.auditor):
        assert c.get(f"/api/dashboard/charts?fiscal_year_id={fy}").status_code == 200
    assert env.admin.get(f"/api/dashboard/charts?fiscal_year_id={fy}").status_code == 403
    assert env.bu.get("/api/dashboard/charts?fiscal_year_id=9999").status_code == 404


def test_chart_selection_per_user(env, base):
    assert env.bu.get("/api/auth/me").json()["dashboard_charts"] == ["income_pie", "monthly", "expense_vs_budget"]
    r = env.bu.put("/api/me/preferences", {"dashboard_charts": ["balances", "income_pie", "balances"]})
    assert r.status_code == 200 and r.json()["dashboard_charts"] == ["balances", "income_pie"]
    assert env.bu.get("/api/auth/me").json()["dashboard_charts"] == ["balances", "income_pie"]
    assert env.ru.get("/api/auth/me").json()["dashboard_charts"] == ["income_pie", "monthly", "expense_vs_budget"]
    assert env.bu.put("/api/me/preferences", {"dashboard_charts": []}).json()["dashboard_charts"] == []
    assert env.bu.put("/api/me/preferences", {"dashboard_charts": ["pie3d"]}).status_code == 422
