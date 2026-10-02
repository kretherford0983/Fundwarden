"""v1.6.4 CR-037 (cancelled fundraisers) and CR-038 (printable cash count sheet)."""
import io

from pypdf import PdfReader


def _text(pdf: bytes) -> tuple[int, str]:
    r = PdfReader(io.BytesIO(pdf))
    return len(r.pages), " ".join(" ".join((p.extract_text() or "") for p in r.pages).split())


def _fundraiser(env, base):
    assert env.admin.put("/api/system/modules", {"fundraisers": True}).status_code == 200
    env.txn(base["acct"]["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "150.00", "description": "Deposit for hall"}], date="2026-09-01")
    return env.bm.post("/api/fundraisers", {"name": "Autumn Fair", "start_date": "2026-09-20",
                                            "budget_ids": [base["inc"]["id"], base["exp"]["id"]]}).json()["id"]


def test_cancel_and_reinstate(env, base):
    fid = _fundraiser(env, base)
    for c in (env.ru, env.bu, env.auditor):
        assert c.post(f"/api/fundraisers/{fid}/cancel", {"reason": "x"}).status_code == 403
    assert env.bm.post(f"/api/fundraisers/{fid}/cancel", {"reason": "  "}).status_code == 422
    f = env.bm.post(f"/api/fundraisers/{fid}/cancel", {"reason": "Venue flooded"}).json()
    assert f["status"] == "CANCELLED" and f["cancelled"] and f["cancel_reason"] == "Venue flooded"
    assert f["totals"]["expense"] == "150.00" and len(f["lines"]) == 1  # transactions still listed and counted
    assert env.bm.post(f"/api/fundraisers/{fid}/cancel", {"reason": "again"}).status_code == 409
    row = env.bu.get(f"/api/fundraisers?fiscal_year_id={base['fy']['id']}").json()[0]
    assert row["status"] == "CANCELLED" and row["cancel_reason"] == "Venue flooded"
    # still manageable; shown in the fundraiser report and in the Audit report
    assert env.ru.post(f"/api/fundraisers/{fid}/buckets", {"name": "Hall"}).status_code == 201
    text = _text(env.auditor.get(f"/api/fundraisers/{fid}/report").content)[1]
    assert "CANCELLED" in text and "did not take place as planned" in text and "Venue flooded" in text
    text = _text(env.auditor.get(f"/api/reports/audit?fiscal_year_id={base['fy']['id']}&include_fundraisers=true").content)[1]
    assert "did not take place as planned" in text and "Venue flooded" in text
    # archived wins in the status, the cancellation stays recorded
    assert env.bm.post(f"/api/fundraisers/{fid}/archive").json()["status"] == "ARCHIVED"
    env.bm.post(f"/api/fundraisers/{fid}/restore")
    f = env.bm.post(f"/api/fundraisers/{fid}/reinstate").json()
    assert f["status"] != "CANCELLED" and f["cancel_reason"] is None
    assert env.bm.post(f"/api/fundraisers/{fid}/reinstate").status_code == 409
    acts = [e["action"] for e in env.auditor.get("/api/audit-events?object_type=fundraiser&sort=id&direction=asc").json()["items"]]
    assert "FUNDRAISER_CANCELLED" in acts and "FUNDRAISER_REINSTATED" in acts


def test_cash_count_sheet(env, base):
    fid = _fundraiser(env, base)
    assert env.admin.get(f"/api/fundraisers/{fid}/count-sheet").status_code == 403
    r = env.bu.get(f"/api/fundraisers/{fid}/count-sheet")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert "fundraiser-Autumn-Fair-cash-count-sheet.pdf" in r.headers["content-disposition"]
    pages, text = _text(r.content)
    # 1.6.7: 13 check lines beside the 13 bill/coin lines; page 2 (the back) has 30 more and their own total
    assert pages == 2 and "continue on page 2" in text and "additional checks" in text
    assert "Total of the checks on this page" in text and " 43 " in text and " 44 " not in text
    pages, text = _text(env.bu.get(f"/api/fundraisers/{fid}/count-sheet?extra_checks=false").content)
    assert pages == 1 and "page 2" not in text and " 13 " in text and " 14 " not in text
    for want in ("Cash count sheet", "Acme Org", "Autumn Fair", "2026-09-20", "Date of count", "Time", "$100", "$2", "25¢",
                 "Check no.", "Cash total", "Check total", "Total counted", "Notes", "agree with the amounts"):
        assert want in text, want
    # 1.6.7: one row per person - Signature | Printed | Date; three blank rows by default, two notes lines always
    assert "Location" not in text and "Name and title" not in text
    assert text.count("Signature") == 3 and text.count("Printed") == 3 and text.count("Date") == 3 + 1  # + "Date of count"
    assert text.count("_" * 80) >= 2
    for n in (1, 2, 3):  # as many blank rows as asked for, at most three when no signer is chosen
        pages, text = _text(env.bu.get(f"/api/fundraisers/{fid}/count-sheet?extra_checks=false&blank_lines={n}").content)
        assert pages == 1 and text.count("Signature") == n and text.count("Printed") == n, n
    assert env.bu.get(f"/api/fundraisers/{fid}/count-sheet?blank_lines=4").status_code == 422
    # chosen signers (up to five individuals, optional titles): the name under the signature line, no labels
    people = [env.entity(f"Person {i}", etype="INDIVIDUAL")["id"] for i in range(5)]
    q = "extra_checks=false&" + "&".join(f"signer_id={p}" for p in people) + "&signer_title=Treasurer"
    pages, text = _text(env.ru.get(f"/api/fundraisers/{fid}/count-sheet?{q}").content)
    assert pages == 1 and "Person 0, Treasurer" in text and "Person 4" in text
    assert "Signature" not in text and "Printed" not in text and text.count("Date") == 5 + 1 and text.count("_" * 80) >= 2
    # chosen signers followed by blank rows: at most two blank rows then, at most five rows in total
    q2 = f"extra_checks=false&signer_id={people[0]}&signer_title=Treasurer&signer_id={people[1]}&signer_id={people[2]}&blank_lines=2"
    pages, text = _text(env.ru.get(f"/api/fundraisers/{fid}/count-sheet?{q2}").content)
    assert pages == 1 and "Person 0, Treasurer" in text and "Person 2" in text
    assert text.count("Signature") == 2 and text.count("Printed") == 2 and text.count("Date") == 5 + 1
    assert env.ru.get(f"/api/fundraisers/{fid}/count-sheet?signer_id={people[0]}&blank_lines=3").status_code == 422
    assert env.ru.get(f"/api/fundraisers/{fid}/count-sheet?{q}&blank_lines=1").status_code == 422
    # worst case for the page: the longest fundraiser name (120 characters, wraps in the header and the statement)
    long_id = env.bm.post("/api/fundraisers", {"name": ("Annual Spring Pancake Breakfast and Silent Auction " * 3)[:120],
                                               "start_date": "2026-09-20", "end_date": "2026-09-22",
                                               "budget_ids": [base["inc"]["id"]]}).json()["id"]
    for query in ("extra_checks=false", q, q2, f"extra_checks=false&signer_id={people[0]}&signer_id={people[1]}&blank_lines=2"):
        assert _text(env.ru.get(f"/api/fundraisers/{long_id}/count-sheet?{query}").content)[0] == 1, query
        assert _text(env.ru.get(f"/api/fundraisers/{long_id}/count-sheet?{query.replace('extra_checks=false', 'extra_checks=true')}").content)[0] == 2, query
    org = env.entity("Some Company")["id"]
    assert env.ru.get(f"/api/fundraisers/{fid}/count-sheet?signer_id={org}").status_code == 422
    assert env.ru.get(f"/api/fundraisers/{fid}/count-sheet?signer_id={people[0]}&signer_id={people[0]}").status_code == 422
    ev = env.auditor.get("/api/audit-events?action=REPORT_GENERATED&object_type=fundraiser").json()["items"]
    assert any(e["after"]["report"] == "CASH_COUNT_SHEET" for e in ev)
