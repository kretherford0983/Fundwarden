"""Entities and Bank Accounts. AC-ENT-001..006, AC-BANK-001..011, AC-SEC-008."""
import json
import sqlite3

from conftest import Api


# ------------------------------------------------------------------ entities
def test_ac_ent_001_002_required_names(env):
    assert env.ru.post("/api/entities", {"entity_type": "INDIVIDUAL"}).status_code == 422
    assert env.ru.post("/api/entities", {"entity_type": "INDIVIDUAL", "primary_contact": "  "}).status_code == 422
    assert env.ru.post("/api/entities", {"entity_type": "INDIVIDUAL", "organization_name": "Org"}).status_code == 422
    assert env.ru.post("/api/entities", {"entity_type": "INDIVIDUAL", "primary_contact": "Jane Doe"}).status_code == 201
    assert env.ru.post("/api/entities", {"entity_type": "ORGANIZATION", "primary_contact": "Bob"}).status_code == 422
    assert env.ru.post("/api/entities", {"entity_type": "ORGANIZATION", "organization_name": "Acme"}).status_code == 201


def test_ac_ent_003_register_display(env, base):
    ind = env.entity("Jane Doe", "INDIVIDUAL")
    org = env.ru.post("/api/entities", {"entity_type": "ORGANIZATION", "organization_name": "Acme Supplies",
                                        "primary_contact": "Bob Smith"}).json()
    assert ind["display_name"] == "Jane Doe" and org["display_name"] == "Acme Supplies"
    t = env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "1.00"}], entity_id=org["id"])
    assert t["entity"]["display_name"] == "Acme Supplies"


def test_ac_ent_004_005_duplicates_and_numbers(env):
    a = env.ru.post("/api/entities", {"entity_type": "ORGANIZATION", "organization_name": "Acme, Inc."})
    assert a.status_code == 201
    r = env.ru.post("/api/entities", {"entity_type": "ORGANIZATION", "organization_name": "ACME"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFIRMATION_REQUIRED"
    m = r.json()["error"]["warnings"][0]
    assert m["code"] == "DUPLICATE_ENTITY" and m["details"]["matches"][0]["entity_number"] == a.json()["entity_number"]
    b = env.ru.post("/api/entities", {"entity_type": "ORGANIZATION", "organization_name": "ACME",
                                      "confirmations": ["DUPLICATE_ENTITY"]})
    assert b.status_code == 201
    na, nb = a.json()["entity_number"], b.json()["entity_number"]
    assert na != nb and na.startswith("ENT-") and len(na) == 10
    # immutable: cannot be set through the API
    assert env.ru.patch(f"/api/entities/{b.json()['id']}", {"entity_number": "ENT-999999"}).status_code == 422
    assert env.ru.get(f"/api/entities/{b.json()['id']}").json()["entity_number"] == nb


def test_ac_ent_006_inactivation_preserves_history(env, base):
    e = env.entity("Old Vendor")
    t = env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "1.00"}], entity_id=e["id"])
    assert env.ru.post(f"/api/entities/{e['id']}/inactivate", {"reason": "closed"}).status_code == 200
    assert e["id"] not in [x["id"] for x in env.ru.get("/api/entities").json()]
    assert e["id"] in [x["id"] for x in env.ru.get("/api/entities?status=inactive").json()]
    assert env.ru.get(f"/api/transactions/{t['id']}").json()["entity"]["display_name"] == "Old Vendor"
    r = env.ru.post("/api/transactions", {"bank_account_id": base["acct"]["id"], "transaction_type": "WITHDRAWAL",
                                          "transaction_date": "2026-08-01", "entity_id": e["id"],
                                          "allocations": [{"budget_id": base["exp_leaf"], "amount": "1"}]})
    assert r.status_code == 422
    # unchanged historical reference remains valid when editing the transaction
    assert env.ru.patch(f"/api/transactions/{t['id']}", {"notes": "x"}).status_code == 200
    assert env.ru.post(f"/api/entities/{e['id']}/restore", {}).status_code == 200


def test_multiple_entity_is_hidden_and_protected(env):
    names = [e["display_name"] for e in env.auditor.get("/api/entities?status=all").json()]
    assert "Multiple" not in names


# ------------------------------------------------------------------ bank accounts
def test_ac_bank_001_financial_institution_filtering(env):
    fi = env.fi("First Bank")
    ordinary = env.entity("Not A Bank")
    fis = env.bm.get("/api/entities?financial_institution=true").json()
    assert fi["id"] in [e["id"] for e in fis] and ordinary["id"] not in [e["id"] for e in fis]
    r = env.bm.post("/api/bank-accounts", {"account_name": "X", "financial_institution_entity_id": ordinary["id"],
                                           "account_type": "CHECKING", "account_number": "12345678"})
    assert r.status_code == 422


def test_ac_bank_002_003_uniqueness_and_encryption(env, settings):
    a = env.account(number="0001-2345-6789")
    r = env.bm.post("/api/bank-accounts", {"account_name": "Dup", "financial_institution_entity_id": env.fi()["id"],
                                           "account_type": "SAVINGS", "account_number": "000123456789"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "DUPLICATE_ACCOUNT_NUMBER"
    con = sqlite3.connect(settings.database_path)
    rows = con.execute("SELECT account_number_ciphertext, account_number_fingerprint, account_number_visible_suffix "
                       "FROM bank_account").fetchall()
    audit = con.execute("SELECT before_snapshot, after_snapshot FROM audit_event").fetchall()
    con.close()
    for ct, fp, suffix in rows:
        assert "000123456789" not in ct and ct.startswith("v1:") and len(fp) == 64
    # randomized ciphertext: same plaintext encrypts differently
    from fmpoc.security import crypto
    km = crypto.load_key(settings.secrets_dir)
    assert crypto.encrypt(km, "000123456789") != crypto.encrypt(km, "000123456789")
    assert "000123456789" not in json.dumps(audit) and "0001-2345-6789" not in json.dumps(audit)
    assert a


def test_ac_bank_004_masking(env):
    from fmpoc.security.crypto import mask, visible_suffix
    for num, expected in [("12345678", "******5678"), ("123456789012", "******9012"), ("12345", "********45"),
                          ("1234", "********34"), ("123456", "*******456"), ("1234567", "*******567")]:
        m = mask(visible_suffix(num))
        assert m == expected and len(m) == 10
        shown = len(m.lstrip("*"))
        assert shown <= 4 and len(num) - shown >= -(-len(num) // 2)
    acct = env.account(number="9876543210")
    for c in (env.ru, env.bu, env.auditor, env.bm):
        a = c.get(f"/api/bank-accounts/{acct['id']}").json()
        assert a["account_number_masked"] == "******3210" and "9876543210" not in json.dumps(a)
        assert a["label"].endswith("******3210")


def test_ac_sec_008_reveal_only_budget_manager_audited(env):
    acct = env.account(number="5555666677778888")
    for c in (env.ru, env.bu, env.auditor, env.admin):
        assert c.post(f"/api/bank-accounts/{acct['id']}/reveal").status_code == 403
    r = env.bm.post(f"/api/bank-accounts/{acct['id']}/reveal")
    assert r.status_code == 200 and r.json()["account_number"] == "5555666677778888"
    assert r.headers["cache-control"] == "no-store"
    ev = env.auditor.get("/api/audit-events?action=ACCOUNT_NUMBER_REVEALED").json()["items"]
    assert len(ev) == 1 and ev[0]["actor_username"] == "budgetmgr"
    assert "5555666677778888" not in json.dumps(ev)
    log = (env.settings.logs_dir / "fmpoc.log").read_text()
    assert "5555666677778888" not in log


def test_ac_bank_005_primary(env):
    a = env.account(primary=True)
    b = env.account()
    assert env.bm.post(f"/api/bank-accounts/{b['id']}/set-primary").status_code == 200
    accts = {x["id"]: x for x in env.bm.get("/api/bank-accounts").json()}
    assert accts[b["id"]]["is_primary"] and not accts[a["id"]]["is_primary"]
    assert sum(x["is_primary"] for x in accts.values()) == 1
    inv = env.account(atype="INVESTMENT")
    assert inv["register_enabled"] is False
    assert env.bm.post(f"/api/bank-accounts/{inv['id']}/set-primary").status_code == 422
    c = env.account(primary=True)  # creating a new primary clears the old
    accts = {x["id"]: x for x in env.bm.get("/api/bank-accounts").json()}
    assert accts[c["id"]]["is_primary"] and sum(x["is_primary"] for x in accts.values()) == 1
    # register defaults to primary
    assert env.ru.get("/api/register").json()["bank_account"]["id"] == c["id"]


def test_register_defaults(env):
    assert env.account(atype="CHECKING")["register_enabled"] is True
    assert env.account(atype="SAVINGS")["register_enabled"] is True
    assert env.account(atype="INVESTMENT")["register_enabled"] is False
    assert env.account(atype="INVESTMENT", register_enabled=True)["register_enabled"] is True


def test_ac_bank_006_register_balance(env, base):
    a = base["acct"]["id"]
    env.txn(a, "DEPOSIT", [{"budget_id": base["inc_leaf"], "amount": "500.00"}])
    w = env.txn(a, "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "200.00"}])
    v = env.txn(a, "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "999.00"}])
    env.ru.post(f"/api/transactions/{v['id']}/void", {"reason": "error", "confirm_irreversible": True})
    # 1.7.2 (#56): Current Balance counts cleared transactions only; Available (Register) counts all active ones
    assert env.bu.get(f"/api/bank-accounts/{a}").json()["current_balance"] == "1000.00"
    reg = env.bu.get(f"/api/register?bank_account_id={a}").json()
    assert [t["running_balance"] for t in reg["transactions"]] == ["1500.00", "1300.00", "1300.00"]
    assert reg["available_balance"] == "1300.00" and reg["current_balance"] == "1000.00"
    for t in reg["transactions"]:
        if t["status"] == "ACTIVE":
            env.ru.patch(f"/api/transactions/{t['id']}", {"clear_date": "2026-08-02"})
    assert env.bu.get(f"/api/bank-accounts/{a}").json()["current_balance"] == "1300.00"   # VOID has no effect
    assert w


def test_ac_bank_007_transaction_cannot_move_account(env, base):
    other = env.account()
    t = env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "10.00"}])
    r = env.ru.patch(f"/api/transactions/{t['id']}", {"bank_account_id": other["id"]})
    assert r.status_code == 422
    assert env.ru.get(f"/api/transactions/{t['id']}").json()["bank_account_id"] == base["acct"]["id"]
    # correction = void + recreate in the correct account
    env.ru.post(f"/api/transactions/{t['id']}/void", {"reason": "Wrong account", "confirm_irreversible": True})
    n = env.txn(other["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "10.00"}])
    assert n["bank_account_id"] == other["id"]
    assert env.bu.get(f"/api/bank-accounts/{base['acct']['id']}").json()["current_balance"] == "1000.00"


def test_ac_bank_008_009_010_closure_rules(env, base):
    a = base["acct"]["id"]
    t = env.txn(a, "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "400.00"}])
    r = env.bm.post(f"/api/bank-accounts/{a}/close", {"reason": "moving banks"})
    codes = {b["code"] for b in r.json()["error"]["blockers"]}
    assert r.status_code == 409 and codes == {"UNCLEARED_TRANSACTIONS", "NON_ZERO_BALANCE"}
    env.ru.patch(f"/api/transactions/{t['id']}", {"clear_date": "2026-08-03"})
    r = env.bm.post(f"/api/bank-accounts/{a}/close", {"reason": "moving banks"})
    assert {b["code"] for b in r.json()["error"]["blockers"]} == {"NON_ZERO_BALANCE"}
    # manual override of a register balance is impossible
    assert env.bm.post(f"/api/bank-accounts/{a}/balance", {"current_balance": "0.00"}).status_code == 409
    assert env.bm.patch(f"/api/bank-accounts/{a}", {"opening_balance": "400.00"}).status_code == 409
    assert env.bm.patch(f"/api/bank-accounts/{a}", {"manual_current_balance_cents": 0}).status_code == 422
    # final register transaction brings the account to exactly zero
    env.txn(a, "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "600.00"}], clear_date="2026-08-04")
    assert env.bm.get(f"/api/bank-accounts/{a}").json()["current_balance"] == "0.00"
    r = env.bm.post(f"/api/bank-accounts/{a}/close", {"reason": "moving banks"})
    assert r.status_code == 200 and r.json()["status"] == "CLOSED" and r.json()["is_primary"] is False
    # closed account: no new transactions, still visible
    r = env.ru.post("/api/transactions", {"bank_account_id": a, "transaction_type": "DEPOSIT",
                                          "allocations": [{"budget_id": base["inc_leaf"], "amount": "1"}]})
    assert r.status_code == 409
    assert any(x["id"] == a for x in env.bu.get("/api/bank-accounts").json())


def test_ac_bank_011_non_register_zeroing(env):
    inv = env.bm.post("/api/bank-accounts", {"account_name": "Brokerage", "financial_institution_entity_id": env.fi()["id"],
                                             "account_type": "INVESTMENT", "account_number": "INV000111",
                                             "current_balance": "2500.00"}).json()
    assert inv["current_balance"] == "2500.00"
    r = env.bm.post(f"/api/bank-accounts/{inv['id']}/close", {"reason": "liquidated"})
    assert r.status_code == 409
    assert env.ru.post(f"/api/bank-accounts/{inv['id']}/balance", {"current_balance": "0.00"}).status_code == 403
    r = env.bm.post(f"/api/bank-accounts/{inv['id']}/balance", {"current_balance": "0.00", "reason": "Liquidated"})
    assert r.status_code == 200
    ev = env.auditor.get(f"/api/audit-events?action=BANK_ACCOUNT_BALANCE_UPDATED&object_id={inv['id']}").json()["items"]
    assert ev[0]["before"]["manual_current_balance"] == "2500.00" and ev[0]["after"]["manual_current_balance"] == "0.00"
    assert env.bm.post(f"/api/bank-accounts/{inv['id']}/close", {"reason": "liquidated"}).status_code == 200


def test_bank_accounts_cannot_be_deleted(env):
    a = env.account()
    assert env.bm.delete(f"/api/bank-accounts/{a['id']}").status_code in (404, 405)
    assert env.bm.get(f"/api/bank-accounts/{a['id']}").status_code == 200


def test_portable_key_required(env, settings, tmp_path):
    """AC-DEP-006 (negative): a data set without its key refuses to start rather than silently losing data."""
    import shutil

    import pytest

    from fmpoc.app import create_app
    from fmpoc.config import load_settings
    env.account(number="11112222333")
    dst = tmp_path / "copy"
    shutil.copytree(settings.data_dir, dst)
    (dst / "secrets" / "portable-encryption-key.json").unlink()
    with pytest.raises(RuntimeError):
        create_app(load_settings({"data_dir": str(dst)}))


def test_ac_dep_006_portable_data_set(env, settings, tmp_path):
    """Moving database + attachments + portable key to another installation preserves decryption."""
    import shutil

    from fmpoc.app import create_app
    from fmpoc.config import load_settings
    acct = env.account(number="44445555666")
    env.app.state.engine.dispose()
    dst = tmp_path / "other-os-install"
    shutil.copytree(settings.data_dir, dst)
    app2 = create_app(load_settings({"data_dir": str(dst)}))
    c = Api(app2)
    assert c.login("budgetmgr").status_code == 200
    assert c.post(f"/api/bank-accounts/{acct['id']}/reveal").json()["account_number"] == "44445555666"
