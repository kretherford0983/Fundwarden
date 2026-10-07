"""1.6.8 (#66): the two code changes made after the first CodeQL results - the pre-sign-in form token cookie and the
phone extension pattern. Behaviour for users is unchanged; these tests pin that down."""
import time

import pytest

from fmpoc import phone
from fmpoc.deps import PRE_CSRF_COOKIE

from conftest import Api, PASSWORD


def test_form_token_cookie_is_written_once_and_then_returned(app):
    a = Api(app)
    first = a.c.get("/api/auth/csrf")
    token = first.json()["csrf_token"]
    assert len(token) == 43 and PRE_CSRF_COOKIE in first.headers.get("set-cookie", "")
    assert a.c.cookies.get(PRE_CSRF_COOKIE) == token
    # the browser has the cookie now: the same token comes back and the cookie is not written again
    again = a.c.get("/api/auth/csrf")
    assert again.json()["csrf_token"] == token and "set-cookie" not in again.headers


@pytest.mark.parametrize("planted", ["x", "a" * 42, "a" * 44, "a" * 42 + ";", "<script>alert(1)</script>",
                                     "a" * 20 + " " + "a" * 22])
def test_form_token_cookie_that_is_not_ours_is_replaced(app, planted):
    a = Api(app)
    a.c.cookies.set(PRE_CSRF_COOKIE, planted)
    r = a.c.get("/api/auth/csrf")
    token = r.json()["csrf_token"]
    assert token != planted and len(token) == 43
    assert f"{PRE_CSRF_COOKIE}={token}" in r.headers["set-cookie"]


def test_sign_in_with_the_form_token_still_works_and_still_needs_it(env):
    a = Api(env.app)
    assert a.login("reguser").status_code == 200           # token from /api/auth/csrf, sent as cookie + header
    b = Api(env.app)
    b.pre_csrf()
    r = b.c.post("/api/auth/login", json={"username": "reguser", "password": PASSWORD})   # cookie, no header
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED"
    r = b.c.post("/api/auth/login", json={"username": "reguser", "password": PASSWORD},
                 headers={"X-CSRF-Token": "A" * 43})                                       # header that is not the cookie
    assert r.status_code == 403


def test_phone_extensions_are_read_as_before():
    for typed in ("555-123-4567 x204", "555-123-4567x204", "5551234567 ext 204", "5551234567   ext.   204  ",
                  "(555) 123-4567 Ext. 204", "555.123.4567#204", "555 123 4567 # 204", "555-123-4567 X 204"):
        assert phone.normalize(typed) == "5551234567x204", typed
    assert phone.normalize("555-123-4567") == "5551234567"
    assert phone.normalize("+44 20 7123 4567") == "+442071234567"
    for bad in ("555-123-4567 x", "555-123-4567 ext", "x204", "555-123-4567 x123456789", "+44 20 7123 4567 x2"):
        with pytest.raises(ValueError):
            phone.normalize(bad)


def test_phone_extension_pattern_is_linear_on_long_runs_of_spaces():
    # before 1.6.8 this took time proportional to the square of the length (about 50,000 spaces: many seconds)
    for typed in ("5" + " " * 50_000 + "5", " " * 50_000 + "x", "x" + " " * 50_000 + "a", "5551234567" + " x" * 25_000):
        started = time.perf_counter()
        with pytest.raises(ValueError):
            phone.normalize(typed)
        assert time.perf_counter() - started < 1.0
