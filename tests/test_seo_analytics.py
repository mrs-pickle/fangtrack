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
