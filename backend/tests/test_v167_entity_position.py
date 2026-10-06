"""1.6.7: an individual Entity can carry a position in the organization; the dialogs for the audit review signature
page and the cash count sheet offer it as the signer's title (the API prints the title it is given)."""
from __future__ import annotations


def _person(env, name, **extra):
    r = env.ru.post("/api/entities", {"entity_type": "INDIVIDUAL", "primary_contact": name,
                                      "confirmations": ["DUPLICATE_ENTITY"], **extra})
    return r


def test_position_is_optional_and_saved_for_individuals(env):
    e = _person(env, "Pat Example", position="  Treasurer ").json()
    assert e["position"] == "Treasurer"
    assert _person(env, "No Position").json()["position"] is None
    listed = {x["display_name"]: x for x in env.bu.get("/api/entities").json()}   # every financial user sees it
    assert listed["Pat Example"]["position"] == "Treasurer"
    # Budget Managers and Register Users change or clear it; it is audited like any other Entity field
    r = env.bm.patch(f"/api/entities/{e['id']}", {"position": "President"})
    assert r.status_code == 200 and r.json()["position"] == "President"
    assert env.ru.patch(f"/api/entities/{e['id']}", {"position": None}).json()["position"] is None
    assert env.bu.patch(f"/api/entities/{e['id']}", {"position": "X"}).status_code == 403
    ev = env.auditor.get(f"/api/audit-events?object_type=entity&object_id={e['id']}&sort=id&direction=asc").json()["items"]
    assert [x["after"]["position"] for x in ev] == ["Treasurer", "President", None]


def test_position_limits(env):
    assert _person(env, "Too Long", position="x" * 61).status_code == 422
    assert _person(env, "Just Fits", position="x" * 60).status_code == 201
    # an organization has no position: it is dropped, also when a person is changed into an organization
    org = env.ru.post("/api/entities", {"entity_type": "ORGANIZATION", "organization_name": "Acme Supplies",
                                        "position": "Treasurer", "confirmations": ["DUPLICATE_ENTITY"]}).json()
    assert org["position"] is None
    p = _person(env, "Becomes Org", position="Secretary").json()
    r = env.ru.patch(f"/api/entities/{p['id']}", {"entity_type": "ORGANIZATION", "organization_name": "Becomes Org Ltd",
                                                   "confirmations": ["DUPLICATE_ENTITY"]})
    assert r.status_code == 200 and r.json()["position"] is None
