"""1.7.1 (#74): Budget Managers set the order in which bank accounts are listed - kept separately for the two groups
(Checking & Savings; Investments and Other), used by the Bank Accounts page, the Dashboard and the Register account
selector. The Primary account is not pinned; the Register still opens on the Primary account."""
import sqlite3

import pytest


def _names(client, group=None, url="/api/bank-accounts"):
    return [a["account_name"] for a in client.get(url).json() if group is None or a["group"] == group]


def _dash(client):
    d = client.get("/api/dashboard").json()
    return [a["label"].split(" - ")[0] for a in d["bank_accounts"]], d


def _move(client, acct, direction):
    return client.post(f"/api/bank-accounts/{acct['id']}/move", {"direction": direction})


@pytest.fixture
def accts(env):
    """Created out of name order: Primary is created last and is not first by name."""
    a = {}
    for name, atype in (("Delta Checking", "CHECKING"), ("Alpha Savings", "SAVINGS"), ("Brokerage", "INVESTMENT"),
                        ("CD Ladder", "CERTIFICATE_OF_DEPOSIT")):
        a[name] = env.account(atype=atype, account_name=name)
    a["Main Checking"] = env.account(primary=True, account_name="Main Checking")
    return a


def test_new_accounts_go_to_the_end_of_their_group(env, accts):
    assert _names(env.bm, "CHECKING_SAVINGS") == ["Delta Checking", "Alpha Savings", "Main Checking"]
    assert _names(env.bm, "INVESTMENTS_OTHER") == ["Brokerage", "CD Ladder"]
    # the whole list: Checking & Savings first, then Investments and Other
    assert _names(env.bm) == ["Delta Checking", "Alpha Savings", "Main Checking", "Brokerage", "CD Ladder"]
    assert _dash(env.bm)[0] == ["Delta Checking", "Alpha Savings", "Main Checking", "Brokerage", "CD Ladder"]


def test_moving_saves_the_order_for_the_page_dashboard_and_register(env, accts):
    r = _move(env.bm, accts["Main Checking"], "up")
    assert r.status_code == 200, r.text
    assert r.json()["position"] == 2 and r.json()["group_size"] == 3 and r.json()["group"] == "CHECKING_SAVINGS"
    assert _move(env.bm, accts["Main Checking"], "up").json()["position"] == 1
    want = ["Main Checking", "Delta Checking", "Alpha Savings", "Brokerage", "CD Ladder"]
    assert _names(env.bm) == want
    assert _names(env.bu) == want                     # every user sees the order the Budget Manager set
    assert _dash(env.bm)[0] == want
    # Register account selector: same list (register-enabled accounts), in the same order
    reg = [a["account_name"] for a in env.ru.get("/api/bank-accounts").json() if a["register_enabled"]]
    assert reg == ["Main Checking", "Delta Checking", "Alpha Savings"]


def test_the_primary_account_is_not_pinned(env, accts):
    # Primary is third in its group: it stays there, and the Register still opens on it
    assert _names(env.bm, "CHECKING_SAVINGS") == ["Delta Checking", "Alpha Savings", "Main Checking"]
    assert env.ru.get("/api/register").json()["bank_account"]["id"] == accts["Main Checking"]["id"]
    # moved up and then back below the other accounts - it stays where it was placed
    _move(env.bm, accts["Main Checking"], "up")
    _move(env.bm, accts["Main Checking"], "up")
    assert _move(env.bm, accts["Main Checking"], "down").json()["position"] == 2
    assert _names(env.bm, "CHECKING_SAVINGS") == ["Delta Checking", "Main Checking", "Alpha Savings"]
    assert _dash(env.bm)[0][:3] == ["Delta Checking", "Main Checking", "Alpha Savings"]
    assert env.ru.get("/api/register").json()["bank_account"]["id"] == accts["Main Checking"]["id"]


def test_moving_the_primary_designation_keeps_the_order(env, accts):
    before = _names(env.bm)
    assert env.bm.post(f"/api/bank-accounts/{accts['Alpha Savings']['id']}/set-primary").status_code == 200
    assert _names(env.bm) == before
    assert env.ru.get("/api/register").json()["bank_account"]["id"] == accts["Alpha Savings"]["id"]


def test_one_group_is_reordered_without_touching_the_other(env, accts):
    other = _names(env.bm, "INVESTMENTS_OTHER")
    assert _move(env.bm, accts["Alpha Savings"], "up").status_code == 200
    assert _names(env.bm, "INVESTMENTS_OTHER") == other
    assert _names(env.bm, "CHECKING_SAVINGS") == ["Alpha Savings", "Delta Checking", "Main Checking"]
    assert _move(env.bm, accts["CD Ladder"], "up").status_code == 200
    assert _names(env.bm, "INVESTMENTS_OTHER") == ["CD Ladder", "Brokerage"]
    assert _names(env.bm, "CHECKING_SAVINGS") == ["Alpha Savings", "Delta Checking", "Main Checking"]


def test_cannot_move_past_either_end(env, accts):
    r = _move(env.bm, accts["Delta Checking"], "up")
    assert r.status_code == 409 and r.json()["error"]["code"] == "CANNOT_MOVE"
    assert "already first in Checking & Savings" in r.json()["error"]["message"]
    r = _move(env.bm, accts["CD Ladder"], "down")
    assert r.status_code == 409 and "already last in Investments and Other" in r.json()["error"]["message"]
    assert _move(env.bm, accts["Delta Checking"], "sideways").status_code == 422


def test_only_a_budget_manager_can_change_the_order(env, accts):
    before = _names(env.bm)
    for client in (env.bu, env.ru, env.auditor, env.admin):
        assert _move(client, accts["Main Checking"], "up").status_code == 403
    assert _names(env.bm) == before


def test_order_changes_are_audited(env, accts):
    assert _move(env.bm, accts["Main Checking"], "up").status_code == 200
    ev = env.auditor.get(f"/api/audit-events?action=BANK_ACCOUNT_ORDER_CHANGED&object_id={accts['Main Checking']['id']}").json()["items"]
    assert len(ev) == 1
    ids = [accts[n]["id"] for n in ("Delta Checking", "Alpha Savings", "Main Checking")]
    assert ev[0]["before"] == {"group": "CHECKING_SAVINGS", "position": 3, "order": ids}
    assert ev[0]["after"] == {"group": "CHECKING_SAVINGS", "position": 2, "order": [ids[0], ids[2], ids[1]]}


def test_totals_are_unchanged_by_the_order(env, accts):
    env.bm.post(f"/api/bank-accounts/{accts['Brokerage']['id']}/balance", {"current_balance": "250.00"})
    _, d1 = _dash(env.bm)
    _move(env.bm, accts["Main Checking"], "up")
    _move(env.bm, accts["CD Ladder"], "up")
    _, d2 = _dash(env.bm)
    assert d1["bank_accounts_total"] == d2["bank_accounts_total"]
    assert [(g["key"], g["total"], sorted(g["account_ids"])) for g in d1["bank_account_groups"]] == \
           [(g["key"], g["total"], sorted(g["account_ids"])) for g in d2["bank_account_groups"]]
    # each group's account_ids follow the set order
    cs = next(g for g in d2["bank_account_groups"] if g["key"] == "CHECKING_SAVINGS")["account_ids"]
    assert cs == [accts[n]["id"] for n in ("Delta Checking", "Main Checking", "Alpha Savings")]


def test_no_primary_account_lists_in_the_set_order(env):
    a = env.account(account_name="Zeta")
    b = env.account(account_name="Beta")
    _move(env.bm, b, "up")
    assert _names(env.bm) == ["Beta", "Zeta"]
    assert _dash(env.bm)[0] == ["Beta", "Zeta"]
    assert env.ru.get("/api/register").status_code == 200
    fy = env.fy()["id"]
    r = env.bm.get(f"/api/dashboard/charts?fiscal_year_id={fy}")
    assert r.status_code == 200, r.text
    assert [x["label"].split(" - ")[0] for x in r.json()["balances"]["accounts"]] == ["Beta", "Zeta"]
    assert a["is_primary"] is False and b["is_primary"] is False


def test_changing_type_to_the_other_group_puts_it_at_the_end(env, accts):
    r = env.bm.patch(f"/api/bank-accounts/{accts['Delta Checking']['id']}", {"account_type": "MONEY_MARKET"})
    assert r.status_code == 200, r.text
    assert _names(env.bm, "INVESTMENTS_OTHER") == ["Brokerage", "CD Ladder", "Delta Checking"]
    assert _names(env.bm, "CHECKING_SAVINGS") == ["Alpha Savings", "Main Checking"]
    # a type change inside the same group keeps the position
    env.bm.patch(f"/api/bank-accounts/{accts['Brokerage']['id']}", {"account_type": "OTHER"})
    assert _names(env.bm, "INVESTMENTS_OTHER") == ["Brokerage", "CD Ladder", "Delta Checking"]


def test_closed_accounts_keep_their_place_and_can_be_moved(env, accts):
    a = accts["Alpha Savings"]
    assert env.bm.post(f"/api/bank-accounts/{a['id']}/close", {"reason": "done"}).status_code == 200
    assert _names(env.bm, "CHECKING_SAVINGS") == ["Delta Checking", "Alpha Savings", "Main Checking"]
    assert _move(env.bm, a, "down").status_code == 200
    assert _names(env.bm, "CHECKING_SAVINGS") == ["Delta Checking", "Main Checking", "Alpha Savings"]
    assert _dash(env.bm)[0] == ["Delta Checking", "Main Checking", "Brokerage", "CD Ladder"]  # active only


def test_migration_starts_each_group_with_primary_then_by_name(tmp_path):
    from alembic import command

    from fmpoc.db import alembic_config
    url = f"sqlite:///{tmp_path / 'm.sqlite3'}"
    command.upgrade(alembic_config(url), "0017_user_display_name_required")
    c = sqlite3.connect(tmp_path / "m.sqlite3")
    c.execute("pragma foreign_keys=off")
    cols = [r[1] for r in c.execute("pragma table_info(bank_account)")]
    rows = {1: (1, "Zulu Checking", "CHECKING", 1), 2: (1, "Alpha Savings", "SAVINGS", 0),
            3: (1, "Mike Checking", "CHECKING", 0), 4: (1, "Yankee CD", "CERTIFICATE_OF_DEPOSIT", 0),
            5: (1, "Bravo Brokerage", "INVESTMENT", 0), 6: (2, "Other Workspace", "CHECKING", 0),
            7: (1, "Alpha Savings", "SAVINGS", 0)}
    for i, (ws, name, atype, primary) in rows.items():
        row = {k: None for k in cols}
        row.update(id=i, workspace_id=ws, financial_institution_entity_id=1, account_name=name, account_type=atype,
                   account_number_ciphertext="x", account_number_fingerprint=f"fp{i}", account_number_visible_suffix="1234",
                   register_enabled=1, is_primary=primary, status="ACTIVE",
                   created_at="2026-01-01 00:00:00", updated_at="2026-01-01 00:00:00")
        c.execute(f"insert into bank_account ({','.join(row)}) values ({','.join('?' * len(row))})", list(row.values()))
    c.commit(); c.close()
    command.upgrade(alembic_config(url), "head")
    got = dict(sqlite3.connect(tmp_path / "m.sqlite3").execute("select id, sort_order from bank_account").fetchall())
    # Checking & Savings: Primary (Zulu) first, then Alpha (2, then 7 by id), Mike; Investments: Bravo, Yankee
    assert got == {1: 1, 2: 2, 7: 3, 3: 4, 5: 1, 4: 2, 6: 1}
