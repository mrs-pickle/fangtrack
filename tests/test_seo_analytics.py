"""
Link-preview + analytics plumbing.

FangTrack grows by people PASTING LINKS into invert groups, so a broken Open
Graph tag or an empty sitemap is a growth bug, not a cosmetic one — and both
fail SILENTLY (the page still renders 200). These tests are the alarm.

Run:  python -m pytest tests/test_seo_analytics.py
"""
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("FANGTRACK_DB_PATH",
                      os.path.join(tempfile.mkdtemp(), "seo_test.sqlite"))

import wsgi
app = wsgi.app
app.config["TESTING"] = True


# ── robots.txt advertises the sitemap ───────────────────────────────────────
def test_robots_points_at_the_sitemap():
    r = app.test_client().get("/robots.txt")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Sitemap:" in body and "/sitemap.xml" in body


# ── sitemap is valid XML crawlers will accept ───────────────────────────────
def test_sitemap_is_well_formed_and_lists_pages():
    r = app.test_client().get("/sitemap.xml")
    assert r.status_code == 200
    assert "xml" in r.headers["Content-Type"]
    root = ET.fromstring(r.get_data(as_text=True))          # raises if malformed
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [e.text for e in root.iter(f"{ns}loc")]
    assert locs, "sitemap has no <loc> entries"
    assert all(u.startswith("http") for u in locs), "sitemap needs ABSOLUTE urls"


def test_sitemap_never_advertises_a_url_that_would_404():
    """A sitemap entry that 404s becomes a Search Console error.

    A crawl re-keys price_history onto the canonical species immediately, but
    the cached catalog can still hold the old fragment for up to its TTL. Listing
    it would advertise a dead page. Every species URL must be a CANONICAL key.
    """
    from urllib.parse import unquote
    from normalize.key_aliases import canonicalize_key
    r = app.test_client().get("/sitemap.xml")
    root = ET.fromstring(r.get_data(as_text=True))
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    locs = [e.text for e in root.iter(f"{ns}loc")]
    assert len(locs) == len(set(locs)), "sitemap lists a duplicate URL"
    for loc in locs:
        if "/species/" not in loc:
            continue
        key = unquote(loc.split("/species/", 1)[1])
        assert canonicalize_key(key) == key, f"non-canonical key in sitemap: {key}"


def test_sitemap_lastmod_is_a_real_date_and_not_in_the_future():
    """lastmod has to be TRUE to be worth anything.

    Stamping today on every page daily is how a crawler learns to ignore the
    field. Species pages carry the date we last observed a listing, so a future
    or malformed date means that wiring broke.
    """
    import datetime as _dt
    r = app.test_client().get("/sitemap.xml")
    root = ET.fromstring(r.get_data(as_text=True))
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    today = _dt.datetime.now(_dt.timezone.utc).date()
    mods = [e.text for e in root.iter(f"{ns}lastmod")]
    assert mods, "no lastmod entries"
    for m in mods:
        d = _dt.date.fromisoformat(m)             # raises on a malformed date
        assert d <= today, f"lastmod in the future: {m}"


# ── the event queue survives a redirect, and drains exactly once ────────────
def test_track_event_queues_and_drains_once():
    import app as fangtrack
    with app.test_request_context("/"):
        from flask import session
        fangtrack.track_event("watchlist_add", species="Poecilotheria metallica")
        assert len(session.get("_ga_events")) == 1
        drained = fangtrack.inject_analytics()["ga_events"]
        assert drained[0]["name"] == "watchlist_add"
        assert drained[0]["params"]["species"] == "Poecilotheria metallica"
        # Draining must empty the queue, or every later page refires the event
        # and the conversion count silently inflates.
        assert not session.get("_ga_events")
        assert fangtrack.inject_analytics()["ga_events"] == []


def test_track_event_drops_empty_params_and_caps_the_queue():
    import app as fangtrack
    with app.test_request_context("/"):
        from flask import session
        fangtrack.track_event("sign_up", method="email", extra=None)
        assert "extra" not in session["_ga_events"][0]["params"]
        for i in range(20):
            fangtrack.track_event("noise", i=i)
        assert len(session["_ga_events"]) <= 5, "queue must stay bounded"


def test_track_event_never_raises():
    """Analytics must not be able to break a real request."""
    import app as fangtrack
    fangtrack.track_event("outside_request_context", foo="bar")   # no exception
