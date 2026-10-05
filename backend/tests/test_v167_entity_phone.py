"""1.6.7: Entity phone numbers - typed any way, stored plain, shown as (nnn) nnn-nnnn."""
import pytest

from fmpoc import phone


@pytest.mark.parametrize("typed", ["5551234567", "555-123-4567", "555.123.4567", "(555) 123-4567", "555 123 4567",
                                   " 1-555-123-4567 ", "+1 (555) 123-4567", "15551234567"])
def test_every_common_spelling_is_stored_and_shown_the_same(typed):
    assert phone.normalize(typed) == "5551234567"
    assert phone.display(phone.normalize(typed)) == "(555) 123-4567"


def test_extensions_other_countries_and_nonsense():
    for typed in ("555-123-4567 x204", "5551234567 ext 204", "(555) 123-4567 Ext. 204", "555.123.4567#204"):
        assert phone.normalize(typed) == "5551234567x204"
    assert phone.display("5551234567x204") == "(555) 123-4567 x204"
    assert phone.normalize("+44 20 7123 4567") == "+442071234567" and phone.display("+442071234567") == "+442071234567"
    assert phone.normalize("") is None and phone.normalize("   ") is None and phone.normalize(None) is None
    assert phone.display(None) is None and phone.display("call the office") == "call the office"  # older free text
    for bad in ("123-4567", "555-123-45678", "55512345", "+12", "555-123-4567 x", "5+551234567", "+44 20 7123 4567 x2"):
        with pytest.raises(ValueError):
            phone.normalize(bad)


def test_api_stores_plain_and_returns_the_display_form(env, base):
    r = env.ru.post("/api/entities", {"entity_type": "ORGANIZATION", "organization_name": "Phone Co", "phone": "555.123.4567"})
    assert r.status_code == 201 and r.json()["phone"] == "5551234567" and r.json()["phone_display"] == "(555) 123-4567"
    eid = r.json()["id"]
    lst = {e["id"]: e for e in env.ru.get("/api/entities").json()}
    assert lst[eid]["phone_display"] == "(555) 123-4567"
    # the edit form sends back the displayed form: nothing changes, nothing is audited as a phone change
    x = env.ru.patch(f"/api/entities/{eid}", {"phone": "(555) 123-4567"}).json()
    assert x["phone"] == "5551234567"
    x = env.ru.patch(f"/api/entities/{eid}", {"phone": "1 555 987 6543 ext 12"}).json()
    assert x["phone"] == "5559876543x12" and x["phone_display"] == "(555) 987-6543 x12"
    assert env.ru.patch(f"/api/entities/{eid}", {"phone": None}).json()["phone_display"] is None
    r = env.ru.patch(f"/api/entities/{eid}", {"phone": "123-4567"})
    assert r.status_code == 422 and r.json()["error"]["errors"][0]["field"] == "phone"
    assert env.ru.post("/api/entities", {"entity_type": "ORGANIZATION", "organization_name": "Y", "phone": "<b>1</b>"}).status_code == 422
    ev = env.auditor.get("/api/audit-events?object_type=entity&sort=id&direction=asc").json()["items"]
    assert [e["after"]["phone"] for e in ev if e["object_id"] == str(eid)][:1] == ["5551234567"]


def test_an_older_number_in_another_form_can_still_be_edited(env, base, app):
    from sqlalchemy import text
    eid = env.entity("Legacy Ltd")["id"]
    with app.state.session_factory() as db:
        db.execute(text("update entity set phone = '123-4567' where id = :i"), {"i": eid})
        db.commit()
    e = {x["id"]: x for x in env.ru.get("/api/entities").json()}[eid]
    assert e["phone"] == "123-4567" == e["phone_display"]
    x = env.ru.patch(f"/api/entities/{eid}", {"phone": "123-4567", "city": "Springfield"})   # unchanged: accepted
    assert x.status_code == 200 and x.json()["phone"] == "123-4567" and x.json()["city"] == "Springfield"
    assert env.ru.patch(f"/api/entities/{eid}", {"phone": "555-123-4567"}).json()["phone_display"] == "(555) 123-4567"


def test_migration_tidies_existing_numbers_and_leaves_the_rest(tmp_path):
    import sqlite3

    from alembic import command

    from fmpoc.db import alembic_config
    url = f"sqlite:///{tmp_path / 'm.sqlite3'}"
    command.upgrade(alembic_config(url), "0015_reminder_repeat")
    c = sqlite3.connect(tmp_path / "m.sqlite3")
    cols = [r[1] for r in c.execute("pragma table_info(entity)")]
    values = {1: "555-123-4567", 2: "(555) 123-4567 ext 9", 3: "123-4567", 4: "+44 20 7123 4567", 5: None,
              6: "1.555.123.4567", 7: "5551234567", 8: ""}
    c.execute("pragma foreign_keys=off")
    for i, p in values.items():
        row = {k: None for k in cols}
        row.update(id=i, workspace_id=1, entity_number=f"ENT-{i:06d}", entity_type="ORGANIZATION", organization_name=f"O{i}",
                   display_name=f"O{i}", name_key=f"o{i}", phone=p, active=1, is_system=0, is_financial_institution=0,
                   created_at="2026-01-01 00:00:00", updated_at="2026-01-01 00:00:00")
        row = {k: v for k, v in row.items() if k in cols}
        c.execute(f"insert into entity ({','.join(row)}) values ({','.join('?' * len(row))})", list(row.values()))
    c.commit(); c.close()
    command.upgrade(alembic_config(url), "head")
    got = dict(sqlite3.connect(tmp_path / "m.sqlite3").execute("select id, phone from entity").fetchall())
    assert got == {1: "5551234567", 2: "5551234567x9", 3: "123-4567", 4: "+44 20 7123 4567", 5: None,
                   6: "5551234567", 7: "5551234567", 8: ""}
