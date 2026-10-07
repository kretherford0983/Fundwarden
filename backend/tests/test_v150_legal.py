"""v1.5.0: AGPL-3.0 license, third-party notices and the source-code link (AGPL section 13)."""
import json

from fmpoc import legal


def test_status_and_version_offer_the_source(env):
    s = env.admin.get("/api/system/status").json()
    assert s["license"] == "AGPL-3.0-only" and s["source_url"].startswith("https://github.com/kretherford0983/PennyWarden")
    v = env.ru.get("/api/system/version").json()
    assert v["license"] == "AGPL-3.0-only" and v["source_url"] == s["source_url"]


def test_legal_documents_are_served_without_sign_in(anon):
    r = anon.get("/api/system/legal/license")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in r.text and "Version 3, 19 November 2007" in r.text
    n = anon.get("/api/system/legal/notices")
    assert n.status_code == 200 and "INVENTORY" in n.text and "reportlab" in n.text and "recharts" in n.text
    assert anon.get("/api/system/legal/../../config.py").status_code == 404
    assert anon.get("/api/system/legal/secrets").status_code == 404


def test_source_link_points_at_the_build_commit(monkeypatch, tmp_path):
    f = tmp_path / "build_info.json"
    f.write_text(json.dumps({"version": "1.5.0", "commit": "abc1234"}))
    monkeypatch.setattr("fmpoc.config.BUILD_INFO_FILE", f)
    assert legal.source_url() == "https://github.com/kretherford0983/PennyWarden/tree/abc1234"
    f.write_text(json.dumps({"version": "1.5.0", "commit": "<script>"}))
    assert legal.source_url() == "https://github.com/kretherford0983/PennyWarden"
