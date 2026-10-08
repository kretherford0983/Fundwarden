"""1.7.3 (#104): Register Budget filter - transactions with an allocation to the budget (a parent includes its
sub-budgets), the budget's share of each one; filter choices follow the Fiscal Year filter."""
import pytest

from conftest import Api


@pytest.fixture
def tree(env, base):
    fy = base["fy"]["id"]
    prog = env.budget(fy, "2000", "Programs", "EXPENSE", "5000.00")
    env.budget(fy, "01", "Supplies", amount="3000.00", parent=prog["id"])
    env.budget(fy, "02", "Travel", amount="1000.00", parent=prog["id"])
    opts = {o["label"]: o["id"] for o in env.selectable(fy, "WITHDRAWAL")}
    a = base["acct"]["id"]
    split = env.txn(a, "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "60.00"},
                                      {"budget_id": opts["2000-01 Supplies"], "amount": "40.00"}])
    ops = env.txn(a, "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "25.00"}], date="2026-08-02")
    trav = env.txn(a, "WITHDRAWAL", [{"budget_id": opts["2000-02 Travel"], "amount": "15.00"}], date="2026-08-03")
    dep = env.txn(a, "DEPOSIT", [{"budget_id": base["inc_leaf"], "amount": "500.00"}], date="2026-08-04")
    fo = {o["label"]: o for o in env.bu.get(f"/api/budgets/filter-options?fiscal_year_id={fy}").json()}
    return {"fy": fy, "a": a, "split": split, "ops": ops, "trav": trav, "dep": dep, "fo": fo, "prog": prog}


def _reg(client, t, **q):
    url = f"/api/register?bank_account_id={t['a']}" + "".join(f"&{k}={v}" for k, v in q.items())
    r = client.get(url)
    assert r.status_code == 200, r.text
    return r.json()


def test_filter_options_labels_and_order(env, tree):
    labels = list(tree["fo"])
    assert labels == ["FY2027 - 4000 - Donations", "FY2027 - 1000 - Operations", "FY2027 - 2000 - Programs",
                      "FY2027 - 2000-01 - Supplies", "FY2027 - 2000-02 - Travel", "FY2027 - 2000-00 - Other"]  # Other: 1000.00 left
    assert not any(" 0 " in x or x.endswith("Budget 0") for x in labels)          # Budget 0 is left out


def test_budget_filter_lists_only_that_budgets_transactions_with_share(env, tree):
    r = _reg(env.ru, tree, budget_id=tree["fo"]["FY2027 - 1000 - Operations"]["id"])
    got = {x["id"]: x["budget_share"] for x in r["transactions"]}
    assert got == {tree["split"]["id"]: "60.00", tree["ops"]["id"]: "25.00"}
    assert r["budget"]["label"] == "1000 Operations"
    split = next(x for x in r["transactions"] if x["id"] == tree["split"]["id"])
    assert split["withdrawal"] == "100.00"                                       # the full amount is still there


def test_parent_includes_sub_budgets(env, tree):
    r = _reg(env.ru, tree, budget_id=tree["prog"]["id"])
    assert {x["id"]: x["budget_share"] for x in r["transactions"]} == {tree["split"]["id"]: "40.00", tree["trav"]["id"]: "15.00"}
    r = _reg(env.ru, tree, budget_id=tree["fo"]["FY2027 - 2000-02 - Travel"]["id"])
    assert [x["id"] for x in r["transactions"]] == [tree["trav"]["id"]]


def test_balances_and_running_balance_unchanged(env, tree):
    plain = _reg(env.ru, tree)
    f = _reg(env.ru, tree, budget_id=tree["prog"]["id"])
    for k in ("current_balance", "available_balance", "starting_balance", "ending_balance"):
        assert f[k] == plain[k]
    rb = {x["id"]: x["running_balance"] for x in plain["transactions"]}
    assert all(x["running_balance"] == rb[x["id"]] for x in f["transactions"])
    assert "budget_share" not in plain["transactions"][0]


def test_combines_with_other_filters(env, tree):
    bid = tree["fo"]["FY2027 - 1000 - Operations"]["id"]
    assert [x["id"] for x in _reg(env.ru, tree, budget_id=bid, search="nothing-matches")["transactions"]] == []
    assert len(_reg(env.ru, tree, budget_id=bid, date_from="2026-08-02")["transactions"]) == 1
    assert _reg(env.ru, tree, budget_id=tree["fo"]["FY2027 - 4000 - Donations"]["id"], transaction_type="DEPOSIT")["transactions"][0]["id"] == tree["dep"]["id"]


def test_all_years_options_and_other_fiscal_year(env, tree):
    fy28 = env.fy("2028", "2027-07-01", "2028-06-30")
    env.budget(fy28["id"], "1000", "Operations", "EXPENSE", "100.00")
    all_ = [o["label"] for o in env.bu.get("/api/budgets/filter-options").json()]
    assert all_[0] == "FY2028 - 1000 - Operations" and "FY2027 - 1000 - Operations" in all_   # newest year first
    one = [o["label"] for o in env.bu.get(f"/api/budgets/filter-options?fiscal_year_id={fy28['id']}").json()]
    assert one == ["FY2028 - 1000 - Operations"]


def test_void_listed_like_today(env, tree):
    env.ru.post(f"/api/transactions/{tree['ops']['id']}/void", {"reason": "dup", "confirm_irreversible": True})
    r = _reg(env.ru, tree, budget_id=tree["fo"]["FY2027 - 1000 - Operations"]["id"])
    assert {x["id"]: x["status"] for x in r["transactions"]}[tree["ops"]["id"]] == "VOID"
    r = _reg(env.ru, tree, budget_id=tree["fo"]["FY2027 - 1000 - Operations"]["id"], status="active")
    assert tree["ops"]["id"] not in [x["id"] for x in r["transactions"]]


def test_access(env, tree):
    bid = tree["prog"]["id"]
    for c in (env.bm, env.bu, env.ru, env.auditor):
        assert c.get(f"/api/register?bank_account_id={tree['a']}&budget_id={bid}").status_code == 200
        assert c.get("/api/budgets/filter-options").status_code == 200
    assert env.admin.get(f"/api/register?bank_account_id={tree['a']}&budget_id={bid}").status_code == 403
    assert env.admin.get("/api/budgets/filter-options").status_code == 403
    assert env.ru.get(f"/api/register?bank_account_id={tree['a']}&budget_id=999999").status_code == 404
    assert Api(env.app).get("/api/budgets/filter-options").status_code == 401
