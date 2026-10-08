def test_smoke(base, env):
    t = env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "100.00"}])
    assert t["total"] == "100.00"
    r = env.ru.get(f"/api/register?bank_account_id={base['acct']['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["available_balance"] == "900.00" and r.json()["current_balance"] == "1000.00"  # not cleared (1.7.2)
    d = env.bm.get(f"/api/fiscal-years/{base['fy']['id']}")
    assert d.status_code == 200, d.text
