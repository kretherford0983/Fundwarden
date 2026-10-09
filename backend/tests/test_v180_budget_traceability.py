"""1.8.0 (#89): Historic Budget Traceability - a budget can continue one budget of an earlier Fiscal Year (1:1 chain,
same type and level, never Budget 0 / Other), copies into a later year link automatically, the link follows the
normal editing rules and is audited, and History shows the lineage in Fiscal Year order."""
import sqlite3

import pytest

from conftest import Api


@pytest.fixture
def years(env):
    f27 = env.fy("2027", "2026-07-01", "2027-06-30")
    f28 = env.fy("2028", "2027-07-01", "2028-06-30")
    f29 = env.fy("2029", "2028-07-01", "2029-06-30")
    ops27 = env.budget(f27["id"], "1000", "Operations", "EXPENSE", "1000.00")
    trav27 = env.budget(f27["id"], "01", "Travel", amount="200.00", parent=ops27["id"])
    don27 = env.budget(f27["id"], "4000", "Donations", "INCOME", "500.00")
    ops28 = env.budget(f28["id"], "1000", "Operations", "EXPENSE", "1100.00")
    trav28 = env.budget(f28["id"], "01", "Travel", amount="300.00", parent=ops28["id"])
    return {"f27": f27, "f28": f28, "f29": f29, "ops27": ops27, "trav27": trav27, "don27": don27,
            "ops28": ops28, "trav28": trav28}


def _opts(env, fy, btype="EXPENSE", level="budget", budget_id=None, client=None):
    url = f"/api/budgets/continue-options?fiscal_year_id={fy}&budget_type={btype}&level={level}"
    if budget_id:
        url += f"&budget_id={budget_id}"
    r = (client or env.bm).get(url)
    assert r.status_code == 200, r.text
    return r.json()


def _link(env, b, target):
    return env.bm.patch(f"/api/budgets/{b['id']}", {"continues_budget_id": target})


def test_options_are_earlier_years_same_type_and_level(env, years):
    g = _opts(env, years["f28"]["id"])
    assert [x["fiscal_year"]["display_name"] for x in g] == ["FY2027"]
    assert [o["label"] for o in g[0]["options"]] == ["FY2027 - 1000 - Operations"]   # no Income, no Budget 0 / Other
    subs = _opts(env, years["f28"]["id"], level="sub-budget")
    assert [o["label"] for o in subs[0]["options"]] == ["FY2027 - 1000-01 - Travel"]
    assert _opts(env, years["f27"]["id"]) == []                                       # nothing earlier
    inc = _opts(env, years["f28"]["id"], btype="INCOME")
    assert [o["label"] for o in inc[0]["options"]] == ["FY2027 - 4000 - Donations"]


def test_link_and_history(env, years):
    assert _link(env, years["ops28"], years["ops27"]["id"]).status_code == 200
    assert _link(env, years["trav28"], years["trav27"]["id"]).status_code == 200
    ops29 = env.budget(years["f29"]["id"], "1500", "Ops renamed", "EXPENSE", "1200.00")
    assert _link(env, ops29, years["ops28"]["id"]).status_code == 200
    h = env.bu.get(f"/api/budgets/{years['ops28']['id']}/history").json()
    assert [(x["fiscal_year"]["display_name"], x["code"], x["name"], x["amount"]) for x in h] == [
        ("FY2027", "1000", "Operations", "1000.00"), ("FY2028", "1000", "Operations", "1100.00"),
        ("FY2029", "1500", "Ops renamed", "1200.00")]
    assert [x["this"] for x in h] == [False, True, False]
    assert env.bu.get(f"/api/budgets/{years['ops27']['id']}/history").json() == [{**x, "this": x["id"] == years["ops27"]["id"]} for x in h]
    sub = env.bu.get(f"/api/budgets/{years['trav27']['id']}/history").json()
    assert [x["code"] for x in sub] == ["1000-01", "1000-01"]


def test_history_actual_includes_sub_budgets(env, base):
    f28 = env.fy("2028", "2027-07-01", "2028-06-30")
    nxt = env.budget(f28["id"], "1000", "Operations", "EXPENSE", "5.00")
    _link(env, nxt, base["exp"]["id"])
    env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "12.34"}])
    h = env.bu.get(f"/api/budgets/{nxt['id']}/history").json()
    assert h[0]["actual"] == "12.34" and h[1]["actual"] == "0.00"


def test_one_to_one(env, years):
    assert _link(env, years["ops28"], years["ops27"]["id"]).status_code == 200
    other = env.budget(years["f28"]["id"], "2000", "Programs", "EXPENSE", "10.00")
    r = _link(env, other, years["ops27"]["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_CONTINUED"
    # the taken budget is not offered to other budgets, but is to the one that continues it
    assert [o["label"] for g in _opts(env, years["f28"]["id"], budget_id=other["id"]) for o in g["options"]] == []
    assert [o["id"] for g in _opts(env, years["f28"]["id"], budget_id=years["ops28"]["id"]) for o in g["options"]] == [years["ops27"]["id"]]
    # a later year is offered the most recent budget of the lineage
    labels = [o["label"] for g in _opts(env, years["f29"]["id"]) for o in g["options"]]
    assert labels == ["FY2028 - 2000 - Programs", "FY2028 - 1000 - Operations"]          # FY2027 Operations is taken


def test_rules(env, years):
    def err(r):
        assert r.status_code == 422, r.text
        return r.json()["error"]["errors"][0]["field"]
    assert err(_link(env, years["ops28"], years["don27"]["id"])) == "continues_budget_id"   # other type
    assert err(_link(env, years["ops28"], years["trav27"]["id"])) == "continues_budget_id"  # other level
    assert err(_link(env, years["ops27"], years["ops28"]["id"])) == "continues_budget_id"   # later year
    assert err(_link(env, years["ops28"], 999999)) == "continues_budget_id"
    from sqlalchemy import select

    from fmpoc.models import Budget
    with env.app.state.session_factory() as db:
        sysb = list(db.scalars(select(Budget.id).where(Budget.fiscal_year_id == years["f27"]["id"],
                                                       Budget.system_managed.is_(True))))
    assert sysb
    for i in sysb:                                                                           # Budget 0 and Other
        assert err(_link(env, years["ops28"], i)) == "continues_budget_id"


def test_create_with_link_and_remove(env, years):
    r = env.bm.post("/api/budgets", {"fiscal_year_id": years["f29"]["id"], "code": "4000", "name": "Gifts",
                                     "budget_type": "INCOME", "amount": "1.00", "continues_budget_id": years["don27"]["id"]})
    assert r.status_code == 201 and r.json()["continues_budget_id"] == years["don27"]["id"]
    r = env.bm.post("/api/budgets", {"fiscal_year_id": years["f29"]["id"], "parent_budget_id": r.json()["id"], "code": "01",
                                     "name": "Sub", "amount": "1.00", "continues_budget_id": years["trav27"]["id"]})
    assert r.status_code == 422                                                             # Travel is Expense
    assert _link(env, years["ops28"], years["ops27"]["id"]).json()["continues_budget_id"] == years["ops27"]["id"]
    assert _link(env, years["ops28"], None).json()["continues_budget_id"] is None
    ev = env.auditor.get(f"/api/audit-events?action=BUDGET_UPDATED&object_id={years['ops28']['id']}").json()["items"]
    assert ev[0]["before"]["continues_budget_id"] == years["ops27"]["id"] and ev[0]["after"]["continues_budget_id"] is None


def test_locked_budget_needs_unlocking(env, years):
    env.approve(years["f28"]["id"])
    r = _link(env, years["ops28"], years["ops27"]["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "BUDGET_LOCKED", r.text
    assert env.bm.post(f"/api/budgets/{years['ops28']['id']}/unlock", {"reason": "link history"}).status_code == 200
    assert _link(env, years["ops28"], years["ops27"]["id"]).status_code == 200


def test_copy_links_automatically(env, years):
    r = env.bm.post("/api/fiscal-years", {"identifier": "2030", "start_date": "2029-07-01", "end_date": "2030-06-30",
                                          "copy_from_fiscal_year_id": years["f28"]["id"],
                                          "copy_budget_ids": [years["ops28"]["id"]], "confirmations": []})
    assert r.status_code == 201, r.text
    tree = env.bm.get(f"/api/budgets?fiscal_year_id={r.json()['id']}").json()["expense"]
    ops = next(x for x in tree if x["display_code"] == "1000")
    assert ops["continues_budget_id"] == years["ops28"]["id"]
    assert ops["children"][0]["continues_budget_id"] == years["trav28"]["id"]
    # copying the same year again does not steal the link
    r = env.bm.post("/api/fiscal-years", {"identifier": "2031", "start_date": "2030-07-01", "end_date": "2031-06-30",
                                          "copy_from_fiscal_year_id": years["f28"]["id"],
                                          "copy_budget_ids": [years["ops28"]["id"]], "confirmations": []})
    tree = env.bm.get(f"/api/budgets?fiscal_year_id={r.json()['id']}").json()["expense"]
    assert next(x for x in tree if x["display_code"] == "1000")["continues_budget_id"] is None


def test_deleting_frees_the_earlier_budget(env, years):
    ba = env.user("budgetadmin", "FINANCIAL", ["BUDGET_MANAGER", "BUDGET_ADMIN"])
    first = env.budget(years["f28"]["id"], "3000", "Facilities", "EXPENSE", "1.00")
    _link(env, first, years["ops27"]["id"])
    assert ba.post(f"/api/budgets/{first['id']}/delete", {"reason": "x"}).status_code == 200
    other = env.budget(years["f28"]["id"], "3100", "Operations again", "EXPENSE", "1.00")
    assert _link(env, other, years["ops27"]["id"]).status_code == 200


def test_access(env, years):
    for c in (env.bu, env.ru, env.auditor):
        assert c.get(f"/api/budgets/{years['ops28']['id']}/history").status_code == 200
        _opts(env, years["f28"]["id"], client=c)
        assert c.patch(f"/api/budgets/{years['ops28']['id']}", {"continues_budget_id": years["ops27"]["id"]}).status_code == 403
    assert env.admin.get(f"/api/budgets/{years['ops28']['id']}/history").status_code == 403
    assert Api(env.app).get(f"/api/budgets/{years['ops28']['id']}/history").status_code == 401


def test_migration_adds_the_column_without_links(tmp_path):
    from alembic import command

    from fmpoc.db import alembic_config
    url = f"sqlite:///{tmp_path / 'm.sqlite3'}"
    command.upgrade(alembic_config(url), "head")
    c = sqlite3.connect(tmp_path / "m.sqlite3")
    assert "continues_budget_id" in [r[1] for r in c.execute("pragma table_info(budget)")]
    assert "ix_budget_continues_budget_id" in [r[1] for r in c.execute("pragma index_list(budget)")]
