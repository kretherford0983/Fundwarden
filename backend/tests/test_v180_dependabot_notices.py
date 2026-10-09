"""1.8.0 (#98): Dependabot's Python pull requests run the tests - the notices step regenerates instead of failing on
Dependabot pull requests and develop builds, and stays strict everywhere else (pull requests into test and main, the
test and main builds). A shipped package missing from requirements.txt is named."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"


def _script():
    spec = importlib.util.spec_from_file_location("tpn", ROOT / "scripts" / "third_party_notices.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tests_workflow_has_the_notices_input_and_both_modes():
    t = (WF / "tests.yml").read_text()
    assert "inputs:\n      notices:" in t and "default: check" in t
    assert "--regenerate" in t and "--check" in t and 'if [ "$NOTICES" = "regenerate" ]' in t


def test_only_dependabot_pull_requests_and_develop_builds_regenerate():
    ci = (WF / "ci.yml").read_text()
    assert "notices: ${{ startsWith(github.head_ref, 'dependabot/') && 'regenerate' || 'check' }}" in ci
    build = (WF / "build.yml").read_text()
    assert "notices: ${{ github.ref_name == 'develop' && 'regenerate' || 'check' }}" in build


def test_unpinned_packages_are_named():
    tpn = _script()
    comps = [{"name": "fastapi", "version": "1.0"}, {"name": "Brand_New.Pkg", "version": "2.3"},
             {"name": "colorama", "version": "0.4.6"}]
    assert tpn.unpinned(comps) == ["Brand_New.Pkg==2.3"]       # fastapi is pinned; colorama is listed separately
