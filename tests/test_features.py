"""
Regression tests for the features added over the 2026-07-16/17 sprint:
species-404 guard, leaderboard + public-profile privacy, sale badge, and description
capture. Uses the Flask test client on a throwaway DB.

Run:  python tests/test_features.py
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.pop("DATABASE_URL", None)
os.environ["FANGTRACK_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "features_test.sqlite")

import wsgi           # builds full schema on the temp DB
import app as appmod
app = wsgi.app
app.config["TESTING"] = True
from database.db import get_connection, DB_PATH


def _reset():
    conn = get_connection(DB_PATH)
    conn.execute("DELETE FROM users")
    conn.execute("UPDATE collection SET user_id=NULL")
    conn.commit()
    conn.close()
    import auth
    auth._RATE_HITS.clear()


def _csrf(c):
    # base.html injects window.CSRF on every rendered page. /register only renders it
    # while logged-out (it redirects once authenticated), so fall back to /settings,
    # which renders for a logged-in user.
    for path in ("/register", "/settings"):
        resp = c.get(path)
        m = re.search(r'window\.CSRF = "([a-f0-9]+)"', resp.get_data(as_text=True))
        if m:
            return m.group(1)
    return ""


def _register(c, email="collector@x.com"):
    return c.post("/register", data={"_csrf": _csrf(c), "email": email,
                                     "password": "password123", "display_name": "Collector"})


# ── species-404 guard ─────────────────────────────────────────────────────────
def test_species_missing_returns_404():
    c = app.test_client()
    r = c.get("/species/zzz%20nonexistent%20species")
    assert r.status_code == 404, "a species with no data must 404, not a broken 200"


# ── leaderboard + public-profile privacy ──────────────────────────────────────
def test_leaderboard_and_profile_privacy():
    _reset()
    c = app.test_client()
    _register(c, "collector@x.com")
    # add a collection item WITH a private purchase price
    c.post("/collection/add", data={"_csrf": _csrf(c), "species": "Grammostola pulchra",
                                    "quantity": "1"})
    c.get("/collection")   # ensures the price_paid/acquired_date/source columns exist
    conn = get_connection(DB_PATH)
    # distinctive sentinel so the leak check can't collide with incidental digits
    # elsewhere in the page (e.g. a CSS z-index).
    conn.execute("UPDATE collection SET price_paid=76543 WHERE species_key='grammostola pulchra'")
    conn.commit()
    conn.close()
    # go public with a handle
    c.post("/profile/save", data={"_csrf": _csrf(c), "is_public": "on", "handle": "mycoll"})

    # anonymous leaderboard lists the collector
    lb = app.test_client().get("/leaderboard").get_data(as_text=True)
    assert "mycoll" in lb, "public collector should appear on the leaderboard"

    # public profile shows the species but NEVER the price paid
    prof = app.test_client().get("/u/mycoll")
    assert prof.status_code == 200
    body = prof.get_data(as_text=True)
    assert "Grammostola pulchra" in body
    assert "76543" not in body, "public profile must not leak the private purchase price"


def test_private_profile_404s():
    _reset()
    c = app.test_client()
    _register(c, "shy@x.com")
    c.post("/profile/save", data={"_csrf": _csrf(c), "handle": "shy"})  # no is_public
    assert app.test_client().get("/u/shy").status_code == 404


# ── sale badge ────────────────────────────────────────────────────────────────
def test_sale_label_annotation():
    # seed a vendor + one in-stock listing + an active SITEWIDE SALE code, then confirm
    # get_snapshot tags the listing with a sale_label.
    from database.db import upsert_vendor, insert_crawl_run, save_listings, init_discount_tables
    from models import Listing, CrawlResult
    init_discount_tables(DB_PATH)
    upsert_vendor("salev", "SaleVendor", "http://x", "shopify")
    cr = CrawlResult(vendor_key="salev", vendor_name="SaleVendor"); cr.status = "complete"
    rid = insert_crawl_run(cr, DB_PATH)
    save_listings([Listing(vendor="SaleVendor", vendor_key="salev",
                           scientific_name="Brachypelma hamorii", price_usd=50,
                           availability="in_stock")], rid, DB_PATH)
    conn = get_connection(DB_PATH)
    conn.execute("INSERT INTO discount_codes (vendor_key, code, discount_type, discount_value, is_active, is_verified) "
                 "VALUES ('salev','SITEWIDE SALE','pct',20,1,1)")
    conn.commit()
    conn.close()
    appmod._snapshot_cache["data"] = None      # bust cache
    snap = appmod.get_snapshot(force=True)
    mine = [l for l in snap if l.get("vendor_key") == "salev"]
    assert mine, "seeded listing should be in the snapshot"
    assert mine[0].get("sale_label") == "SALE", "active sitewide sale should set sale_label"
    assert mine[0].get("sale_pct") == 20


# ── private sellers are account-only ──────────────────────────────────────────
def test_private_sellers_hidden_from_anonymous():
    from database.db import upsert_vendor, insert_crawl_run, save_listings
    from models import Listing, CrawlResult
    _reset()
    upsert_vendor("secretguy", "Secret Private Seller", "", "private_seller")
    cr = CrawlResult(vendor_key="secretguy", vendor_name="Secret Private Seller")
    cr.status = "complete"
    rid = insert_crawl_run(cr, DB_PATH)
    save_listings([Listing(vendor="Secret Private Seller", vendor_key="secretguy",
                           scientific_name="Aphonopelma chalchodes", price_usd=40,
                           availability="in_stock")], rid, DB_PATH)
    # Stamp the canonical key so the listing lands on the species card (the deal
    # pipeline does this normally; save_listings alone leaves it blank).
    conn = get_connection(DB_PATH)
    conn.execute("UPDATE price_history SET scientific_name_key='aphonopelma chalchodes' "
                 "WHERE vendor_key='secretguy'")
    conn.commit()
    conn.close()
    appmod._snapshot_cache["data"] = None

    # Anonymous: the private seller must NOT appear on the species card.
    anon = app.test_client().get("/species/aphonopelma chalchodes").get_data(as_text=True)
    assert "secretguy" not in anon, "private seller leaked to a logged-out visitor"

    # Signed-in (first user = admin): the private seller IS visible.
    appmod._snapshot_cache["data"] = None
    c = app.test_client()
    _register(c, "owner@x.com")
    seen = c.get("/species/aphonopelma chalchodes").get_data(as_text=True)
    assert "secretguy" in seen, "private seller should be visible once signed in"


# ── livestock filter: art prints must not pass ────────────────────────────────
def test_art_prints_are_not_livestock():
    from normalize.livestock import is_livestock
    # named-species art prints sold by photo dimension must be rejected…
    assert not is_livestock("Print 5X7 of Typhochlaena seladonia by Gray Ghost Creations!")
    assert not is_livestock("Poecilotheria metallica 2x3 print")
    # …while real listings whose common names contain 'patch'/'bark' still pass.
    assert is_livestock("Hapalopus formosus (Pumpkin patch tarantula)")
    assert is_livestock("Centruroides sculpturatus (Arizona bark scorpion)")


# ── truncated runs don't shrink the snapshot ──────────────────────────────────
def test_snapshot_skips_truncated_run():
    from database.db import (upsert_vendor, insert_crawl_run, save_listings,
                             get_connection)
    from models import Listing, CrawlResult
    upsert_vendor("truncv", "TruncVendor", "http://x", "shopify")
    # run 1: a good, complete run with two species in stock
    cr1 = CrawlResult(vendor_key="truncv", vendor_name="TruncVendor"); cr1.status = "complete"
    rid1 = insert_crawl_run(cr1, DB_PATH)
    save_listings([
        Listing(vendor="TruncVendor", vendor_key="truncv", scientific_name="Brachypelma hamorii",
                price_usd=50, availability="in_stock"),
        Listing(vendor="TruncVendor", vendor_key="truncv", scientific_name="Grammostola pulchra",
                price_usd=90, availability="in_stock"),
    ], rid1, DB_PATH)
    # run 2 (newer): truncated — captured only one species before a 429
    cr2 = CrawlResult(vendor_key="truncv", vendor_name="TruncVendor"); cr2.status = "partial"
    rid2 = insert_crawl_run(cr2, DB_PATH)
    save_listings([
        Listing(vendor="TruncVendor", vendor_key="truncv", scientific_name="Brachypelma hamorii",
                price_usd=50, availability="in_stock"),
    ], rid2, DB_PATH)
    conn = get_connection(DB_PATH)
    conn.execute("UPDATE crawl_runs SET truncated=1 WHERE id=?", (rid2,))
    conn.commit(); conn.close()

    appmod._snapshot_cache["data"] = None
    snap = appmod.get_snapshot(force=True)
    mine = [l for l in snap if l.get("vendor_key") == "truncv"]
    # The snapshot must fall back to run 1 (2 listings), NOT the truncated run 2 (1).
    assert len(mine) == 2, f"snapshot should keep the last good run, got {len(mine)} listings"


# ── species trait badges ──────────────────────────────────────────────────────
def test_trait_badges():
    from normalize.traits import trait_badges, traits_for
    # species override wins
    gbb = trait_badges("chromatopelma cyaneopubescens")
    vals = {b["axis"]: b["value"] for b in gbb["badges"]}
    assert vals["hemisphere"] == "New World" and vals["temperament"] == "Skittish"
    assert gbb["kind"] == "Tarantula"
    # genus fallback for a species not explicitly overridden
    poeci = traits_for("poecilotheria metallica")
    assert poeci and poeci["hemisphere"] == "Old World" and poeci["experience"] == "Advanced"
    # non-tarantula carries its kind
    assert trait_badges("pandinus imperator")["kind"] == "Scorpion"
    # unknown species → no badges, doesn't crash
    assert trait_badges("zzz nonexistent")["badges"] == []
    # badge order is locked (hemisphere first)
    assert gbb["badges"][0]["axis"] == "hemisphere"


# ── like-for-like collection valuation ────────────────────────────────────────
def test_like_for_like_valuation():
    lfl = appmod._like_for_like_value
    listings = [
        {"sex": "F", "size_midpoint": 5.0, "price_usd": 250},
        {"sex": "F", "size_midpoint": 4.0, "price_usd": 300},
        {"sex": "F", "size_midpoint": 4.5, "price_usd": 200},
        {"sex": "Unknown", "size_midpoint": 0.5, "price_usd": 40},
        {"sex": "Unknown", "size_midpoint": 0.5, "price_usd": 50},
        {"sex": "Unknown", "size_midpoint": 0.75, "price_usd": 60},
    ]
    # An adult female is valued against the female comps, NOT the cheap slings.
    fval, fbasis = lfl({"sex": "F", "size_notes": "Adult female"}, listings, blended=95)
    assert fval >= 200, f"adult female should reflect female comps, got {fval}"
    assert "female" in fbasis

    # An unsexed sling is valued against the slings, not blended up by the females.
    sval, sbasis = lfl({"sex": "U", "size_notes": '0.5" sling'}, listings, blended=95)
    assert sval <= 70, f"sling should reflect sling comps, got {sval}"

    # No matching listings → falls back to the blended species median.
    nval, nbasis = lfl({"sex": "U", "size_notes": None}, [], blended=95)
    assert nval == 95 and nbasis == "market median"


# ── description capture ───────────────────────────────────────────────────────
def test_description_capture_and_clean():
    from vendors.base import _clean_description
    assert _clean_description("<p>Captive&nbsp;bred <b>sling</b></p>") == "Captive bred sling"
    assert _clean_description("") is None
    assert _clean_description(None) is None
    # cap length
    assert len(_clean_description("x" * 5000)) == 800


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
