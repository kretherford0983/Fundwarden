"""1.6.7: Audit / Fiscal Year Close report - with several bank accounts, each account's transactions sit between a
"Start of transactions" page and an "End of transactions" page that state the account's page range."""
import io
import re

from pypdf import PdfReader

from test_v12_reports import make_pdf, up


def texts(content: bytes) -> list[str]:
    return [" ".join((p.extract_text() or "").split()) for p in PdfReader(io.BytesIO(content)).pages]


def two_accounts(env, base):
    a1 = base["acct"]["id"]
    other = env.account(opening="0.00")
    t1 = env.txn(a1, "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "3.00"}], date="2026-08-01")
    up(env, "transaction", t1["id"], "invoice.pdf", make_pdf("INVOICE", pages=3))   # makes the section several pages
    t2 = env.txn(a1, "DEPOSIT", [{"budget_id": base["inc_leaf"], "amount": "20.00"}], date="2026-09-01")
    t3 = env.txn(other["id"], "WITHDRAWAL", [{"budget_id": base["exp_leaf"], "amount": "4.00"}], date="2026-08-15")
    env.ru.post(f"/api/transactions/{t3['id']}/void", {"reason": "x", "confirm_irreversible": True})
    return a1, other, (t1, t2, t3)


def sections(pages: list[str]) -> list[tuple[int, int]]:
    starts = [i + 1 for i, t in enumerate(pages) if t.startswith("Start of transactions")]
    ends = [i + 1 for i, t in enumerate(pages) if t.startswith("End of transactions")]
    assert len(starts) == len(ends)
    return list(zip(starts, ends))


def test_each_account_is_framed_by_a_start_and_an_end_page(env, base):
    fy = base["fy"]["id"]
    a1, other, (t1, t2, t3) = two_accounts(env, base)
    for url in (f"/api/reports/audit?fiscal_year_id={fy}", f"/api/reports/fy-close?fiscal_year_id={fy}"):
        pages = texts(env.auditor.get(url).content)
        total = len(pages)
        secs = sections(pages)
        assert len(secs) == 2
        names = [base["acct"]["account_name"], other["account_name"]]
        order = sorted(range(2), key=lambda i: names[i].lower())      # accounts are in name order
        ids = [[t1["id"], t2["id"]], [t3["id"]]]
        prev_end = 0
        for n, (first, last) in enumerate(secs):
            name, mine = names[order[n]], ids[order[n]]
            assert first > prev_end
            prev_end = last
            size = last - first + 1
            start, end = pages[first - 1], pages[last - 1]
            assert name in start and name in end and f"Account in this report {n + 1} of 2" in start
            # both pages state the same range, each naming the other one
            span = f"pages {first} to {last} of {total} ({size} pages"
            assert span in start and span in end
            assert f"Its last page is page {last}" in start and f"Its first page is page {first}" in end
            assert f"First transaction #{mine[0]}" in start and f"Last transaction #{mine[-1]}" in end
            # every page in between carries the account and a gap-free "section page k of n"
            for k, pg in enumerate(range(first, last + 1), start=1):
                assert f"section page {k} of {size}" in pages[pg - 1] and f"Page {pg} of {total}" in pages[pg - 1]
            # the account's transactions - and only those - are inside its section
            inside = " ".join(pages[first:last - 1])
            found = {int(x) for x in re.findall(r"Transaction #(\d+)", inside)}
            assert set(mine) <= found and not found & (set(sum(ids, [])) - set(mine))
        # nothing before the first or after the last section is marked as part of a section
        assert all("section page" not in pages[i] for i in range(secs[0][0] - 1))
        assert "Next This was the last account in the report." in pages[secs[-1][1] - 1]
        assert f"Next {names[order[1]]}" in pages[secs[0][1] - 1]
        assert 'begins with a "Start of transactions" page' in pages[1]
    assert "1 — 0 active, 1 VOID" in pages[secs[order.index(1)][0] - 1]
    # the audit log records the page range of each account
    ev = env.auditor.get("/api/audit-events?object_type=fiscal_year&sort=id&direction=desc").json()["items"]
    last = next(e for e in ev if e["action"] == "REPORT_GENERATED")
    assert [(s["first_page"], s["last_page"]) for s in last["after"]["account_sections"]] == secs


def test_one_account_gets_no_section_pages(env, base):
    fy = base["fy"]["id"]
    a1, other, _ = two_accounts(env, base)
    for q in (f"&bank_account_id={a1}", "&include_void=false"):     # filtered to one / the other has only a VOID
        pages = texts(env.auditor.get(f"/api/reports/audit?fiscal_year_id={fy}{q}").content)
        assert sections(pages) == [] and all("section page" not in t for t in pages)
        assert "grouped by bank account" not in pages[1]

