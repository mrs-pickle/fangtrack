"""
Auth flow tests via the Flask test client on a throwaway DB. Covers the multi-tenant
guarantees that matter for a public beta: first-user-is-admin, per-user isolation,
gating, CSRF, and login/logout.

Run:  python tests/test_auth.py
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fresh temp DB BEFORE importing the app, and never Postgres.
os.environ.pop("DATABASE_URL", None)
os.environ["FANGTRACK_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "auth_test.sqlite")

import wsgi  # runs _init_schema() → full schema incl. user_id columns on the temp DB
app = wsgi.app
app.config["TESTING"] = True


def _reset():
    """Isolate tests: clear users + rate-limiter so each starts with 'no accounts yet'
    (the first registrant becomes admin)."""
    import auth
    from database.db import get_connection
    conn = get_connection()
    conn.execute("DELETE FROM users")
    conn.execute("DELETE FROM password_resets")
    conn.execute("UPDATE collection SET user_id=NULL")
    conn.commit()
    conn.close()
    auth._RATE_HITS.clear()


def _csrf(client):
    # /register renders the token while logged-out (redirects once authenticated);
    # /collection renders it for any logged-in user (base.html emits window.CSRF).
    # NB: /settings is admin-only now, so it can't be the logged-in fallback.
    for path in ("/register", "/collection"):
        m = re.search(r'window\.CSRF = "([a-f0-9]+)"', client.get(path).get_data(as_text=True))
        if m:
            return m.group(1)
    return ""


def _register(client, email, pw="password123", name="U"):
    tok = _csrf(client)
    return client.post("/register", data={"_csrf": tok, "email": email,
                                          "password": pw, "display_name": name})


def test_admin_via_allowlist_and_isolation():
    _reset()
    c1 = app.test_client()
    r = _register(c1, "admin@x.com")
    assert r.status_code == 302, "register should redirect"
    # Registration NO LONGER auto-grants admin (public signup on empty DB must not).
    assert c1.get("/history").status_code == 403, "first registrant must NOT be auto-admin"

    # Admin is granted only via the FANGTRACK_ADMIN_EMAILS allowlist, applied at init.
    import auth
    os.environ["FANGTRACK_ADMIN_EMAILS"] = "admin@x.com"
    try:
        auth.init_auth_tables()
    finally:
        os.environ.pop("FANGTRACK_ADMIN_EMAILS", None)
    assert c1.get("/history").status_code == 200, "allowlisted account should be admin"

    # second user: non-admin, empty collection, no admin access
    c2 = app.test_client()
    _register(c2, "tester@x.com")
    assert c2.get("/history").status_code == 403, "non-admin must be forbidden from admin"
    body = c2.get("/collection").get_data(as_text=True)
    assert "ANIMALS" in body or "empty" in body.lower()


def test_gating_redirects_anonymous():
    _reset()
    c = app.test_client()
    for path in ("/collection", "/watchlist", "/settings", "/history"):
        r = c.get(path)
        assert r.status_code == 302 and "/login" in r.headers["Location"], path


def test_public_pages_open_anonymously():
    _reset()
    c = app.test_client()
    for path in ("/", "/deals", "/species", "/login", "/register"):
        assert c.get(path).status_code == 200, path


def test_healthz_is_cookieless_and_bypasses_before_request():
    # Render's liveness probe must be a pure in-memory 200 with no per-request work:
    # no session/CSRF cookie write (so a slow DB can't delay it and flap the instance,
    # the 2026-07-20 outage). A Set-Cookie here means the before_request hook ran.
    _reset()
    c = app.test_client()
    r = c.get("/healthz")
    assert r.status_code == 200 and r.get_json() == {"status": "ok"}
    assert "Set-Cookie" not in r.headers, "healthz must not write a session cookie"


def test_csrf_blocks_tokenless_post():
    _reset()
    c = app.test_client()
    _register(c, "csrf@x.com")
    # POST without the token → 400
    r = c.post("/collection/add", data={"species": "Grammostola pulchra"})
    assert r.status_code == 400, "tokenless POST must be rejected"


def test_login_logout_and_wrong_password():
    _reset()
    c = app.test_client()
    _register(c, "loginflow@x.com", pw="password123")
    c.post("/logout", data={"_csrf": _csrf(c)})   # logout is POST-only now
    tok = _csrf(c)
    bad = c.post("/login", data={"_csrf": tok, "email": "loginflow@x.com", "password": "nope"})
    assert "Wrong email or password" in bad.get_data(as_text=True)
    tok = _csrf(c)
    good = c.post("/login", data={"_csrf": tok, "email": "loginflow@x.com", "password": "password123"})
    assert good.status_code == 302, "correct login should redirect"


def test_password_reset_flow():
    import auth
    _reset()
    c = app.test_client()
    _register(c, "resetme@x.com", pw="password123")
    c.post("/logout", data={"_csrf": _csrf(c)})

    # Capture the emailed reset link instead of actually sending mail.
    captured = []
    orig = auth._deliver_reset_email
    auth._deliver_reset_email = lambda to, name, link: captured.append(link)
    try:
        r = c.post("/forgot", data={"_csrf": _csrf(c), "email": "resetme@x.com"})
        assert r.status_code == 302, "forgot should redirect to login"
        assert captured, "a reset link should have been generated for a real account"

        # An unknown email must look identical (no user enumeration) and issue no token.
        c2 = app.test_client()
        before = len(captured)
        c2.post("/forgot", data={"_csrf": _csrf(c2), "email": "nobody@x.com"})
        assert len(captured) == before, "no token should be issued for an unknown email"
    finally:
        auth._deliver_reset_email = orig

    token = captured[0].rsplit("/reset/", 1)[1]
    # The reset page loads for a valid token…
    assert c.get(f"/reset/{token}").status_code == 200
    # …and setting a new password works, then the token is single-use.
    rc = app.test_client()
    r = rc.post(f"/reset/{token}", data={"_csrf": _csrf(rc), "password": "brandnew456"})
    assert r.status_code == 302
    assert rc.get(f"/reset/{token}").status_code == 302, "used token must be rejected"

    # Old password no longer works; new one does.
    lc = app.test_client()
    bad = lc.post("/login", data={"_csrf": _csrf(lc), "email": "resetme@x.com", "password": "password123"})
    assert "Wrong email or password" in bad.get_data(as_text=True)
    good = lc.post("/login", data={"_csrf": _csrf(lc), "email": "resetme@x.com", "password": "brandnew456"})
    assert good.status_code == 302, "new password should sign in"


def test_change_password():
    _reset()
    c = app.test_client()
    _register(c, "changer@x.com", pw="oldpass123")
    # wrong current password is rejected
    r = c.post("/settings/password", data={"_csrf": _csrf(c), "current_password": "nope",
                                            "new_password": "newpass456"}, follow_redirects=True)
    assert "incorrect" in r.get_data(as_text=True)
    # correct change works
    c.post("/settings/password", data={"_csrf": _csrf(c), "current_password": "oldpass123",
                                        "new_password": "newpass456"})
    c.post("/logout", data={"_csrf": _csrf(c)})
    lc = app.test_client()
    bad = lc.post("/login", data={"_csrf": _csrf(lc), "email": "changer@x.com", "password": "oldpass123"})
    assert "Wrong email or password" in bad.get_data(as_text=True)
    good = lc.post("/login", data={"_csrf": _csrf(lc), "email": "changer@x.com", "password": "newpass456"})
    assert good.status_code == 302


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    passed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  ok   {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {name}: {e}")
        except Exception as e:
            print(f"  ERR  {name}: {e!r}")
    print(f"{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
