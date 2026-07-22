#!/usr/bin/env python3
"""
Tarantula Market Tracker — Local Web App
Run with: python app.py
Opens automatically at http://localhost:5000
"""
import os, sys, json, threading, time, logging, smtplib
from email.message import EmailMessage
from pathlib import Path
from datetime import datetime, timezone
from functools import lru_cache

# Windows consoles default to cp1252, which can't encode the spider emoji in
# the startup banner (or ″ marks in logged listing text) — the app then dies
# with UnicodeEncodeError before serving. Force UTF-8 with replacement.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, Response, session, g, abort,
                   send_from_directory)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db import (get_connection, init_db, upsert_vendor, DB_PATH,
                          init_discount_tables, get_all_shipping)
from database.history import (get_crawl_summary, get_all_history_for_export,
                               get_species_price_history, get_all_historical_lows,
                               populate_historical_lows)
from scoring.deals import rate_all, score_all_listings, compute_fire_deals
from scoring.rarity import (compute_all_rarity, annotate_listings_with_rarity,
                             compute_size_class_rarity, annotate_with_size_class_rarity)
from scoring.trends import annotate_with_trends
from scoring.watchlist import (init_watchlist_tables, add_target, remove_target,
                                list_targets, check_watchlist, print_watchlist_hits)
from scoring.sex_probability import annotate_sex_probability
from normalize.source_type import annotate_source_types
from normalize.species import normalize_species_key

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Structured file logging (rotating) alongside stdout, so errors survive a restart.
try:
    from logging.handlers import RotatingFileHandler
    os.makedirs("logs", exist_ok=True)
    _fh = RotatingFileHandler("logs/app.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(_fh)
except Exception as _e:  # never let logging setup crash the app
    logger.warning(f"File logging disabled: {_e}")

# Optional error tracking (Sentry). Activates only if SENTRY_DSN is set AND sentry-sdk is
# installed — no hard dependency, no-op otherwise.
if os.environ.get("SENTRY_DSN"):
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=os.environ["SENTRY_DSN"],
                        traces_sample_rate=0.0,
                        environment=os.environ.get("FANGTRACK_ENV", "production"))
        logger.info("Sentry error tracking enabled.")
    except Exception as _e:
        logger.warning(f"Sentry not enabled: {_e}")

app = Flask(__name__)
# Secret key: required in production. A hardcoded fallback in the repo would let
# anyone forge a signed session cookie (auth as any user), so fail closed when we
# look like prod (Postgres or HTTPS configured) and the env var isn't set.
_secret = os.environ.get("FANGTRACK_SECRET_KEY")
_is_prod = bool(os.environ.get("DATABASE_URL") or os.environ.get("FANGTRACK_HTTPS"))
if not _secret:
    if _is_prod:
        # Prod-like env with no configured key: use an EPHEMERAL random key so we never
        # run on the repo's known fallback (which would allow session forgery). Sessions
        # won't survive a restart until FANGTRACK_SECRET_KEY is set — loud-log it. (We
        # don't raise: the cron also imports this module and has no key of its own.)
        import sys as _sys
        print("CRITICAL: FANGTRACK_SECRET_KEY not set in a prod-like env — using an "
              "ephemeral key. Set it on the web service so sessions persist across restarts.",
              file=_sys.stderr, flush=True)
        _secret = os.urandom(32).hex()
    else:
        _secret = "tmt-local-dev-secret-change-in-prod"
app.secret_key = _secret
# Cap request bodies so the collection uploader (pandas) can't be DoS'd with a huge file.
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024   # 5 MB
# Session cookie hardening. Secure by default whenever we look like prod.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("FANGTRACK_HTTPS")) or _is_prod,
)
# Let browsers (and the CDN) cache static files for a day instead of re-fetching
# every visit. The token CSS is ?v=-busted and images are stable; a change that
# must go out immediately is covered by a Cloudflare cache purge.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 86400  # 1 day

# Hand-rolled auth (users, login/register/logout, CSRF, @login_required/@admin_required).
from auth import (init_auth, login_required, admin_required,
                  current_user, current_user_id)
init_auth(app)


@app.errorhandler(413)
def _too_large(e):
    flash("That file is too large (5 MB max).", "error")
    return redirect(request.referrer or url_for("collection")), 302


@app.errorhandler(400)
def _bad_request(e):
    # Most 400s here are CSRF failures; guide the user to retry.
    return render_template("error.html", code=400,
                           msg="Your session expired or the form token was invalid. "
                               "Reload the page and try again."), 400


@app.errorhandler(403)
def _forbidden(e):
    return render_template("error.html", code=403,
                           msg="You don't have access to that. Admin only."), 403


@app.after_request
def _security_headers(resp):
    """Baseline hardening headers on every response. Kept conservative so they
    don't break the UI: no strict CSP yet (the templates use inline styles), just
    the non-breaking wins — MIME-sniffing off, clickjacking blocked, referrer
    trimmed, and HSTS once we're on HTTPS (prod)."""
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # CSP tuned to what the site actually loads: Tailwind CDN + inline styles/scripts
    # (base.html), and external product images on deals/species. Restricts everything
    # else — blocks 3rd-party script injection, framing (clickjacking), external form
    # posts, and <base> hijacking. Defense-in-depth (stored-XSS risk is already low).
    resp.headers.setdefault("Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' https://www.googletagmanager.com https://www.google-analytics.com "
        "https://*.google-analytics.com https://*.analytics.google.com; "
        "frame-ancestors 'self'; base-uri 'self'; form-action 'self'")
    if os.environ.get("FANGTRACK_HTTPS"):
        resp.headers.setdefault("Strict-Transport-Security",
                                "max-age=31536000; includeSubDomains")
    return resp


# When True (set by wsgi for the hosted web process) the request-serving code
# NEVER builds the heavy dashboard caches on a request — it loads the cron-built
# blobs via hydrate_caches(). Building live pegs the single worker's core, starves
# the 5s health check, and Render restart-loops the instance. The CRON (and local
# dev) leave this False and build normally, then persist the blobs.
_WEB_READONLY = False

# ── Market analytics (StockX/Keepa/TCG microstructure layer) ────────────────
_market_cache = {"data": None, "ts": 0}


def get_market_stats(force=False) -> dict:
    """Cached per-species market microstructure (lowest ask, market price, 90d
    range, liquidity, trend, sparkline). Rebuilt on each crawl / TTL."""
    now = time.time()
    if not force and _market_cache["data"] is not None and (now - _market_cache["ts"]) < _CACHE_TTL:
        return _market_cache["data"]
    if _WEB_READONLY and not force:
        hydrate_caches()
        return _market_cache["data"] if _market_cache["data"] is not None else {}
    try:
        from analytics.market import species_market_stats
        data = species_market_stats(DB_PATH)
    except Exception as e:
        logger.warning(f"market stats failed: {e}")
        data = {}
    _market_cache["data"] = data
    _market_cache["ts"] = now
    return data


# Species-CARD analytics. These were recomputed on EVERY /species/<key> load —
# compute_size_class_rarity (~0.9s, whole-DB scan) + inferred_sales (~1.4s) = ~2.3s
# of CPU per card on top of render. That per-request burn is what made cards take
# 5s AND spiked the 1-CPU box enough to time out the health check → restarts. They
# only change on a crawl, so memoize them to the crawl TTL like everything else.
_scr_cache = {"data": None, "ts": 0}
_sales_cache = {"data": None, "ts": 0}


def get_size_class_rarity(force=False) -> dict:
    now = time.time()
    if not force and _scr_cache["data"] is not None and (now - _scr_cache["ts"]) < _CACHE_TTL:
        return _scr_cache["data"]
    try:
        from scoring.rarity import compute_size_class_rarity
        _scr_cache["data"] = compute_size_class_rarity(DB_PATH)
    except Exception as e:
        logger.warning(f"size-class rarity cache failed: {e}")
        _scr_cache["data"] = {}
    _scr_cache["ts"] = now
    return _scr_cache["data"]


def get_inferred_sales(force=False) -> dict:
    """Inferred recent sales for ALL species; look up per-species from the dict."""
    now = time.time()
    if not force and _sales_cache["data"] is not None and (now - _sales_cache["ts"]) < _CACHE_TTL:
        return _sales_cache["data"]
    try:
        from analytics.market import inferred_sales
        _sales_cache["data"] = inferred_sales(DB_PATH)
    except Exception as e:
        logger.warning(f"inferred-sales cache failed: {e}")
        _sales_cache["data"] = {}
    _sales_cache["ts"] = now
    return _sales_cache["data"]


# Dashboard analytics that only change on a crawl. Recomputing them on every
# homepage load (heavy DB queries + Python) is what made the live site crawl on
# Render's 0.5-CPU box, so they're cached like the snapshot and invalidated by the
# crawl. `snap` is the (already-cached) REGISTRY-filtered snapshot.
_movers_cache = {"data": None, "ts": 0}
_intel_cache = {"data": None, "ts": 0}
_summary_cache = {"data": None, "ts": 0}
_rarity_legend_cache = {"data": None, "ts": 0}


_EMPTY_MOVERS = {"fire": [], "drops": [], "back_in_stock": [], "heating": [], "cooling": [], "stats": {}}
_EMPTY_INTEL = {"price_action": {}, "coverage": {}, "standouts": [], "new_this_crawl": 0}


def _cached_movers(snap, force=False) -> dict:
    now = time.time()
    if not force and _movers_cache["data"] is not None and (now - _movers_cache["ts"]) < _CACHE_TTL:
        return _movers_cache["data"]
    if _WEB_READONLY and not force:
        hydrate_caches()
        return _movers_cache["data"] if _movers_cache["data"] is not None else dict(_EMPTY_MOVERS)
    try:
        from analytics.market import market_movers
        movers = market_movers(snap, DB_PATH, limit=25)
        for _col in ("fire", "drops", "back_in_stock"):
            _attach_clean_names(movers.get(_col, []))
    except Exception as e:
        logger.warning(f"movers failed: {e}")
        movers = {"fire": [], "drops": [], "back_in_stock": [], "heating": [], "cooling": [], "stats": {}}
    _movers_cache["data"] = movers
    _movers_cache["ts"] = now
    return movers


def _cached_intel(snap, force=False) -> dict:
    now = time.time()
    if not force and _intel_cache["data"] is not None and (now - _intel_cache["ts"]) < _CACHE_TTL:
        return _intel_cache["data"]
    if _WEB_READONLY and not force:
        hydrate_caches()
        return _intel_cache["data"] if _intel_cache["data"] is not None else dict(_EMPTY_INTEL)
    try:
        from analytics.market import market_intelligence
        # intel is a SHARED, cron-built, blob-cached tile — it must not carry any
        # per-user "owned" set (that would bake one account's collection into the
        # blob everyone loads). Pass empty; owned marks are applied per-request
        # elsewhere via _req_owned().
        intel = market_intelligence(DB_PATH, snap, set())
    except Exception as e:
        logger.warning(f"market_intelligence failed: {e}")
        intel = {}
    if not isinstance(intel, dict):        # never let a fresh/empty DB 500 the homepage
        intel = {"price_action": {}, "coverage": {}, "standouts": [], "new_this_crawl": 0}
    _intel_cache["data"] = intel
    _intel_cache["ts"] = now
    return intel


def _cached_crawl_summary(force=False) -> list:
    now = time.time()
    if not force and _summary_cache["data"] is not None and (now - _summary_cache["ts"]) < _CACHE_TTL:
        return _summary_cache["data"]
    if _WEB_READONLY and not force:
        hydrate_caches()
        return _summary_cache["data"] or []
    full = get_crawl_summary(DB_PATH) or []
    _summary_cache["data"] = full
    _summary_cache["ts"] = now
    return full


def _cached_rarity_legend(force=False) -> list:
    """The Species page's rarity-tier legend — a full-catalog rarity computation
    (~1s locally, ~10s on the Postgres/0.5-CPU box) that was run uncached on every
    /species load. Only changes on a crawl, so cache it like the rest."""
    now = time.time()
    if not force and _rarity_legend_cache["data"] is not None and (now - _rarity_legend_cache["ts"]) < _CACHE_TTL:
        return _rarity_legend_cache["data"]
    if _WEB_READONLY and not force:
        hydrate_caches()
        return _rarity_legend_cache["data"] or []
    try:
        from analytics.market import rarity_tier_legend
        legend = rarity_tier_legend(DB_PATH)
    except Exception as e:
        logger.warning(f"rarity_tier_legend failed: {e}")
        legend = []
    _rarity_legend_cache["data"] = legend
    _rarity_legend_cache["ts"] = now
    return legend


def warm_caches():
    """Build the expensive dashboard caches once at startup so the first visitor
    doesn't pay the ~10s+ cold build (which on a small box can trip the health
    check). Meant to run in a background daemon thread from wsgi; every piece
    already guards its own errors, so a failure here just leaves a cold cache."""
    try:
        from vendors import REGISTRY
        snap = [l for l in get_snapshot() if l.get("vendor_key") in REGISTRY]
        _cached_movers(snap)
        _cached_intel(snap)
        _cached_crawl_summary()
        get_market_stats()
        logger.info("cache warm complete")
    except Exception as e:
        logger.warning(f"cache warm failed: {e}")


def spark_svg(series: list, w: int = 108, h: int = 26, color: str = "#2563eb") -> str:
    """Tiny inline sparkline SVG from a [[ymd, price], ...] series (cheapest per
    day). One point renders as a flat dashed hint; empty renders as a dash."""
    pts = [p for p in (series or []) if p and p[1] is not None]
    if not pts:
        return ('<svg width="%d" height="%d"></svg>' % (w, h))
    ys = [float(p[1]) for p in pts]
    lo, hi = min(ys), max(ys)
    pad = 3
    span = (hi - lo) or 1.0
    n = len(pts)
    def X(i):
        return pad + (0 if n < 2 else (i / (n - 1)) * (w - 2 * pad))
    def Y(v):
        return pad + (1 - (v - lo) / span) * (h - 2 * pad)
    if n == 1:
        y = h / 2
        return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
                f'<line x1="{pad}" y1="{y:.1f}" x2="{w-pad}" y2="{y:.1f}" '
                f'stroke="{color}" stroke-width="1.4" stroke-dasharray="3 3" opacity="0.5"/>'
                f'<circle cx="{w/2:.1f}" cy="{y:.1f}" r="2" fill="{color}"/></svg>')
    d = " ".join(("M" if i == 0 else "L") + f"{X(i):.1f} {Y(v):.1f}"
                 for i, v in enumerate(ys))
    last_up = ys[-1] >= ys[0]
    stroke = "#22c55e" if not last_up else "#ef4444"   # falling price = green (buyer-good)
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="1.5" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{X(n-1):.1f}" cy="{Y(ys[-1]):.1f}" r="2.2" fill="{stroke}"/></svg>')


def _hide_private() -> bool:
    """Whether to drop private-seller listings from a price view.

    Private sellers are ALWAYS hidden from logged-out visitors — that data is
    account-only. For a signed-in user, the cookie-backed sitewide toggle decides."""
    from auth import current_user
    if current_user() is None:
        return True
    return request.cookies.get("ft_hide_private") == "1"


def _apply_private_pref(listings: list) -> list:
    """Drop private-seller listings when the global toggle is on."""
    if _hide_private():
        return [l for l in listings if not l.get("is_private")]
    return listings


def _visible_to_user(listings: list) -> list:
    """PER-USER private-seller isolation — the security boundary. A private-seller
    listing is visible ONLY to the account that uploaded it; website/public
    listings are visible to everyone. Logged-out visitors and OTHER logged-in
    users never see someone else's private sellers (that would leak their sources
    and muddy the market view). Apply to every price view built from the shared
    snapshot: deals, species detail, collection valuation."""
    uid = current_user_id()
    return [l for l in listings
            if not l.get("is_private")
            or (uid is not None and l.get("private_owner") == uid)]


@app.context_processor
def inject_helpers():
    """Expose analytics presentation helpers to every template."""
    from analytics.market import rarity_tier
    return {"rarity_tier": rarity_tier, "spark_svg": spark_svg,
            "hide_private": _hide_private()}


@app.context_processor
def inject_theme():
    """Rarity colours come from ONE place: theme.py. base.html renders
    rarity_css() so no template ever hard-codes a rarity hex."""
    import theme
    return {"rarity_css": theme.rarity_css,
            "RARITY_TIERS": theme.RARITY_TIERS,
            "TIER_ORDER": theme.TIER_ORDER}


# Only these pages actually render the #species-datalist autocomplete. Injecting
# the full ~1k-species <option> list into EVERY response (login, privacy, etc.)
# bloated the DOM on every navigation for no reason.
_SPECIES_PICKER_ENDPOINTS = {"species_search", "alerts", "collection"}


@app.context_processor
def inject_all_species():
    """Species list for autocomplete datalists — only on pages that have one."""
    if request.endpoint not in _SPECIES_PICKER_ENDPOINTS:
        return {"all_species": []}
    try:
        return {"all_species": get_species_list(DB_PATH)}
    except Exception:
        return {"all_species": []}

# ── Settings file ─────────────────────────────────────────────────────────────
SETTINGS_PATH = Path("tracker_settings.json")

def load_settings() -> dict:
    defaults = {
        "dest_zip": "72712",
        "notify_email": "",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_pass": "",
        # From address must be on the VERIFIED sending domain (not the SMTP
        # username). Resend/others silently drop mail whose From isn't verified.
        "mail_from": "FangTrack <mike@fangtrack.com>",
        "auto_crawl": False,
        "crawl_schedule": "daily",
        "crawl_vendors": "all",
        "digest_path": "output/daily_digest.txt",
    }
    if SETTINGS_PATH.exists():
        try:
            saved = json.loads(SETTINGS_PATH.read_text())
            defaults.update(saved)
        except Exception:
            pass
    # Env vars win over the on-disk file so production (Render) keeps SMTP creds
    # out of the repo. Only override when the env var is actually set.
    _env_map = {
        "SMTP_HOST": "smtp_host", "SMTP_PORT": "smtp_port", "SMTP_USER": "smtp_user",
        "SMTP_PASS": "smtp_pass", "NOTIFY_EMAIL": "notify_email", "MAIL_FROM": "mail_from",
    }
    for env_key, skey in _env_map.items():
        val = os.environ.get(f"FANGTRACK_{env_key}") or os.environ.get(env_key)
        if val:
            defaults[skey] = int(val) if skey == "smtp_port" else val
    return defaults

def save_settings(data: dict):
    SETTINGS_PATH.write_text(json.dumps(data, indent=2))

# ── Crawl state ───────────────────────────────────────────────────────────────
_CRAWL_STATE_FILE = Path("logs/crawl_state.json")


def _load_crawl_state() -> dict:
    """Restore last-crawl status across restarts; never restore a stuck 'running'."""
    base = {"running": False, "vendor": "", "started": None, "finished": None,
            "just_finished": False, "last_hits": []}
    try:
        if _CRAWL_STATE_FILE.exists():
            saved = json.loads(_CRAWL_STATE_FILE.read_text(encoding="utf-8"))
            base.update(saved)
            base["running"] = False          # a restart means no crawl is live
            base["just_finished"] = False
    except Exception:
        pass
    return base


def _save_crawl_state():
    try:
        _CRAWL_STATE_FILE.parent.mkdir(exist_ok=True)
        _CRAWL_STATE_FILE.write_text(json.dumps(_crawl_state, default=str), encoding="utf-8")
    except Exception:
        pass


_crawl_state = _load_crawl_state()

# ── Snapshot cache (rebuilt after each crawl) ─────────────────────────────────
_snapshot_cache = {"data": None, "ts": 0}
# The snapshot is expensive to build (rarity + trends + fire-deals over ~75k rows)
# and only changes on the daily crawl, so we cache it for a long time. The crawl
# force-refreshes via get_snapshot(force=True); between crawls nothing changes, so
# serving up-to-an-hour-stale data is fine and keeps the free tier responsive.
_CACHE_TTL = 3600  # seconds (1 hour)
# Serialize the (expensive) recompute so a cold cache hit by N gunicorn threads at
# once triggers ONE build, not N simultaneous ones that thrash the free tier.
_snapshot_lock = threading.Lock()

def get_owned_keys(db_path=DB_PATH, user_id=None) -> set:
    """Species_keys owned. `user_id=None` = global (background crawl/digest); pass a
    specific id for per-user marks. Web routes should use `_req_owned()` so anonymous
    visitors see nothing."""
    conn = get_connection(db_path)
    try:
        if user_id is None:
            rows = conn.execute("SELECT DISTINCT species_key FROM collection").fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT species_key FROM collection WHERE user_id=?", (user_id,)).fetchall()
        return {r["species_key"] for r in rows}
    except Exception:
        return set()
    finally:
        conn.close()


def _req_owned() -> set:
    """Owned-species set for the current request: the logged-in user's collection,
    or empty for anonymous visitors."""
    uid = current_user_id()
    return get_owned_keys(DB_PATH, user_id=uid) if uid else set()


def get_snapshot(force=False) -> list:
    now = time.time()
    if not force and _snapshot_cache["data"] and (now - _snapshot_cache["ts"]) < _CACHE_TTL:
        return _snapshot_cache["data"]

    # Hosted web: never build on a request — load the cron-built blob and serve
    # that (or empty if the cron hasn't populated it yet). Building here would jam
    # the health check and restart-loop the instance.
    if _WEB_READONLY and not force:
        hydrate_caches()
        return _snapshot_cache["data"] or []

    # Only one thread builds the snapshot at a time. Whoever loses the race waits
    # here, then finds the fresh cache on the re-check below instead of rebuilding.
    with _snapshot_lock:
        now = time.time()
        if not force and _snapshot_cache["data"] and (now - _snapshot_cache["ts"]) < _CACHE_TTL:
            return _snapshot_cache["data"]
        return _build_snapshot(now)


def _build_snapshot(now: float) -> list:
    conn = get_connection(DB_PATH)
    cur = conn.cursor()
    # Pick, per vendor, the newest run that ISN'T truncated. A truncated run
    # (pagination cut short by a 429/timeout) under-counts, so we fall back to
    # the vendor's last good run rather than let a bad crawl shrink the market.
    # Only if a vendor has no good run at all do we use its newest truncated one.
    cur.execute("""
        SELECT id, vendor_key, COALESCE(truncated, 0) AS truncated
        FROM crawl_runs WHERE status IN ('complete','partial')
        ORDER BY id
    """)
    good, any_run = {}, {}
    for r in cur.fetchall():
        vk = r["vendor_key"]
        any_run[vk] = r["id"]                       # newest overall (rows are id-ordered)
        if not r["truncated"]:
            good[vk] = r["id"]                      # newest good
    latest_runs = {vk: good.get(vk, any_run[vk]) for vk in any_run}
    if not latest_runs:
        conn.close()
        return []
    phs = ",".join("?"*len(latest_runs))
    cur.execute(f"""
        SELECT * FROM price_history
        WHERE crawl_run_id IN ({phs}) AND availability != 'out_of_stock'
        ORDER BY scientific_name_key, sex, price_usd
    """, list(latest_runs.values()))
    snapshot = [dict(r) for r in cur.fetchall()]
    conn.close()

    if snapshot:
        # Human-confirmed vendor source policies outrank the scraped ones.
        from normalize.source_type import set_confirmed_policies
        set_confirmed_policies(get_vendor_policies(DB_PATH))
        annotate_source_types(snapshot)
        from normalize.common_names import enrich_listings_with_common_names
        enrich_listings_with_common_names(snapshot)
        populate_historical_lows(snapshot, DB_PATH)
        lows = get_all_historical_lows(DB_PATH)
        rate_all(snapshot, lows)
        shipping = get_all_shipping(DB_PATH)
        compute_fire_deals(snapshot, shipping, db_path=DB_PATH)
        rarity_data = compute_all_rarity(DB_PATH)
        annotate_listings_with_rarity(snapshot, DB_PATH)
        scr = compute_size_class_rarity(DB_PATH)
        annotate_with_size_class_rarity(snapshot, scr)
        annotate_with_trends(snapshot, DB_PATH)

    # Annotate with vendor homepages for Buy links
    for l in snapshot:
        l["vendor_homepage"] = _vendor_homepage(l.get("vendor_key", ""))

    # NOTE: "owned" is per-user and MUST NOT be baked into this shared/cached
    # snapshot — doing so leaked the admin's collection checkmarks to every visitor
    # (incl. logged-out). Routes pass `owned_keys=_req_owned()` to the template and
    # check membership per request instead (empty for anonymous visitors).

    # Flag private-seller listings + their owner so the per-user visibility filter
    # (_visible_to_user) can hide a private seller from everyone except the account
    # that uploaded it. private_owner is None for website vendors.
    private = get_private_seller_keys(DB_PATH)
    owners = get_private_owner_map(DB_PATH)
    for l in snapshot:
        vk = l.get("vendor_key")
        l["is_private"] = vk in private
        l["private_owner"] = owners.get(vk)

    # ── Deal codes + free shipping (native, first-class) ────────────────────
    # Attach the vendor's best active discount code and its "with code" price,
    # plus the free-shipping threshold, to every listing.
    from database.db import get_active_discount_codes
    codes_by_vendor = get_active_discount_codes(DB_PATH)
    shipping = get_all_shipping(DB_PATH)
    _SALE_LABELS = {"SITEWIDE SALE": "SALE", "HOLIDAY SALE": "HOLIDAY", "BOGO": "BOGO"}
    for l in snapshot:
        vk = l.get("vendor_key", "")
        price = l.get("price_usd") or 0
        codes = codes_by_vendor.get(vk, [])
        best = _best_discount(codes, price)
        if best:
            l["discount_code"] = best["code"]
            l["discount_type"] = best["discount_type"]
            l["discount_value"] = best["discount_value"]
            l["discount_verified"] = bool(best.get("is_verified"))
            l["price_with_code"] = _apply_discount(price, best)
        else:
            l["discount_code"] = None
            l["price_with_code"] = None
        # Sitewide/holiday/BOGO sale flag — an event, distinct from a per-order code.
        sale = next((c for c in codes
                     if (c.get("code") or "").upper() in _SALE_LABELS), None)
        if sale:
            l["sale_label"] = _SALE_LABELS[sale["code"].upper()]
            pct = sale.get("discount_value")
            l["sale_pct"] = int(pct) if pct and sale.get("code", "").upper() != "BOGO" else None
        else:
            l["sale_label"] = None
        ship = shipping.get(vk) or {}
        l["free_ship_threshold"] = ship.get("free_threshold")

    _snapshot_cache["data"] = snapshot
    _snapshot_cache["ts"] = now
    return snapshot


def _ensure_vendor_policy_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS vendor_source_policy (
        vendor_key TEXT PRIMARY KEY,
        policy     TEXT,               -- 'CB' | 'WC' | '' (mixed/unknown)
        note       TEXT,               -- how it was confirmed
        updated_at TEXT
    )""")


def get_vendor_policies(db_path=DB_PATH) -> dict:
    """Human-confirmed vendor source policies: {vendor_key: 'CB'|'WC'}."""
    try:
        conn = get_connection(db_path)
        _ensure_vendor_policy_table(conn)
        rows = conn.execute(
            "SELECT vendor_key, policy FROM vendor_source_policy WHERE policy != ''"
        ).fetchall()
        conn.close()
        return {r["vendor_key"]: r["policy"] for r in rows}
    except Exception:
        return {}


def get_vendor_policy_rows(db_path=DB_PATH) -> dict:
    """Full rows (policy + note) for the admin screen."""
    try:
        conn = get_connection(db_path)
        _ensure_vendor_policy_table(conn)
        rows = [dict(r) for r in conn.execute("SELECT * FROM vendor_source_policy")]
        conn.close()
        return {r["vendor_key"]: r for r in rows}
    except Exception:
        return {}


@app.route("/admin/vendor-policy", methods=["POST"])
@admin_required
def admin_vendor_policy():
    """Record a HUMAN-CONFIRMED source policy for a vendor (e.g. 'I asked Fear
    Not — they are captive-bred only'). Outranks anything we scraped."""
    vk = (request.form.get("vendor_key") or "").strip()
    policy = (request.form.get("policy") or "").strip().upper()
    note = (request.form.get("note") or "").strip()
    if policy not in ("CB", "WC", ""):
        policy = ""
    if vk:
        conn = get_connection(DB_PATH)
        _ensure_vendor_policy_table(conn)
        conn.execute("""INSERT INTO vendor_source_policy (vendor_key, policy, note, updated_at)
                        VALUES (?,?,?,?)
                        ON CONFLICT(vendor_key) DO UPDATE SET
                          policy=excluded.policy, note=excluded.note,
                          updated_at=excluded.updated_at""",
                     (vk, policy, note, datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        conn.close()
        _snapshot_cache["data"] = None      # force re-annotation
        flash(f"Source policy for {vk} set to {policy or 'mixed/unknown'}", "success")
    return redirect(request.referrer or url_for("vendors_admin"))


def _page_base() -> str:
    """URL prefix for pagination links: current path + all query args EXCEPT
    'page', ending so the pager can append 'page=N'. Works for any route."""
    from urllib.parse import urlencode
    args = request.args.to_dict()
    args.pop("page", None)
    base = request.path + "?" + urlencode(args)
    return base + "&" if args else base


def _attach_clean_names(listings: list) -> None:
    """Attach the canonical, standardized display name to each listing dict:
      sci_display  → "Genus species" / "Genus sp. 'Descriptor'" (clean, cased)
      common_clean → best curated/harvested common name
      wiki_url     → Wikipedia link for the clean binomial
    Used by Deals and Market Movers so both read identically no matter how messy
    the vendor's raw title was. The row still links via scientific_name_key."""
    from normalize.species_canonical import _display_from_key
    from normalize.common_names_map import best_common
    for l in listings:
        k = l.get("scientific_name_key") or ""
        disp = _display_from_key(k) or (l.get("scientific_name") or k).title()
        l["sci_display"] = disp
        l["common_clean"] = best_common(k, l.get("common_name") or "")
        slug = disp.replace("'", "").replace(".", "").replace(" ", "_")
        l["wiki_url"] = "https://en.wikipedia.org/wiki/" + slug


def _apply_discount(price: float, code: dict) -> float:
    """Price after applying a discount code."""
    if not price or not code:
        return price
    dt = (code.get("discount_type") or "pct").lower()
    val = code.get("discount_value") or 0
    if dt in ("pct", "percent", "%"):
        return round(price * (1 - val / 100.0), 2)
    return round(max(0.0, price - val), 2)   # flat $ off


def _best_discount(codes: list, price: float):
    """Pick the code giving the biggest saving on this price (respecting min_order)."""
    best, best_saving = None, 0.0
    for c in codes:
        if c.get("min_order") and price < c["min_order"]:
            continue
        saving = price - _apply_discount(price, c)
        if saving > best_saving:
            best, best_saving = c, saving
    return best


def get_private_seller_keys(db_path=DB_PATH) -> set:
    """Vendor keys that are private-seller uploads (i.e. NOT website scrapers).

    Robust definition: any vendor that isn't in the website crawler REGISTRY is
    a private/manual upload — so a stray platform value ('wholesale', etc.) can't
    make an imported list leak into the 'Websites only' view.
    """
    try:
        from vendors import REGISTRY
        website = set(REGISTRY.keys())
        conn = get_connection(db_path)
        rows = conn.execute("SELECT DISTINCT vendor_key FROM price_history").fetchall()
        by_platform = conn.execute(
            "SELECT vendor_key FROM vendors WHERE platform = 'private_seller'").fetchall()
        conn.close()
        keys = {r["vendor_key"] for r in rows if r["vendor_key"] not in website}
        keys |= {r["vendor_key"] for r in by_platform}
        return keys
    except Exception:
        return set()


def get_private_owner_map(db_path=DB_PATH) -> dict:
    """{vendor_key: owner_user_id} for every private-seller upload. Drives the
    per-user visibility filter: a private seller is shown ONLY to the account
    that uploaded it. A NULL owner (legacy import not yet claimed) stays hidden
    from everyone until the migration assigns it."""
    try:
        conn = get_connection(db_path)
        rows = conn.execute(
            "SELECT vendor_key, user_id FROM vendors WHERE platform='private_seller'").fetchall()
        conn.close()
        return {r["vendor_key"]: r["user_id"] for r in rows}
    except Exception:
        return {}


# Cached canonical species catalog (drives search, dropdown, browse tiles).
_species_cache = {"data": None, "ts": 0}


def _display_from_key(key: str) -> str:
    """'theraphosa blondi' -> 'Theraphosa blondi'; 'cyriopagopus sp hati' ->
    'Cyriopagopus sp. \\'Hati\\''."""
    parts = (key or "").split()
    if not parts:
        return key
    if len(parts) >= 2 and parts[1] == "sp":
        desc = " ".join(parts[2:])
        return parts[0].capitalize() + " sp." + (f" '{desc.title()}'" if desc else "")
    return " ".join([parts[0].capitalize()] + parts[1:])


def get_species_catalog(db_path=DB_PATH, force=False) -> list:
    """Every canonical species in the system: {key, display, common, n, min_p}.
    force=True rebuilds from the DB even under _WEB_READONLY — needed so an
    in-process (admin 'Run Crawl') warm_and_persist actually refreshes this blob
    instead of re-persisting the stale hydrated copy."""
    now = time.time()
    if not force and _species_cache["data"] and (now - _species_cache["ts"]) < _CACHE_TTL:
        return _species_cache["data"]
    if _WEB_READONLY and not force:
        hydrate_caches()
        return _species_cache["data"] or []
    from normalize.livestock import GENUS_SET
    from normalize.common_names_map import pick_common
    cat = []
    try:
        conn = get_connection(db_path)
        # WEBSITE-ONLY catalog: private-seller lists must NOT create species pages
        # (Mike's rule) — a private-only species (e.g. a seller's misspelled "sp.")
        # became a browse card that 404'd for everyone but the uploader, and leaked
        # private sourcing into the public catalog. Exclude platform='private_seller'
        # so the catalog is the website market only. Private listings still show to
        # their owner on /deals + collection, mapped to the nearest real species.
        rows = conn.execute("""
            SELECT scientific_name_key AS k,
                   GROUP_CONCAT(DISTINCT common_name) AS commons,
                   COUNT(*) AS n, MIN(price_usd) AS min_p
            FROM price_history
            WHERE price_usd > 0 AND scientific_name_key IS NOT NULL
              AND vendor_key NOT IN (SELECT vendor_key FROM vendors
                                     WHERE platform='private_seller')
            GROUP BY scientific_name_key
        """).fetchall()
        conn.close()
        for r in rows:
            key = r["k"] or ""
            toks = key.split()
            # only clean canonical keys (genus is a known invert genus)
            if not toks or toks[0] not in GENUS_SET:
                continue
            commons = (r["commons"] or "").split(",")
            cat.append({
                "key": key,
                "display": _display_from_key(key),
                "common": pick_common(key, commons),
                "n": r["n"], "min_p": r["min_p"],
            })
    except Exception:
        pass
    cat.sort(key=lambda s: s["display"].lower())
    _species_cache["data"] = cat
    _species_cache["ts"] = now
    return cat


def get_species_list(db_path=DB_PATH) -> list:
    """Autocomplete options: 'Genus species (Common)' for every species.
    LEGACY — the native <datalist>. Superseded by the /api/species/suggest
    combobox (kept only for any callers still reading the flat list)."""
    return [f"{s['display']} ({s['common']})" if s["common"] else s["display"]
            for s in get_species_catalog(db_path)]


# ── Species typeahead (combobox suggest API) ────────────────────────────────
# Replaces the native <datalist> whose option value was the whole
# "Genus species (Common)" string — which the substring search could never
# match. Here the client renders rich rows and selects the STABLE key, so a
# pick always resolves to a real species page (no more "returns no result").
_syn_index_cache = {"data": None}


def _species_synonym_index() -> dict:
    """canonical_key -> {junior-synonym / misspelling phrases} from key_aliases,
    so a query typed as a bad/old name still surfaces the canonical species."""
    if _syn_index_cache["data"] is None:
        idx: dict[str, set] = {}
        try:
            from normalize.key_aliases import KEY_ALIASES
            for bad, good in KEY_ALIASES.items():
                idx.setdefault(good, set()).add(bad.lower())
        except Exception:
            pass
        _syn_index_cache["data"] = idx
    return _syn_index_cache["data"]


def _score_species(q: str, s: dict, aliases) -> int:
    """Rank one catalog entry against query q. Higher = better; 0 = no match.
    Token-prefix aware: every whitespace token in q must prefix some word in the
    field — so 'poecil metal' matches 'Poecilotheria metallica' and 'gram pulc'
    matches 'Grammostola pulchra'. exact(100) > full-prefix(90) > all-tokens-lead
    (80) > all-tokens(66) > contains(55) > fuzzy(≤45)."""
    from difflib import SequenceMatcher
    fields = [(s.get("display") or "").lower(), (s.get("common") or "").lower(),
              (s.get("key") or "")] + list(aliases or ())
    qtokens = q.split()
    best = 0
    for f in fields:
        if not f:
            continue
        if f == q:
            best = max(best, 100); continue
        if f.startswith(q):
            best = max(best, 90); continue
        fwords = f.split()
        if qtokens and all(any(w.startswith(t) for w in fwords) for t in qtokens):
            lead = bool(fwords) and fwords[0].startswith(qtokens[0])
            best = max(best, 80 if lead else 66); continue
        if q in f:
            best = max(best, 55); continue
        if len(q) >= 4:
            r = SequenceMatcher(None, q, f).ratio()
            if r >= 0.72:
                best = max(best, int(r * 45))
    return best


@app.route("/api/species/suggest")
def api_species_suggest():
    """Typeahead suggestions: ranked, synonym-aware, one row per canonical
    species. Returns [{key, sci, common, n, live, url}] (top 10)."""
    from urllib.parse import quote
    q = (request.args.get("q") or "").strip().lower()
    if len(q) < 2:
        return jsonify([])
    syn = _species_synonym_index()
    scored = []
    for s in get_species_browse():
        sc = _score_species(q, s, syn.get(s.get("key", ""), ()))
        if sc:
            # tie-break: score, then more live listings, then more history, then A–Z
            scored.append((-sc, -(s.get("live") or 0), -(s.get("n") or 0),
                           (s.get("display") or "").lower(), s))
    scored.sort(key=lambda t: t[:4])
    out = [{"key": s["key"], "sci": s["display"], "common": s.get("common") or "",
            "n": s.get("n") or 0, "live": s.get("live") or 0,
            "url": f"/species/{quote(s['key'])}"}
           for *_, s in scored[:10]]
    return jsonify(out)


# Enriched browse catalog (facets + market stats + rarity) — cached.
_browse_cache = {"data": None, "ts": 0}


def get_species_browse(db_path=DB_PATH, force=False) -> list:
    """Catalog enriched with facet fields (genus, origin, care, price band,
    rarity tier) + market stats (sparkline, market price, trend) for the
    faceted Species browse and its tiles. force=True rebuilds under _WEB_READONLY
    (see get_species_catalog)."""
    now = time.time()
    if not force and _browse_cache["data"] and (now - _browse_cache["ts"]) < _CACHE_TTL:
        return _browse_cache["data"]
    if _WEB_READONLY and not force:
        hydrate_caches()
        return _browse_cache["data"] or []
    from normalize.genus_meta import origin, price_band
    from normalize.traits import traits_for
    stats = get_market_stats()
    out = []
    for s in get_species_catalog(db_path, force=force):
        key = s["key"]
        genus = key.split()[0] if key.split() else ""
        st = stats.get(key) or {}
        tr = traits_for(key) or {}
        out.append({**s,
                    "genus": genus.capitalize(),
                    "origin": origin(genus),
                    "hemisphere": tr.get("hemisphere") or "",
                    "habitat":    tr.get("habitat") or "",
                    "t_size":     tr.get("size") or "",
                    "temperament":tr.get("temperament") or "",
                    "experience": tr.get("experience") or "",
                    "climate":    tr.get("climate") or "",
                    "price_band": price_band(s.get("min_p")),
                    "rarity_score": st.get("rarity_score"),
                    "rarity_tier": st.get("rarity_tier") or "",
                    "rarity_class": st.get("rarity_class") or "",
                    "market_price": st.get("market_price"),
                    "lowest_ask": st.get("lowest_ask"),
                    "trend": st.get("trend"),
                    "trend_pct": st.get("trend_pct"),
                    "vendors_live": st.get("vendors_live"),
                    "live": st.get("listings_live_now") or 0,  # in-stock count now
                    "spark": st.get("spark") or []})
    _browse_cache["data"] = out
    _browse_cache["ts"] = now
    return out


# ── Persisted cache blobs (built by the cron, loaded by the web) ─────────────
# The dashboard/species builds are CPU+DB-heavy (~130s cold on the hosted Postgres)
# and jam the single web worker's health check when run on a request. So the CRON
# builds these caches and persists them here as JSON; the WEB loads them (fast) and
# never builds on the request path (see _WEB_READONLY + hydrate_caches).
_CACHE_REGISTRY = {
    "snapshot":      _snapshot_cache,
    "market_stats":  _market_cache,
    "movers":        _movers_cache,
    "intel":         _intel_cache,
    "summary":       _summary_cache,
    "rarity_legend": _rarity_legend_cache,
    "species":       _species_cache,
    "browse":        _browse_cache,
}
_hydrated = {"ts": 0}
_HYDRATE_TTL = 300   # re-pull the blobs from the DB at most every 5 min


def _ensure_cache_blob_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS cache_blob (
        name TEXT PRIMARY KEY, payload TEXT, built_at TEXT)""")


def persist_caches():
    """Write every populated in-memory cache to cache_blob (called by the cron after
    a force-build). JSON so the web can load it cheaply."""
    conn = get_connection(DB_PATH)
    try:
        _ensure_cache_blob_table(conn)
        stamp = datetime.now().isoformat()
        for name, cache in _CACHE_REGISTRY.items():
            if cache.get("data") is None:
                continue
            payload = json.dumps(cache["data"], default=str)
            # Portable upsert. Must use ON CONFLICT (not DELETE+INSERT): the pg
            # adapter auto-appends "RETURNING id" to a plain INSERT to emulate
            # lastrowid, but cache_blob has no id column → "column id does not
            # exist". The adapter skips RETURNING when the SQL has ON CONFLICT.
            conn.execute(
                "INSERT INTO cache_blob (name, payload, built_at) VALUES (?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET payload=excluded.payload, "
                "built_at=excluded.built_at",
                (name, payload, stamp))
        conn.commit()
        logger.info("persist_caches: wrote %d cache blob(s)",
                    sum(1 for c in _CACHE_REGISTRY.values() if c.get("data") is not None))
    finally:
        conn.close()


def hydrate_caches(force=False):
    """Load the cron-built blobs into the in-memory caches. Cheap (one SELECT +
    json.loads); throttled so we re-read the DB at most every _HYDRATE_TTL so a
    fresh crawl's data is picked up without hammering the DB each request."""
    now = time.time()
    if not force and (now - _hydrated["ts"]) < _HYDRATE_TTL:
        return
    _hydrated["ts"] = now
    try:
        conn = get_connection(DB_PATH)
        try:
            _ensure_cache_blob_table(conn)
            rows = conn.execute("SELECT name, payload FROM cache_blob").fetchall()
        finally:
            conn.close()
        for r in rows:
            cache = _CACHE_REGISTRY.get(r["name"])
            if cache is not None:
                cache["data"] = json.loads(r["payload"])
                cache["ts"] = now
    except Exception as e:
        logger.warning(f"cache hydrate failed: {e}")


def warm_and_persist():
    """CRON entrypoint: build every dashboard/species cache from current DB data and
    persist the blobs for the web to load. Runs in the (non-health-checked) cron
    process, so the heavy build is fine here. Idempotent."""
    from vendors import REGISTRY
    snap = [l for l in get_snapshot(force=True) if l.get("vendor_key") in REGISTRY]
    get_market_stats(force=True)
    _cached_movers(snap, force=True)
    _cached_intel(snap, force=True)
    _cached_crawl_summary(force=True)
    _cached_rarity_legend(force=True)
    get_species_catalog(force=True)   # force → rebuilds even on an in-process
    get_species_browse(force=True)    # (web) Run Crawl, not just the cron
    persist_caches()
    logger.info("warm_and_persist: all dashboard caches built + persisted")


def _apply_key_aliases(db_path=DB_PATH) -> int:
    """Collapse fragmented / misspelled / truncated species keys onto their
    canonical form across price_history — PORTABLE (uses the pg adapter, unlike
    tools/migrate_key_aliases.py which is raw sqlite3). canonicalize_key already
    runs on each NEW row via db.record; this fixes accumulated HISTORICAL rows so
    the search dropdown shows ONE entry per species (e.g. the 3 'Dominican Purple'
    fragments collapse to one). Run after every crawl."""
    from normalize.key_aliases import canonicalize_key
    conn = get_connection(db_path)
    changed = 0
    try:
        keys = [r["scientific_name_key"] for r in conn.execute(
            "SELECT DISTINCT scientific_name_key FROM price_history "
            "WHERE scientific_name_key IS NOT NULL AND scientific_name_key<>''")]
        for k in keys:
            ck = canonicalize_key(k)
            if ck != k:
                conn.execute("UPDATE price_history SET scientific_name_key=? "
                             "WHERE scientific_name_key=?", (ck, k))
                changed += 1
        conn.commit()
    except Exception as e:
        logger.warning(f"_apply_key_aliases failed: {e}")
    finally:
        conn.close()
    return changed


def run_crawl_thread(vendor_keys: list[str]):
    """Run crawler in background thread."""
    global _crawl_state
    import crawl_lock
    # Re-entrancy backstop: never start if a crawl (any origin) is already active.
    if crawl_lock.is_active():
        logger.info("Crawl already running — run_crawl_thread aborting.")
        return
    crawl_lock.acquire("app")
    try:
        from tools.backup_db import make_backup
        make_backup()            # rolling pre-crawl snapshot (no-op on Postgres)
    except Exception as e:
        logger.warning(f"Pre-crawl backup skipped: {e}")
    _crawl_state.update({"running": True, "started": datetime.now().isoformat(),
                          "just_finished": False, "last_hits": []})

    try:
        import asyncio
        from vendors import REGISTRY

        # ── Parallel crawl ──────────────────────────────────────────────────
        # Different vendors are crawled concurrently (crawl etiquette is
        # per-vendor: each scraper still throttles ≥2s between its OWN requests,
        # so hitting many different sites at once is polite). A semaphore caps
        # concurrency; DB writes happen once at the end, so no SQLite contention.
        keys = [vk for vk in vendor_keys if vk in REGISTRY]
        total = len(keys)
        _crawl_state["done"] = 0
        _crawl_state["total"] = total
        CONCURRENCY = 8

        async def _crawl_all():
            sem = asyncio.Semaphore(CONCURRENCY)
            results = []

            async def one(vk):
                async with sem:
                    _crawl_state["vendor"] = vk
                    try:
                        scraper = REGISTRY[vk]()
                        res = await asyncio.wait_for(scraper.scrape(), timeout=1800)
                        if res.listings:
                            logger.info(f"[{vk}] {len(res.listings)} listings"
                                        + (" (TRUNCATED)" if getattr(res, "truncated", False) else ""))
                            st = res.started_at.isoformat() if getattr(res, "started_at", None) else None
                            fin = res.finished_at.isoformat() if getattr(res, "finished_at", None) else None
                            return (vk, scraper.VENDOR_NAME, res.listings, st, fin,
                                    getattr(res, "truncated", False))
                    except asyncio.TimeoutError:
                        logger.error(f"[{vk}] Crawl timed out after 30 min — skipped")
                    except Exception as e:
                        logger.error(f"[{vk}] Crawl error: {e}")
                    finally:
                        _crawl_state["done"] = _crawl_state.get("done", 0) + 1
                    return None

            for coro in asyncio.as_completed([one(vk) for vk in keys]):
                r = await coro
                if r:
                    results.append(r)
            return results

        all_results = asyncio.run(_crawl_all())

        # Refresh discount codes + shipping in the background of the crawl so
        # sale codes (incl. sitewide Black-Friday style promos) stay current —
        # deal codes are a first-class signal, captured every crawl.
        try:
            from vendors.discount_scraper import scan_all, seed_known_codes
            seed_known_codes(DB_PATH)
            asyncio.run(scan_all(DB_PATH))
        except Exception as e:
            logger.warning(f"Discount scan skipped: {e}")

        if all_results:
            from pipeline import run_multi_vendor_pipeline
            run_multi_vendor_pipeline(all_results, db_path=DB_PATH)

        # Collapse fragmented species keys onto their canonical form so the catalog
        # / search dropdown shows ONE entry per species (self-heals on every crawl).
        try:
            n = _apply_key_aliases(DB_PATH)
            if n:
                logger.info(f"key-alias pass: collapsed {n} fragmented species keys")
        except Exception as e:
            logger.warning(f"key-alias pass skipped: {e}")

        # Rebuild snapshot and check watchlist
        _snapshot_cache["data"] = None  # invalidate cache
        _market_cache["data"] = None
        _species_cache["data"] = None
        _browse_cache["data"] = None
        _movers_cache["data"] = None
        _intel_cache["data"] = None
        _summary_cache["data"] = None
        _rarity_legend_cache["data"] = None
        snap = get_snapshot(force=True)
        get_market_stats(force=True)
        # Rebuild + persist the rest of the dashboard caches so the read-only web
        # (and future boots) load fresh blobs instead of stale ones.
        try:
            warm_and_persist()
        except Exception as e:
            logger.warning(f"warm_and_persist after crawl skipped: {e}")
        init_watchlist_tables(DB_PATH)
        hits = check_watchlist(snap, DB_PATH)
        owned_keys = get_owned_keys(DB_PATH)
        _crawl_state["last_hits"] = [
            {
                "target": h.target_display,
                "vendor": h.vendor_key,
                "name":   h.scientific_name,
                "size":   h.size_text,
                "sex":    h.sex,
                "price":  h.price_usd,
                "landed": h.landed_cost,
                "rating": h.deal_rating,
                "rarity": h.rarity_score,
                "fire":   h.is_fire_deal,
                "owned":  normalize_species_key(h.scientific_name) in owned_keys,
            }
            for h in hits
        ]

        # Write digest
        _write_digest(snap, hits)

        # Evaluate alerts (price drops / back-in-stock / fire / saved searches)
        try:
            from analytics.alerts import evaluate_and_record
            new_alerts = evaluate_and_record(snap, DB_PATH, load_settings())
            if new_alerts:
                logger.info(f"{len(new_alerts)} new alert(s) recorded")
        except Exception as e:
            logger.warning(f"Alert evaluation skipped: {e}")

    except Exception as e:
        logger.error(f"Crawl thread error: {e}")
    finally:
        # Speed report — computed from crawl_runs so it's always available after a crawl.
        try:
            from crawl_report import get_speed_report, format_speed_report
            rep = get_speed_report(DB_PATH)
            _crawl_state["speed"] = rep
            if rep:
                logger.info("\n" + format_speed_report(rep))
        except Exception as e:
            logger.warning(f"Speed report skipped: {e}")
        crawl_lock.release()
        _crawl_state.update({
            "running": False,
            "vendor": "",
            "finished": datetime.now().isoformat(),
            "just_finished": True,
        })
        _save_crawl_state()
        time.sleep(5)
        _crawl_state["just_finished"] = False


def _start_daily_crawl_scheduler():
    """Optional in-process daily crawl. Enabled by FANGTRACK_DAILY_CRAWL_HOUR (0-23 UTC).
    Uses a date marker + the cross-process crawl lock so it fires once/day even across
    multiple gunicorn workers. Best with an always-on plan (an idle instance won't wake).

    ONLY for the single-service SQLite-on-a-disk deployment. On the hosted Postgres
    topology the daily crawl is a dedicated Render cron worker (render.yaml); running an
    all-vendor crawl inside the 1-CPU/2GB web process spikes memory + saturates the CPU and
    flaps the health check → Render restart (prod outage 2026-07-20). So we hard-refuse to
    arm whenever DATABASE_URL is present, even if the hour env var got set by mistake.
    Returns a short status string (for logging/tests); the value is otherwise unused."""
    raw = os.environ.get("FANGTRACK_DAILY_CRAWL_HOUR")
    if raw is None:
        return "off"
    if os.environ.get("DATABASE_URL"):
        logger.warning(
            "FANGTRACK_DAILY_CRAWL_HOUR is set but DATABASE_URL is present — refusing to "
            "crawl inside the web process (a dedicated cron worker handles the daily crawl). "
            "Unset FANGTRACK_DAILY_CRAWL_HOUR on the web service to silence this.")
        return "refused-postgres"
    try:
        target_hour = int(raw)
    except ValueError:
        logger.warning("FANGTRACK_DAILY_CRAWL_HOUR must be 0-23; scheduler off.")
        return "invalid"
    import crawl_lock
    marker = Path("logs/.last_daily_crawl")

    def _loop():
        while True:
            try:
                now = datetime.utcnow()
                today = now.strftime("%Y-%m-%d")
                last = marker.read_text().strip() if marker.exists() else ""
                if now.hour == target_hour and last != today and not crawl_lock.is_active():
                    marker.parent.mkdir(exist_ok=True)
                    marker.write_text(today)      # claim the day before crawling (multi-worker guard)
                    from vendors import REGISTRY
                    logger.info(f"In-process daily crawl firing (hour {target_hour} UTC)")
                    run_crawl_thread(list(REGISTRY.keys()))
            except Exception as e:
                logger.warning(f"daily crawl scheduler: {e}")
            time.sleep(300)   # check every 5 minutes

    threading.Thread(target=_loop, daemon=True).start()
    logger.info(f"Daily crawl scheduler armed for {target_hour}:00 UTC")
    return "armed"


_start_daily_crawl_scheduler()


def _write_digest(snapshot: list, hits: list):
    owned_keys = get_owned_keys(DB_PATH)
    """Write a human-readable daily digest file."""
    settings = load_settings()
    out_path = Path(settings.get("digest_path", "output/daily_digest.txt"))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"Tarantula Market Tracker — Digest",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"{'='*60}",
        f"WATCHLIST HITS ({len(hits)})",
        f"{'='*60}",
    ]
    if hits:
        for h in hits:
            badges = []
            if h.is_fire_deal: badges.append("🔥")
            if h.deal_rating == "💎💎": badges.append("💎💎")
            elif h.deal_rating == "💎": badges.append("💎")
            rstr = f"Rarity {h.rarity_score}/10 " if h.rarity_score else ""
            lstr = f"${h.landed_cost:.2f} shipped" if h.landed_cost else ""
            lines += [
                f"",
                f"🎯 {h.target_display}",
                f"   {h.scientific_name}  {h.size_text or '?'}\"  sex={h.sex or '?'}",
                f"   ${h.price_usd:.2f}  {lstr}  @{h.vendor_key}  {' '.join(badges)}  {rstr}",
                *(["   ✓ YOU ALREADY OWN THIS SPECIES"] if normalize_species_key(h.scientific_name) in owned_keys else []),
            ]
    else:
        lines.append("No watchlist hits this crawl.")

    fire_deals = [l for l in snapshot if l.get("is_fire_deal")]
    gem2_deals = [l for l in snapshot if l.get("deal_rating") == "💎💎" and not l.get("is_fire_deal")]
    lines += [
        f"",
        f"{'='*60}",
        f"TOP DEALS",
        f"{'='*60}",
        f"🔥 All-time lowest shipped price: {len(fire_deals)}",
        f"💎💎 Exceptional deals: {len(gem2_deals)}",
        f"",
    ]
    top = sorted(fire_deals + gem2_deals,
                 key=lambda l: l.get("price_usd",9999))[:15]
    for l in top:
        fire = "🔥" if l.get("is_fire_deal") else "💎💎"
        rarity = l.get("size_class_rarity_score") or l.get("rarity_score") or "?"
        lines.append(f"  {fire}  ${l['price_usd']:.2f}  {l['scientific_name'][:35]}  "
                     f"{l.get('size_text','?')}\"  {l.get('sex','U')}  "
                     f"@{l['vendor_key']}  [{rarity}/10]")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Digest written to {out_path}")

    # Optional email — branded watchlist digest (hyperlinked names + unsubscribe),
    # falls back to the plain-text digest if branded rendering fails.
    settings = load_settings()
    to_addr = settings.get("notify_email")
    if to_addr and settings.get("smtp_user") and not _email_opted_out(to_addr):
        try:
            items = []
            for h in hits:
                badges = ("🔥" if h.is_fire_deal else
                          ("💎💎" if h.deal_rating == "💎💎" else
                           ("💎" if h.deal_rating == "💎" else "")))
                lstr = f" · ${h.landed_cost:.0f} shipped" if h.landed_cost else ""
                items.append({
                    "icon": "🎯", "kind": h.target_display,
                    "sci": h.scientific_name,
                    "url": getattr(h, "product_url", "") or f"{SITE_URL}/deals",
                    "detail": f"${h.price_usd:.0f} · {h.size_text or '?'}\" · "
                              f"{h.sex or '?'} · {h.vendor_key}{lstr}  {badges}".strip(),
                })
            stats = [{"label": "Watchlist hits", "value": len(hits)},
                     {"label": "🔥 all-time lows", "value": len(fire_deals)},
                     {"label": "💎💎 deals", "value": len(gem2_deals)}]
            html, text = render_watchlist_email(items, stats, to_addr)
            subject = f"🕷 FangTrack — {len(hits)} watchlist hit{'' if len(hits)==1 else 's'} — {datetime.now().strftime('%b %d')}"
            send_email(to_addr, subject, text, settings, html=html)
            logger.info(f"Branded watchlist digest emailed to {to_addr}")
        except Exception as e:
            logger.warning(f"Branded digest email failed ({e}); sending plain text")
            try:
                _send_email(settings, "\n".join(lines), hits)
            except Exception as e2:
                logger.warning(f"Email notification failed: {e2}")


SITE_URL = os.environ.get("FANGTRACK_SITE_URL", "https://fangtrack.com")

# Email templates that may be rendered/previewed by name. Allowlist — the name
# reaches render_template and the admin preview route.
EMAIL_TEMPLATES = {"welcome", "alerts", "watchlist"}


@lru_cache(maxsize=1)
def _design_tokens() -> dict:
    """tokens/fangtrack.tokens.json — shared by the web app and the emails so
    branded HTML mail never hard-codes a colour (tests enforce parity with
    theme.py for the mirrored rarity/deal sections)."""
    p = Path(__file__).parent / "tokens" / "fangtrack.tokens.json"
    return json.loads(p.read_text(encoding="utf-8"))


def render_email(name: str, **ctx) -> tuple[str, str]:
    """Render a branded email -> (html, plain_text). `name` must be in
    EMAIL_TEMPLATES; both parts come from templates/email/<name>.{html,txt}
    with the design tokens injected as `T`."""
    if name not in EMAIL_TEMPLATES:
        raise ValueError(f"unknown email template: {name!r}")
    ctx.setdefault("site_url", SITE_URL)
    ctx["T"] = _design_tokens()
    # test_request_context, not app_context: the auth context processor reads
    # session, which only exists inside a request context (the cron path has none).
    with app.test_request_context():
        html = render_template(f"email/{name}.html", **ctx)
        text = render_template(f"email/{name}.txt", **ctx)
    return html, text


def send_email(to_addr: str, subject: str, body: str, settings: dict = None,
               html: str = None) -> None:
    """Send one email via the configured SMTP account. Plain text by default;
    pass `html` to send multipart/alternative (text part stays the fallback).
    Shared by the watchlist digest, password resets, and branded mail. Raises
    on failure so callers can decide how loud to be."""
    settings = settings or load_settings()
    if not settings.get("smtp_user") or not settings.get("smtp_pass"):
        raise RuntimeError("SMTP is not configured (set FANGTRACK_SMTP_USER / _PASS)")
    # The SMTP username (e.g. Resend's "resend") authenticates the session but is
    # NOT a valid From address. The From/envelope-sender must be on the verified
    # sending domain, or the provider silently drops the message.
    from_header = settings.get("mail_from") or "FangTrack <mike@fangtrack.com>"
    envelope_from = (from_header.split("<", 1)[1].split(">", 1)[0]
                     if "<" in from_header and ">" in from_header else from_header)
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = from_header, to_addr, subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings["smtp_host"], settings["smtp_port"]) as s:
        s.starttls()
        s.login(settings["smtp_user"], settings["smtp_pass"])
        s.send_message(msg, from_addr=envelope_from, to_addrs=[to_addr])


def _send_email(settings: dict, body: str, hits: list):
    subject = f"🕷 Tracker Digest — {len(hits)} watchlist hits — {datetime.now().strftime('%b %d')}"
    send_email(settings["notify_email"], subject, body, settings)
    logger.info(f"Digest emailed to {settings['notify_email']}")


# ── Branded alert / watchlist email (unsubscribe + hyperlinked names) ──────────

def _unsub_serializer():
    from itsdangerous import URLSafeSerializer
    return URLSafeSerializer(app.secret_key or "fangtrack-dev-key", salt="email-unsub")


def _unsub_url(email: str) -> str:
    """One-click unsubscribe URL for a recipient (signed, no login needed)."""
    return f"{SITE_URL}/unsubscribe/{_unsub_serializer().dumps(email or '')}"


def _email_opted_out(email: str) -> bool:
    """True if a user with this email has unsubscribed from alert/watchlist mail."""
    if not email:
        return False
    try:
        conn = get_connection(DB_PATH)
        _ensure_profile_cols(conn)
        row = conn.execute("SELECT email_opt_out FROM users WHERE lower(email)=lower(?)",
                           (email,)).fetchone()
        conn.close()
        return bool(row and row["email_opt_out"])
    except Exception:
        return False


_ALERT_KIND = {"fire": "All-time low", "price_drop": "Price drop",
               "back_in_stock": "Back in stock", "saved_search": "Watchlist match"}


def _alert_items(events: list) -> list:
    """Turn raw alert events into email rows: icon, kind, scientific name, a link
    (the exact listing, or the species page as a fallback so the name is ALWAYS
    clickable), and the detail line."""
    items = []
    for e in events[:50]:
        sci = e.get("sci") or (e.get("title", "").split(":", 1)[-1].strip()) \
              or (e.get("species_key") or "").title()
        url = e.get("url")
        if not url and e.get("species_key"):
            from urllib.parse import quote
            url = f"{SITE_URL}/species/{quote(e['species_key'])}"
        items.append({"icon": e.get("icon", "•"), "kind": _ALERT_KIND.get(e.get("type"), "Alert"),
                      "sci": sci, "url": url or "", "detail": e.get("detail", "")})
    return items


def render_alert_email(events: list, to_addr: str) -> tuple[str, str]:
    """(html, text) for the branded alerts email."""
    from collections import Counter
    c = Counter(e.get("type") for e in events)
    stats = [{"label": lbl, "value": c.get(t, 0)} for t, lbl in
             (("fire", "All-time lows"), ("price_drop", "Price drops"),
              ("back_in_stock", "Restocks"), ("saved_search", "Watchlist"))
             if c.get(t)]
    n = len(events)
    return render_email("alerts",
                        intro=f"{n} new alert{'' if n == 1 else 's'} from the latest crawl",
                        stats=stats, items=_alert_items(events),
                        unsub_url=_unsub_url(to_addr),
                        cta_url=f"{SITE_URL}/alerts", cta_label="View all alerts")


def render_watchlist_email(items: list, stats: list, to_addr: str) -> tuple[str, str]:
    """(html, text) for the branded watchlist digest email."""
    return render_email("watchlist",
                        intro=f"{len(items)} watchlist hit{'' if len(items) == 1 else 's'} today"
                              if items else "Your watchlist digest",
                        stats=stats, items=items,
                        unsub_url=_unsub_url(to_addr),
                        cta_url=f"{SITE_URL}/deals", cta_label="Browse today's deals")


def send_branded_alert_email(settings: dict, events: list, to_addr: str = None) -> None:
    """Send the branded (multipart) alerts email. No-op without SMTP or if the
    recipient has unsubscribed."""
    to_addr = to_addr or settings.get("notify_email")
    if not (to_addr and settings.get("smtp_user") and settings.get("smtp_pass")):
        return
    if _email_opted_out(to_addr):
        return
    html, text = render_alert_email(events, to_addr)
    n = len(events)
    send_email(to_addr, f"🕷 FangTrack — {n} new alert{'' if n == 1 else 's'}",
               text, settings, html=html)


# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route("/healthz")
def healthz():
    """Lightweight liveness probe for Render / uptime monitors — no DB hit."""
    return {"status": "ok"}, 200


# robots.txt — curb the bot-crawler load that saturates the 1-worker box
# (2026-07-20 flap). Keeps every content page indexable (/, /species,
# /species/<name>, /deals, /genus/*, /about) but waves mass crawlers off the
# heavy/duplicate surfaces: faceted query URLs (sort/page/filter variants of the
# same content), the 420KB /history dump, the JSON /api endpoints, and the
# private/admin areas. Crawl-delay throttles the rate on the pages they DO take.
# This is advisory-only: it never blocks a signed-in human or a purpose-built
# agent, only well-behaved crawlers.
_ROBOTS_TXT = """User-agent: *
Crawl-delay: 10
Disallow: /*?
Disallow: /history
Disallow: /api/
Disallow: /admin/
Disallow: /account
Disallow: /collection
Disallow: /watchlist
Disallow: /settings
Disallow: /login
Disallow: /register
Allow: /
"""


@app.route("/robots.txt")
def robots_txt():
    resp = app.response_class(_ROBOTS_TXT, mimetype="text/plain")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/tokens/fangtrack.css")
def tokens_css():
    """Design-token stylesheet, served from tokens/ so the token files stay a
    single directory of truth (base.html links this instead of an inline
    :root block)."""
    resp = send_from_directory(os.path.join(app.root_path, "tokens"),
                               "fangtrack.css", mimetype="text/css")
    # Immutable + 1yr: the link is ?v=-busted (base.html bumps it on token edits),
    # so browsers/CDN can hold it forever and never revalidate.
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


def _sample_alert_events() -> list:
    """Realistic sample events for previewing/testing the alerts email."""
    return [
        {"type": "fire", "icon": "🔥", "sci": "Poecilotheria metallica", "species_key": "poecilotheria metallica",
         "detail": "$65 at fear_not_tarantulas ($78 shipped)", "url": f"{SITE_URL}/deals"},
        {"type": "price_drop", "icon": "▼", "sci": "Grammostola pulchra", "species_key": "grammostola pulchra",
         "detail": "$90 → $72 (−20%) at spider_shoppe", "url": f"{SITE_URL}/deals"},
        {"type": "back_in_stock", "icon": "↺", "sci": "Monocentropus balfouri", "species_key": "monocentropus balfouri",
         "detail": "$45 at the_tarantula_collective", "url": f"{SITE_URL}/deals"},
        {"type": "saved_search", "icon": "🎯", "sci": "Chromatopelma cyaneopubescens", "species_key": "chromatopelma cyaneopubescens",
         "detail": "$28 · 1.5\" · juices_arthropods", "url": f"{SITE_URL}/deals"},
    ]


def _sample_watchlist():
    """Sample (items, stats) for previewing/testing the watchlist email."""
    items = [
        {"icon": "🎯", "kind": "Watchlist match", "sci": "Pamphobeteus sp. machala",
         "url": f"{SITE_URL}/deals", "detail": "$40 · 2\" · ♀ · great_basin_tarantulas 🔥"},
        {"icon": "🎯", "kind": "Watchlist match", "sci": "Xenesthis intermedia",
         "url": f"{SITE_URL}/deals", "detail": "$120 · 1.25\" · unsexed · exotics_unlimited 💎💎"},
    ]
    stats = [{"label": "Watchlist hits", "value": 2},
             {"label": "All-time lows", "value": 6}, {"label": "💎💎 deals", "value": 3}]
    return items, stats


@app.route("/admin/email-preview/<name>")
@admin_required
def email_preview(name):
    """Render an email template in the browser for review before anything is
    sent. Allowlisted names only."""
    if name not in EMAIL_TEMPLATES:
        abort(404)
    if name == "alerts":
        html, _ = render_alert_email(_sample_alert_events(), "mike@fangtrack.com")
    elif name == "watchlist":
        items, stats = _sample_watchlist()
        html, _ = render_watchlist_email(items, stats, "mike@fangtrack.com")
    else:
        html, _ = render_email(name, display_name="Mike",
                               cta_url=f"{SITE_URL}/deals", cta_label="Browse today's deals")
    return html


@app.route("/admin/email-test/<name>")
@admin_required
def email_test(name):
    """Send a real test of a branded email to ?to= (default mike@fangtrack.com).
    Uses the configured SMTP — works on prod where Resend is set."""
    if name not in ("alerts", "watchlist"):
        abort(404)
    to_addr = (request.args.get("to") or "mike@fangtrack.com").strip()
    settings = load_settings()
    if not (settings.get("smtp_user") and settings.get("smtp_pass")):
        return {"ok": False, "error": "SMTP not configured in this environment"}, 503
    try:
        if name == "alerts":
            html, text = render_alert_email(_sample_alert_events(), to_addr)
            subject = "🕷 FangTrack — 4 new alerts (test)"
        else:
            items, stats = _sample_watchlist()
            html, text = render_watchlist_email(items, stats, to_addr)
            subject = "🕷 FangTrack — watchlist digest (test)"
        send_email(to_addr, subject, text, settings, html=html)
        return {"ok": True, "sent_to": to_addr, "template": name}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


@app.route("/unsubscribe/<token>")
def unsubscribe(token):
    """One-click unsubscribe from alert/watchlist email (CAN-SPAM). Signed token,
    no login needed. Turns off ALL alert email for the matching user; in-app inbox
    alerts still work. Idempotent."""
    from itsdangerous import BadSignature
    try:
        email = _unsub_serializer().loads(token)
    except BadSignature:
        return _unsub_page("This unsubscribe link is invalid or expired.", ok=False), 400
    try:
        conn = get_connection(DB_PATH)
        _ensure_profile_cols(conn)
        conn.execute("UPDATE users SET email_opt_out=1, alert_categories='' "
                     "WHERE lower(email)=lower(?)", (email,))
        conn.commit()
        conn.close()
    except Exception:
        pass
    return _unsub_page(f"{email} has been unsubscribed from FangTrack alert emails. "
                       "You'll still see alerts in your in-app inbox.", ok=True)


def _unsub_page(msg: str, ok: bool = True) -> str:
    T = _design_tokens()
    color = T["color"]["accent"]["primary"] if ok else "#f97316"
    return f"""<!doctype html><meta charset=utf-8>
<title>FangTrack — Unsubscribe</title>
<body style="margin:0;background:{T['color']['surface']['base']};color:{T['color']['text']['primary']};
             font-family:{T['type']['family']};text-align:center;padding:80px 20px;">
  <div style="font-size:22px;font-weight:900;letter-spacing:-.02em;margin-bottom:24px;">
    <span style="color:#fff;">FANG</span><span style="color:{color};">TRACK</span></div>
  <p style="font-size:15px;line-height:1.7;max-width:440px;margin:0 auto;">{msg}</p>
  <p style="margin-top:28px;"><a href="{SITE_URL}/account/alerts"
     style="color:{color};">Manage alert preferences</a></p>
</body>"""


def _is_tarantula_listing(l) -> bool:
    """True if the listing's genus is a known Theraphosidae (tarantula) genus.
    Keeps the dashboard Top Deals to tarantulas only — no scorpions/centipedes/
    millipedes/beetles/roaches/isopods."""
    from normalize.traits import TARANTULA_GENUS_DEFAULTS
    global _TARANTULA_GENERA
    try:
        _TARANTULA_GENERA
    except NameError:
        _TARANTULA_GENERA = {g.lower() for g in TARANTULA_GENUS_DEFAULTS}
    k = (l.get("scientific_name_key") or "").strip().lower()
    return bool(k) and k.split(" ")[0] in _TARANTULA_GENERA


def _curated_top_deals(snap, n=12):
    """Curated 'Top Deals right now': tarantulas only, in-stock, ONE best deal per
    species, ranked by deal grade + rarity, then spread across price tiers so the
    list isn't all $10-12 slings. Vendor links to the exact listing in the template."""
    def _rar(l):
        return l.get("size_class_rarity_score") or l.get("rarity_score") or 0

    def _weight(l):
        w = 0.0
        if l.get("is_fire_deal"):
            w += 3
        dr = l.get("deal_rating")
        if dr == "💎💎":
            w += 3
        elif dr == "💎":
            w += 2
        elif dr == "👍":
            w += 1
        return w + _rar(l) / 10.0   # rarity 0-10 → 0-1, tie-breaks toward rarer

    cand = [l for l in snap
            if _is_tarantula_listing(l)
            and l.get("availability") != "out_of_stock"
            and (l.get("price_usd") or 0) > 0
            and (l.get("is_fire_deal")
                 or l.get("deal_rating") in ("💎💎", "💎")
                 or (_rar(l) >= 7 and l.get("deal_rating") in ("💎💎", "💎", "👍")))]

    # one BEST deal per species (highest weight wins)
    best = {}
    for l in cand:
        k = l.get("scientific_name_key")
        if k and (k not in best or _weight(l) > _weight(best[k])):
            best[k] = l
    ranked = sorted(best.values(), key=lambda l: (-_weight(l), l.get("price_usd") or 9e9))

    # round-robin across price tiers → a spread of prices AND sizes, best-first per tier
    def _tier(p):
        p = p or 0
        return 0 if p < 50 else 1 if p < 150 else 2 if p < 400 else 3
    tiers = {0: [], 1: [], 2: [], 3: []}
    for l in ranked:
        tiers[_tier(l.get("price_usd"))].append(l)
    out = []
    while len(out) < n and any(tiers.values()):
        for t in (0, 1, 2, 3):
            if tiers[t]:
                out.append(tiers[t].pop(0))
                if len(out) >= n:
                    break
    return out


def _filter_banned_movers(movers: dict) -> dict:
    """Belt-and-suspenders: strip BANNED_MOVER_VENDORS (Urban) from the movers at
    RENDER time. market_movers already excludes them when building, but the movers
    are served from a cron-built blob that can be stale (built before the ban, or
    not yet rebuilt) — this makes the ban hold no matter what blob is loaded."""
    from analytics.market import BANNED_MOVER_VENDORS
    if not isinstance(movers, dict):
        return movers
    out = dict(movers)
    for col in ("fire", "drops", "back_in_stock"):
        v = out.get(col)
        if isinstance(v, list):
            out[col] = [m for m in v
                        if not (isinstance(m, dict) and m.get("vendor_key") in BANNED_MOVER_VENDORS)]
    return out


@app.route("/")
def dashboard():
    # The dashboard is the market overview — site crawls only. Private-seller lists
    # never appear here (nor in its counts, movers, or coverage); they live on the
    # Deals filter and species cards for signed-in users.
    from vendors import REGISTRY
    from analytics.market import BANNED_MOVER_VENDORS
    snap = [l for l in get_snapshot()
            if l.get("vendor_key") in REGISTRY
            and l.get("vendor_key") not in BANNED_MOVER_VENDORS]
    fire   = [l for l in snap if l.get("is_fire_deal")]
    gem2   = [l for l in snap if l.get("deal_rating") == "💎💎" and not l.get("is_fire_deal")]
    gem1   = [l for l in snap if l.get("deal_rating") == "💎"]
    fair   = [l for l in snap if l.get("deal_rating") == "👍"]
    above  = [l for l in snap if l.get("deal_rating") == "👎"]
    female = [l for l in snap if l.get("sex") == "F"]
    top_deals = _curated_top_deals(snap)
    _attach_clean_names(top_deals)
    summary = _cached_crawl_summary()[-10:]
    hits = _crawl_state.get("last_hits", [])
    wl_targets = list_targets(DB_PATH, user_id=current_user_id()) if current_user_id() else []

    # ── Market movers + intelligence (only change on a crawl → cached) ───────
    movers = _filter_banned_movers(_cached_movers(snap))
    stats = get_market_stats()
    intel = _cached_intel(snap)

    # ── Header meta + crawl-history depth (drives the mover empty-state counters) ─
    head = _dashboard_header_meta()
    # Site-only vendor count (private sellers excluded), shared with the
    # What-is-FangTrack page so the two never disagree.
    vendors_live = _site_counts(snap)["vendor_count"]

    return render_template("dashboard.html",
        top_deals=top_deals, fire_count=len(fire), gem2_count=len(gem2),
        gem1_count=len(gem1), fair_count=len(fair), above_count=len(above),
        female_count=len(female),
        total=len(snap), crawl_summary=summary, wl_hits=hits,
        wl_count=len(wl_targets), crawl_state=_crawl_state,
        movers=movers, mstats=stats, intel=intel, owned_keys=_req_owned(),
        last_crawl=head["last_crawl"], days_history=head["days"],
        crawl_health=head["health"], health_counts=head["health_counts"],
        vendors_live=vendors_live)


@app.route("/movers")
def movers_all():
    """Full market-movers lists — the 'All N →' target for each dashboard mover
    tile (all-time lows, biggest drops, restocks, heating). Reuses the same
    cached mover data the dashboard shows, just uncapped (dashboard shows [:5])."""
    from vendors import REGISTRY
    from analytics.market import BANNED_MOVER_VENDORS
    snap = [l for l in get_snapshot()
            if l.get("vendor_key") in REGISTRY
            and l.get("vendor_key") not in BANNED_MOVER_VENDORS]
    movers = _filter_banned_movers(_cached_movers(snap))
    head = _dashboard_header_meta()
    return render_template("movers.html", movers=movers, days_history=head["days"])


_header_meta_cache = {"data": None, "ts": 0}


def _dashboard_header_meta() -> dict:
    """Last-crawl time, distinct crawl-day depth, and health for the header +
    the Market-Movers empty-state progress counters. Crawl-derived → only changes
    on a crawl, so memoize with the shared TTL (was 2 uncached crawl_runs scans on
    every landing-page hit)."""
    now = time.time()
    if _header_meta_cache["data"] is not None and (now - _header_meta_cache["ts"]) < _CACHE_TTL:
        return _header_meta_cache["data"]
    out = {"last_crawl": None, "days": 0, "health": "ok",
           "health_counts": {"healthy": 0, "partial": 0, "down": 0}}
    try:
        conn = get_connection(DB_PATH)
        row = conn.execute("""SELECT MAX(started_at) mx,
                                     COUNT(DISTINCT DATE(started_at)) days
                              FROM crawl_runs WHERE status IN ('complete','partial')""").fetchone()
        # Honest scanner health from each vendor's latest run that ACTUALLY SERVES
        # DATA (status complete/partial) — the exact runs the live snapshot + Vendor
        # QA read, so the three surfaces agree:
        #   healthy = latest serving run completed
        #   partial = latest serving run was truncated (429 mid-pagination)
        #   down    = the vendor has NO successful run at all
        # A later 'rejected' (write-guard kept last-good data) or 'skipped' run must
        # NOT flip a vendor to "down": the site is still serving its last good data,
        # so Crawl History / QA show it "complete" — the dashboard now matches. (The
        # write-guard already rejects genuine collapses, so a complete run counts as
        # healthy without second-guessing its product count — that was flagging
        # fanghub, a legitimately-empty social seller, as "down".)
        rows = conn.execute("""
            SELECT cr.vendor_key AS vk, cr.status AS status
            FROM crawl_runs cr
            JOIN (SELECT vendor_key, MAX(id) AS mid FROM crawl_runs
                  WHERE status IN ('complete','partial') GROUP BY vendor_key) m
              ON cr.id = m.mid
        """).fetchall()
        conn.close()
        if row and row["mx"]:
            out["last_crawl"] = str(row["mx"])[:16].replace("T", " ")
            out["days"] = row["days"] or 0
        # Only the ACTIVE scanners count toward health — retired/removed vendors
        # still have old crawl_runs rows but aren't "down", they're gone.
        try:
            from vendors import REGISTRY
            active = set(REGISTRY.keys())
        except Exception:
            active = None
        good = {}
        for r in rows:
            if active is not None and r["vk"] not in active:
                continue
            good[r["vk"]] = (r["status"] or "").lower()
        healthy = partial = down = 0
        # Every ACTIVE scanner is counted: one with no complete/partial run at all
        # is genuinely down; the rest are healthy/partial per their latest good run.
        scanners = active if active is not None else set(good.keys())
        for vk in scanners:
            st = good.get(vk)
            if st == "partial":
                partial += 1
            elif st == "complete":
                healthy += 1
            else:
                down += 1
        out["health_counts"] = {"healthy": healthy, "partial": partial, "down": down}
        if partial or down:
            bits = []
            if healthy: bits.append(f"{healthy} healthy")
            if partial: bits.append(f"{partial} partial")
            if down: bits.append(f"{down} down")
            out["health"] = " · ".join(bits)
    except Exception:
        pass
    _header_meta_cache["data"] = out
    _header_meta_cache["ts"] = now
    return out


@app.route("/deals")
def deals():
    snap = _visible_to_user(get_snapshot())   # per-user private-seller isolation
    sex_filter   = request.args.get("sex", "")
    deal_filter  = request.args.get("deal", "")
    vendor_filter= request.args.get("vendor", "")
    source_filter= request.args.get("source", "")
    species_filter = request.args.get("species", "").strip()
    seller_mode  = request.args.get("private", "all")   # all | web | private
    # Logged-out visitors never see private sellers — hard override, even if the
    # URL asks for ?private=private. For a signed-in user the cookie toggle sets
    # the default when the page-level seller filter hasn't been explicitly chosen.
    from auth import current_user
    if current_user() is None:
        seller_mode = "web"
    elif _hide_private() and "private" not in request.args:
        seller_mode = "web"
    code_only    = request.args.get("code", "") == "1"
    min_rarity   = request.args.get("min_rarity", 0, type=int)
    min_price    = request.args.get("min_price", 0, type=float)
    max_price    = request.args.get("max_price", 9999, type=float)
    sort_by      = request.args.get("sort", "deal")

    filtered = snap
    if seller_mode == "web":
        filtered = [l for l in filtered if not l.get("is_private")]
    elif seller_mode == "private":
        filtered = [l for l in filtered if l.get("is_private")]
    if code_only:
        filtered = [l for l in filtered if l.get("discount_code")]
    if species_filter:
        skey = normalize_species_key(species_filter)
        filtered = [l for l in filtered if skey in (l.get("scientific_name_key") or "")]
    if sex_filter:
        filtered = [l for l in filtered if l.get("sex") == sex_filter]
    if deal_filter == "fire":
        filtered = [l for l in filtered if l.get("is_fire_deal")]
    elif deal_filter == "gem2":
        filtered = [l for l in filtered if l.get("deal_rating") == "💎💎"]
    elif deal_filter == "gem":
        filtered = [l for l in filtered if l.get("deal_rating") in ("💎💎","💎")]
    if vendor_filter:
        filtered = [l for l in filtered if l.get("vendor_key") == vendor_filter]
    if source_filter:
        filtered = [l for l in filtered if l.get("source_type","unknown") == source_filter]
    if min_rarity:
        filtered = [l for l in filtered
                    if (l.get("size_class_rarity_score") or 0) >= min_rarity]
    filtered = [l for l in filtered if min_price <= (l.get("price_usd") or 0) <= max_price]

    sort_key = {
        "deal":   lambda l: (l.get("deal_rating") not in ("💎💎","💎"), l.get("is_fire_deal",False) is False, l.get("price_usd",9999)),
        "price":  lambda l: l.get("price_usd", 9999),
        "rarity": lambda l: -(l.get("size_class_rarity_score") or 0),
        "vendor": lambda l: l.get("vendor_key",""),
    }.get(sort_by, lambda l: l.get("price_usd",9999))
    filtered.sort(key=sort_key)

    vendors = sorted({l.get("vendor_key","") for l in snap})
    # Paginate 100 per page — keeps the DOM small (so the table scrolls
    # smoothly and the horizontal scrollbar is reachable) and gives real paging.
    per = 50   # was 100 → the page rendered a ~445KB DOM (100 rows × sparklines),
               # slow to parse/paint on mobile even though the server + Brotli were
               # fast. 50/page ~halves the DOM for a much snappier feel.
    matched_count = len(filtered)
    pages = max(1, (matched_count + per - 1) // per)
    page = request.args.get("page", 1, type=int)
    page = max(1, min(page, pages))
    listings = filtered[(page - 1) * per: page * per]

    # Standardize the display name on every visible row to the canonical
    # "Scientific name (common name)" format, regardless of how messy the vendor's
    # raw title was. The link still targets the same clean species key.
    _attach_clean_names(listings)

    return render_template("deals.html", listings=listings, total=len(snap),
                           matched_count=matched_count, page=page, pages=pages,
                           per=per, vendors=vendors, filters=request.args,
                           page_base=_page_base(), mstats=get_market_stats(),
                           owned_keys=_req_owned())


@app.route("/watchlist")
@login_required
def watchlist():
    targets = list_targets(DB_PATH, user_id=current_user_id())
    recent_hits = _crawl_state.get("last_hits", [])

    # Picker options come from the SAME canonical catalog as the Species page —
    # only real species (genus in the known invert set), so junk like a
    # "A Walk In The Park Journey Pack" bundle title can never appear here.
    species_options = [{"value": s["display"], "common": s["common"]}
                       for s in get_species_catalog(DB_PATH)]
    return render_template("watchlist.html", targets=targets,
                           recent_hits=recent_hits, species_options=species_options)


@app.route("/watchlist/add", methods=["POST"])
@login_required
def watchlist_add():
    init_watchlist_tables(DB_PATH)
    species = request.form.get("species","").strip()
    if not species:
        flash("Species name required", "error")
        return redirect(url_for("watchlist"))
    try:
        wid = add_target(
            species,
            sex      = request.form.get("sex") or None,
            min_size = float(request.form["min_size"]) if request.form.get("min_size") else None,
            max_size = float(request.form["max_size"]) if request.form.get("max_size") else None,
            max_price= float(request.form["max_price"]) if request.form.get("max_price") else None,
            max_landed=float(request.form["max_landed"]) if request.form.get("max_landed") else None,
            notes    = request.form.get("notes") or None,
            db_path  = DB_PATH,
            user_id  = current_user_id(),
        )
        flash(f"Target #{wid} added: {species}", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("watchlist"))


@app.route("/watchlist/remove/<int:wid>", methods=["POST"])
@login_required
def watchlist_remove(wid):
    remove_target(wid, DB_PATH, user_id=current_user_id())
    flash(f"Target #{wid} removed", "success")
    return redirect(url_for("watchlist"))


# Maturity words → an approximate midpoint size (inches) when a collection item's
# size note has no explicit measurement ("Adult female", "juvie", "sling").
_MATURITY_INCHES = {
    "adult": 4.5, "mature": 4.5, "sub-adult": 3.0, "subadult": 3.0, "sub adult": 3.0,
    "juvenile": 1.25, "juvie": 1.25, "juvi": 1.25, "well-started": 1.0,
    "well started": 1.0, "sling": 0.5, "spiderling": 0.5,
}


def _item_size_inches(size_notes):
    """Best-effort size (inches) for a collection item, from an explicit measurement
    or a maturity word. None when neither is present."""
    from normalize.size import parse_size
    try:
        _mn, _mx, mid = parse_size(size_notes or "")
        if mid:
            return mid
    except Exception:
        pass
    low = (size_notes or "").lower()
    for word, inch in _MATURITY_INCHES.items():
        if word in low:
            return inch
    return None


def _sex_group(s):
    s = (s or "").strip().upper()
    if s.startswith("F"):
        return "F"
    if s.startswith("M"):
        return "M"
    return "U"


def _like_for_like_value(item, listings, blended):
    """Value ONE collection item against comparable in-stock listings of the same
    species — matching sex and size class where known — instead of a single blended
    median. Returns (unit_value, basis_label). Falls back through progressively wider
    comparisons, ending at the species-wide market median.

    Sex is the dominant price driver for tarantulas (a confirmed female commands a
    large premium), so a sexed item is compared to same-sex listings first; size
    class refines it."""
    import statistics
    from normalize.size import size_category
    priced = [l for l in listings if l.get("price_usd")]
    if not priced:
        return (blended, "market median") if blended else (None, None)

    sex = _sex_group(item.get("sex"))
    mid = _item_size_inches(item.get("size_notes"))
    bucket = size_category(mid) if mid is not None else None

    def lbucket(l):
        m = l.get("size_midpoint")
        return size_category(m) if m is not None else None

    def med(ls):
        return round(statistics.median([l["price_usd"] for l in ls]), 2)

    sexword = "female" if sex == "F" else "male"
    # Tier 1: same sex + same size class (most specific)
    if sex in ("F", "M"):
        same_sex = [l for l in priced if _sex_group(l.get("sex")) == sex]
        if bucket:
            t = [l for l in same_sex if lbucket(l) == bucket]
            if len(t) >= 2:
                return med(t), f"{bucket.lower()} {sexword} comps ({len(t)})"
        # Tier 2: same sex, any size
        if len(same_sex) >= 2:
            return med(same_sex), f"{sexword} comps ({len(same_sex)})"
    # Tier 3: same size class, any sex (for unsexed items)
    if bucket:
        t = [l for l in priced if lbucket(l) == bucket]
        if len(t) >= 2:
            return med(t), f"{bucket.lower()} comps ({len(t)})"
    # Tier 4: species-wide blended median
    return (blended if blended else med(priced)), "market median"


def _collection_valued(items: list) -> tuple[list, dict]:
    """Annotate collection items with today's market value and a portfolio rollup
    (distinct species, cost basis, gain/loss). Each item is valued LIKE-FOR-LIKE:
    against same-species listings matching its sex and size class, falling back to
    the species-wide trimmed-median Market Price when specifics aren't available."""
    stats = get_market_stats()
    from normalize.species_canonical import canonical_species
    from normalize.common_names_map import best_common
    # Group current in-stock listings by species key for like-for-like comparisons.
    # Visible-only: a user's valuation may use their own private sellers, never
    # another user's.
    listings_by_key = {}
    for l in _visible_to_user(get_snapshot()):
        k = l.get("scientific_name_key") or ""
        if k and l.get("price_usd"):
            listings_by_key.setdefault(k, []).append(l)
    total_val = 0.0
    cost_basis = 0.0
    valued = 0
    species = set()
    for it in items:
        key = it.get("species_key") or ""
        it["common"] = best_common(key, "")
        st = stats.get(key)
        ck = key
        if st is None:
            # collection keys may be normalize_species_key; try canonical
            try:
                ck = canonical_species(it.get("species_display") or key)[0]
                st = stats.get(ck)
            except Exception:
                st = None
        blended = (st or {}).get("market_price")
        unit, basis = _like_for_like_value(
            it, listings_by_key.get(key) or listings_by_key.get(ck) or [], blended)
        qty = it.get("quantity") or 1
        it["market_price"] = unit
        it["value_basis"] = basis
        it["market_value"] = round(unit * qty, 2) if unit else None
        it["lowest_ask"] = (st or {}).get("lowest_ask")
        species.add(key)
        paid = it.get("price_paid")
        if paid:
            cost_basis += paid * qty
        # per-item gain vs what was paid
        if paid and it["market_value"]:
            it["gain"] = round(it["market_value"] - paid * qty, 2)
        else:
            it["gain"] = None
        if it["market_value"]:
            total_val += it["market_value"]
            valued += 1
    gain = round(total_val - cost_basis, 2) if cost_basis else None
    port = {
        "total_value": round(total_val, 2),
        "holdings": len(items),
        "species": len(species),
        "animals": sum((it.get("quantity") or 1) for it in items),
        "valued": valued,
        "cost_basis": round(cost_basis, 2) if cost_basis else None,
        "gain": gain,
    }
    return items, port


def _ensure_collection_cols(conn):
    """Additively add purchase-tracking columns to the app's own collection
    table (nullable, non-destructive; the market pipeline never touches it)."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(collection)")}
    for col, decl in (("price_paid", "REAL"), ("acquired_date", "TEXT"),
                      ("source", "TEXT")):
        if col not in have:
            conn.execute(f"ALTER TABLE collection ADD COLUMN {col} {decl}")
    conn.commit()


@app.route("/collection")
@login_required
def collection():
    conn = get_connection(DB_PATH)
    try:
        _ensure_collection_cols(conn)
        items = [dict(r) for r in conn.execute(
            "SELECT * FROM collection WHERE user_id=? ORDER BY species_display",
            (current_user_id(),)).fetchall()]
    except Exception:
        items = []
    conn.close()
    items, portfolio = _collection_valued(items)
    return render_template("collection.html", items=items, portfolio=portfolio)


@app.route("/collection/edit/<int:item_id>", methods=["POST"])
@login_required
def collection_edit(item_id):
    conn = get_connection(DB_PATH)
    _ensure_collection_cols(conn)
    def _num(field):
        v = request.form.get(field, "").strip()
        try:
            return float(v) if v else None
        except ValueError:
            return None
    conn.execute("""
        UPDATE collection SET sex=?, quantity=?, size_notes=?, notes=?,
               price_paid=?, acquired_date=?, source=? WHERE id=? AND user_id=?
    """, (request.form.get("sex") or None,
          int(request.form.get("quantity") or 1),
          request.form.get("size_notes") or None,
          request.form.get("notes") or None,
          _num("price_paid"),
          request.form.get("acquired_date") or None,
          request.form.get("source") or None,
          item_id, current_user_id()))
    conn.commit()
    conn.close()
    flash("Collection entry updated.", "success")
    return redirect(url_for("collection"))


# Common label stock — geometry in inches on US Letter (8.5×11). Avery numbers
# and their OnlineLabels equivalents share the same layout, so each entry lists
# both. cols/rows/label size + page margins + gaps drive the print CSS so the
# sheet lines up with the physical labels.
LABEL_TEMPLATES = {
    "ol875_5160": {"name": 'Avery 5160/8160 · OnlineLabels OL875 — 1" × 2⅝" (30/sheet)',
                   "cols": 3, "rows": 10, "w": 2.625, "h": 1.0,
                   "mt": 0.5, "ml": 0.1875, "gx": 0.125, "gy": 0.0},
    "ol125_5163": {"name": 'Avery 5163/8163 · OnlineLabels OL125 — 2" × 4" (10/sheet)',
                   "cols": 2, "rows": 5, "w": 4.0, "h": 2.0,
                   "mt": 0.5, "ml": 0.15625, "gx": 0.1875, "gy": 0.0},
    "ol150_5164": {"name": 'Avery 5164/8164 · OnlineLabels OL150 — 3⅓" × 4" (6/sheet)',
                   "cols": 2, "rows": 3, "w": 4.0, "h": 3.333,
                   "mt": 0.5, "ml": 0.15625, "gx": 0.1875, "gy": 0.0},
    "ol1000_5167": {"name": 'Avery 5167/8167 · OnlineLabels OL1000 — ½" × 1¾" (80/sheet)',
                    "cols": 4, "rows": 20, "w": 1.75, "h": 0.5,
                    "mt": 0.5, "ml": 0.28125, "gx": 0.3, "gy": 0.0},
    "ol5000_5195": {"name": 'Avery 5195 · OnlineLabels OL5000 — ⅔" × 1¾" (60/sheet)',
                    "cols": 4, "rows": 15, "w": 1.75, "h": 0.6667,
                    "mt": 0.48, "ml": 0.28125, "gx": 0.3, "gy": 0.0},
}


@app.route("/collection/labels")
@login_required
def collection_labels():
    """Printer-ready collection labels laid out for a chosen label stock."""
    conn = get_connection(DB_PATH)
    try:
        items = [dict(r) for r in conn.execute(
            "SELECT * FROM collection WHERE user_id=? ORDER BY species_display",
            (current_user_id(),)).fetchall()]
    except Exception:
        items = []
    conn.close()
    from normalize.common_names_map import COMMON_NAMES
    for it in items:
        it["common"] = COMMON_NAMES.get(it.get("species_key") or "", "")
    tkey = request.args.get("template", "ol875_5160")
    if tkey not in LABEL_TEMPLATES:
        tkey = "ol875_5160"
    tmpl = LABEL_TEMPLATES[tkey]
    per_sheet = tmpl["cols"] * tmpl["rows"]
    return render_template("collection_labels.html", items=items,
                           today=datetime.now().strftime("%Y-%m-%d"),
                           templates=LABEL_TEMPLATES, tkey=tkey, tmpl=tmpl,
                           per_sheet=per_sheet)


@app.route("/collection/add", methods=["POST"])
@login_required
def collection_add():
    conn = get_connection(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS collection (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            species_key TEXT NOT NULL,
            species_display TEXT NOT NULL,
            sex TEXT,
            quantity INTEGER DEFAULT 1,
            size_notes TEXT,
            notes TEXT,
            added_at TEXT DEFAULT (datetime('now'))
        );
    """)
    species = request.form.get("species","").strip()
    if not species:
        flash("Species name required", "error")
        return redirect(url_for("collection"))
    # Prefer the combobox's canonical species key (an exact pick); fall back to
    # deriving the key from the typed text for manual/free entries.
    from normalize.key_aliases import canonicalize_key
    picked = request.form.get("species_key", "").strip()
    key = canonicalize_key(picked) if picked else normalize_species_key(species)
    conn.execute("""
        INSERT INTO collection (species_key, species_display, sex, quantity, size_notes, notes, user_id)
        VALUES (?,?,?,?,?,?,?)
    """, (key, species,
          request.form.get("sex") or None,
          int(request.form.get("quantity") or 1),
          request.form.get("size_notes") or None,
          request.form.get("notes") or None,
          current_user_id()))
    conn.commit()
    conn.close()
    flash(f"Added {species} to collection", "success")
    return redirect(url_for("collection"))


@app.route("/collection/remove/<int:item_id>", methods=["POST"])
@login_required
def collection_remove(item_id):
    conn = get_connection(DB_PATH)
    conn.execute("DELETE FROM collection WHERE id = ? AND user_id = ?", (item_id, current_user_id()))
    conn.commit()
    conn.close()
    flash("Removed from collection", "success")
    return redirect(url_for("collection"))


# ── Collection spreadsheet uploader ─────────────────────────────────────────
# A collector with a sheet can upload it and have the Collection columns fill
# automatically. Column names are matched fuzzily so any reasonable header works.
_COL_ALIASES = {
    "species":  ["scientific name", "scientific", "species", "latin", "name"],
    "common":   ["common name", "common"],
    "sex":      ["sex", "gender"],
    "size":     ["size notes", "size", "size_notes", "leg span", "legspan",
                 "dls", "length", "current size", "grow", "inches", '"', "cm",
                 "body", "measurement"],
    "source":   ["source", "cb/wc", "cb wc", "captive"],
    "vendor":   ["vendor", "seller", "bought from", "purchased from", "from"],
    "price":    ["price paid", "cost", "price", "paid", "amount", "$"],
    "date":     ["acquired date", "acquired", "purchase date", "date"],
    "notes":    ["notes", "note", "comment", "comments"],
    "quantity": ["quantity", "qty", "count", "#"],
}


def _map_collection_columns(columns) -> dict:
    """Map incoming spreadsheet columns onto collection fields (fuzzy, first match wins)."""
    norm = {str(c).strip().lower(): c for c in columns}
    mapping = {}
    for field, aliases in _COL_ALIASES.items():
        for alias in aliases:                    # try exact, then substring
            if alias in norm:
                mapping[field] = norm[alias]; break
        else:
            for alias in aliases:
                hit = next((orig for low, orig in norm.items() if alias in low), None)
                if hit:
                    mapping[field] = hit; break
    return mapping


def _norm_sex(v) -> str | None:
    s = str(v or "").strip().lower()
    if not s or s in ("nan", "unknown", "u", "?"):
        return None
    if s.startswith("mature m") or s in ("mm",):
        return "MM"
    if s.startswith("f"):
        return "F"
    if s.startswith("m"):
        return "M"
    return None


def _norm_date(v) -> str | None:
    s = str(v or "").strip()
    if not s or s.lower() == "nan":
        return None
    return s[:10]  # ISO / Timestamp string → YYYY-MM-DD


def parse_collection_file(stream, filename: str) -> list[dict]:
    """Parse an uploaded .csv/.xlsx into collection-row dicts (species canonicalized)."""
    import pandas as pd
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        df = pd.read_excel(stream)
    else:
        df = pd.read_csv(stream)
    m = _map_collection_columns(df.columns)
    if "species" not in m:
        raise ValueError("Couldn't find a scientific-name / species column in the file.")

    def cell(row, field):
        col = m.get(field)
        if not col:
            return None
        val = row.get(col)
        try:
            if val is None or pd.isna(val):   # catches NaN (float) and NaT (datetime)
                return None
        except (TypeError, ValueError):
            pass
        return val

    import re as _re
    rows = []
    for _, row in df.iterrows():
        species = str(cell(row, "species") or "").strip()
        # Require a real name: non-empty and containing letters (skips blank/NaN/NaT/total rows).
        if not species or species.lower() in ("nan", "nat") or not _re.search(r"[A-Za-z]", species):
            continue
        # Notes = ONLY the user's Notes column. The Common Name column is redundant
        # (the common name is derived from the species key) and must NOT be folded in.
        raw_notes = cell(row, "notes")
        notes = (str(raw_notes).strip()
                 if raw_notes and str(raw_notes).strip() and str(raw_notes).lower() != "nan"
                 else None)
        try:
            price = float(cell(row, "price")) if cell(row, "price") is not None else None
        except (TypeError, ValueError):
            price = None
        try:
            qty = int(float(cell(row, "quantity"))) if cell(row, "quantity") is not None else 1
        except (TypeError, ValueError):
            qty = 1
        rows.append({
            "species_display": species,
            "species_key": normalize_species_key(species),
            "sex": _norm_sex(cell(row, "sex")),
            "quantity": qty or 1,
            "size_notes": (str(cell(row, "size")).strip() if cell(row, "size") is not None else None),
            "notes": notes,
            "price_paid": price,
            "acquired_date": _norm_date(cell(row, "date")),
            "source": (str(cell(row, "source") or cell(row, "vendor")).strip()
                       if (cell(row, "source") or cell(row, "vendor")) is not None else None),
        })
    return rows


def _insert_collection_rows(conn, rows: list[dict], skip_existing_keys: bool = False,
                            user_id=None) -> tuple[int, int]:
    """Insert parsed collection rows for a user. Returns (added, skipped)."""
    _ensure_collection_cols(conn)
    existing = {r["species_key"] for r in conn.execute(
        "SELECT species_key FROM collection WHERE user_id = ?", (user_id,))}
    added = skipped = 0
    for r in rows:
        if skip_existing_keys and r["species_key"] in existing:
            skipped += 1
            continue
        # Positional ? placeholders — the pg adapter translates ?→%s but NOT the
        # sqlite-only :named style, so named params 500'd every upload on prod
        # Postgres (worked locally on SQLite). This is the real "uploader broken".
        conn.execute("""
            INSERT INTO collection
              (species_key, species_display, sex, quantity, size_notes, notes,
               price_paid, acquired_date, source, user_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (r["species_key"], r["species_display"], r["sex"], r["quantity"],
              r["size_notes"], r["notes"], r["price_paid"], r["acquired_date"],
              r["source"], user_id))
        existing.add(r["species_key"])
        added += 1
    conn.commit()
    return added, skipped


@app.route("/collection/upload", methods=["POST"])
@login_required
def collection_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose a .csv or .xlsx file to upload.", "error")
        return redirect(url_for("collection"))
    try:
        rows = parse_collection_file(f.stream, f.filename)
    except Exception as e:
        flash(f"Couldn't read that file: {e}", "error")
        return redirect(url_for("collection"))
    if not rows:
        flash("No rows with a species name were found in that file.", "error")
        return redirect(url_for("collection"))
    skip_dupes = request.form.get("skip_dupes") == "on"
    conn = get_connection(DB_PATH)
    added, skipped = _insert_collection_rows(conn, rows, skip_existing_keys=skip_dupes,
                                             user_id=current_user_id())
    conn.close()
    msg = f"Imported {added} animal(s) from {f.filename}."
    if skipped:
        msg += f" Skipped {skipped} already in your collection."
    flash(msg, "success")
    return redirect(url_for("collection"))


# ── Shareable collections + collector Leaderboard ───────────────────────────
# Opt-in public profiles (vanity handle) and leaderboards sliced several ways —
# the community / status / sign-up engine. Scaffold: value + rarity slices, a
# public read-only profile, and a privacy toggle. (Photos, friends-only, and
# anti-gaming value caps are follow-ups.)
import re as _re_profile


def _ensure_profile_cols(conn):
    have = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "is_public" not in have:
        conn.execute("ALTER TABLE users ADD COLUMN is_public INTEGER DEFAULT 0")
    if "handle" not in have:
        conn.execute("ALTER TABLE users ADD COLUMN handle TEXT")
    # Real name — PRIVATE (not asked at signup, never shown publicly; the
    # leaderboard/public profile keep showing display_name). Only the user + an
    # admin can see it.
    if "first_name" not in have:
        conn.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
    if "last_name" not in have:
        conn.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
    # Opt-in market-alert categories (comma-separated: fire,drops,restocks). Empty
    # by default → a user only gets alerts for their own saved searches, not the
    # firehose of every market mover.
    if "alert_categories" not in have:
        conn.execute("ALTER TABLE users ADD COLUMN alert_categories TEXT DEFAULT ''")
    # One-click email unsubscribe (CAN-SPAM). 1 = never send this user any alert /
    # watchlist email again (in-app inbox alerts still work). Set by /unsubscribe.
    if "email_opt_out" not in have:
        conn.execute("ALTER TABLE users ADD COLUMN email_opt_out INTEGER DEFAULT 0")
    conn.commit()


_VALID_ALERT_CATS = {"fire", "drops", "restocks"}


def _user_alert_categories(user_id) -> set:
    """Market-alert categories this user opted into (empty for anon / no opt-in)."""
    if not user_id:
        return set()
    try:
        conn = get_connection(DB_PATH)
        _ensure_profile_cols(conn)
        row = conn.execute("SELECT alert_categories FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        raw = (row["alert_categories"] if row else "") or ""
        return {c.strip() for c in raw.split(",") if c.strip() in _VALID_ALERT_CATS}
    except Exception:
        return set()


def _slugify_handle(raw: str) -> str:
    s = _re_profile.sub(r"[^a-z0-9-]", "", (raw or "").strip().lower().replace(" ", "-"))
    return _re_profile.sub(r"-+", "-", s).strip("-")[:30]


_RARITY_ORDER = {"Mythic": 0, "Legendary": 1, "Rare": 2, "Uncommon": 3,
                 "Common": 4, "Ubiquitous": 5}


def _collection_stats_for(user_id, tiers=None):
    """Value + rarity rollup for one user's collection. `tiers` = catalog_rarity_tiers
    map, passed in so the leaderboard computes it once."""
    from analytics.market import catalog_rarity_tiers
    if tiers is None:
        tiers = catalog_rarity_tiers(DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        _ensure_collection_cols(conn)
        items = [dict(r) for r in conn.execute(
            "SELECT * FROM collection WHERE user_id=?", (user_id,)).fetchall()]
    except Exception:
        items = []
    conn.close()
    items, portfolio = _collection_valued(items)
    mythic = legendary = 0
    rarest = None
    genus = {}
    for it in items:
        key = it.get("species_key") or ""
        t = (tiers.get(key) or {}).get("tier")
        if t == "Mythic":
            mythic += 1
        elif t == "Legendary":
            legendary += 1
        if t and (rarest is None or _RARITY_ORDER.get(t, 9) < _RARITY_ORDER.get(rarest[1], 9)):
            rarest = (it.get("species_display"), t)
        g = key.split()[0] if key else ""
        if g:
            genus[g] = genus.get(g, 0) + (it.get("quantity") or 1)
    top_genus = max(genus.items(), key=lambda kv: kv[1]) if genus else None
    return {
        "value": portfolio.get("total_value") or 0,
        "species": portfolio.get("species") or 0,
        "animals": portfolio.get("animals") or sum((it.get("quantity") or 1) for it in items),
        "mythic": mythic,
        "legendary": legendary,
        "rarest": rarest,          # (display, tier) or None
        "top_genus": top_genus,    # (genus, count) or None
    }


_leaderboard_cache = {"data": None, "ts": 0}


@app.route("/leaderboard")
def leaderboard():
    now = time.time()
    if _leaderboard_cache["data"] and now - _leaderboard_cache["ts"] < 120:
        board = _leaderboard_cache["data"]
    else:
        from analytics.market import catalog_rarity_tiers
        tiers = catalog_rarity_tiers(DB_PATH)
        conn = get_connection(DB_PATH)
        _ensure_profile_cols(conn)
        pubs = [dict(r) for r in conn.execute(
            "SELECT id, display_name, handle FROM users WHERE is_public=1 AND handle IS NOT NULL")]
        conn.close()
        rows = []
        for u in pubs:
            s = _collection_stats_for(u["id"], tiers)
            if s["animals"]:
                rows.append({**u, **s})
        def top(key, n=10):
            return sorted([r for r in rows if r.get(key)], key=lambda r: r[key], reverse=True)[:n]
        board = {
            "count": len(rows),
            "most_valuable": top("value"),
            "most_species": top("species"),
            "most_mythic": top("mythic"),
            "most_animals": top("animals"),
            "rarest": sorted([r for r in rows if r.get("rarest")],
                             key=lambda r: _RARITY_ORDER.get(r["rarest"][1], 9))[:10],
        }
        _leaderboard_cache.update(data=board, ts=now)
    return render_template("leaderboard.html", board=board)


@app.route("/u/<handle>")
def public_profile(handle):
    conn = get_connection(DB_PATH)
    _ensure_profile_cols(conn)
    u = conn.execute("SELECT id, display_name, handle, is_public FROM users WHERE handle=?",
                     (handle,)).fetchone()
    if u:
        items = [dict(r) for r in conn.execute(
            "SELECT * FROM collection WHERE user_id=? ORDER BY species_display", (u["id"],)).fetchall()]
    conn.close()
    if not u or not u["is_public"]:
        return render_template("error.html", code=404,
                               msg="No public collection at that address."), 404
    items, portfolio = _collection_valued(items)
    stats = _collection_stats_for(u["id"])
    from normalize.common_names_map import COMMON_NAMES
    for it in items:
        it["common"] = COMMON_NAMES.get(it.get("species_key") or "", "")
    return render_template("public_profile.html", owner=dict(u), items=items,
                           portfolio=portfolio, stats=stats)


@app.route("/account")
@login_required
def account():
    """Account + Settings hub — the single place a user manages their name,
    password, public profile, alert email, and display prefs. Admins also get the
    site/market settings here (the old admin-only /settings gear was redundant with
    this page, so it was removed). load_settings() is global app config; only the
    admin-gated sections in the template read/write it."""
    return render_template("account.html", settings=load_settings(),
                           hide_private=_hide_private(),
                           alert_cats=_user_alert_categories(current_user_id()))


@app.route("/account/alerts", methods=["POST"])
@login_required
def account_alerts():
    """Save which market-alert categories the user opts into. Personal saved-search
    hits always alert; these toggles add the market firehose only if wanted."""
    cats = ",".join(sorted(c for c in request.form.getlist("cats") if c in _VALID_ALERT_CATS))
    conn = get_connection(DB_PATH)
    _ensure_profile_cols(conn)
    conn.execute("UPDATE users SET alert_categories=? WHERE id=?", (cats, current_user_id()))
    conn.commit()
    conn.close()
    flash("Alert preferences saved.", "success")
    return redirect(url_for("account"))


@app.route("/account/name", methods=["POST"])
@login_required
def account_name():
    """Save the user's real first/last name. PRIVATE — never shown publicly; the
    leaderboard/public profile keep using display_name. Only the user + an admin
    can see it. Not collected at signup by design."""
    conn = get_connection(DB_PATH)
    _ensure_profile_cols(conn)
    fn = (request.form.get("first_name") or "").strip()[:60] or None
    ln = (request.form.get("last_name") or "").strip()[:60] or None
    conn.execute("UPDATE users SET first_name=?, last_name=? WHERE id=?",
                 (fn, ln, current_user_id()))
    conn.commit()
    conn.close()
    flash("Name saved.", "success")
    return redirect(url_for("account"))


def _all_users_admin() -> list:
    """Admin user list with per-user data counts. Read-only. NEVER selects
    password_hash. PII: admin-only, never cached/blobbed."""
    conn = get_connection(DB_PATH)
    _ensure_profile_cols(conn)
    users = [dict(r) for r in conn.execute("""
        SELECT u.id, u.email, u.display_name, u.first_name, u.last_name,
               u.is_admin, u.is_public, u.handle, u.created_at,
               (SELECT COUNT(*) FROM collection c WHERE c.user_id=u.id) AS collection_count,
               (SELECT COUNT(*) FROM watchlist w WHERE w.user_id=u.id)  AS watchlist_count,
               (SELECT COUNT(*) FROM vendors v WHERE v.platform='private_seller' AND v.user_id=u.id) AS private_seller_count
        FROM users u
        ORDER BY u.created_at DESC, u.id DESC
    """).fetchall()]
    conn.close()
    return users


@app.route("/admin")
@admin_required
def admin():
    """Single admin hub — Users + Crawler on one page (replaces the separate
    Crawler and Users nav links). Vendor QA + site settings link out from here."""
    from crawl_report import get_speed_report
    speed = _crawl_state.get("speed") or get_speed_report(DB_PATH)
    return render_template("admin.html",
        users=_all_users_admin(),
        crawl_runs=get_crawl_summary(DB_PATH),
        speed=speed,
        finished_est=_fmt_eastern(speed.get("finished_at")) if speed else "")


@app.route("/admin/users")
@admin_required
def admin_users():
    """Kept for deep links; the Users table now lives on the /admin hub too."""
    return render_template("admin_users.html", users=_all_users_admin())


def _admin_user_or_404(conn, uid):
    u = conn.execute("SELECT id, email, display_name, first_name, last_name "
                     "FROM users WHERE id=?", (uid,)).fetchone()
    if not u:
        conn.close()
        abort(404)
    return dict(u)


@app.route("/admin/users/<int:uid>/collection")
@admin_required
def admin_user_collection(uid):
    conn = get_connection(DB_PATH)
    u = _admin_user_or_404(conn, uid)
    items = [dict(r) for r in conn.execute(
        "SELECT species_display, sex, quantity, size_notes, price_paid, acquired_date, "
        "source, notes FROM collection WHERE user_id=? ORDER BY species_display", (uid,)).fetchall()]
    conn.close()
    return render_template("admin_user_data.html", u=u, kind="Collection", items=items)


@app.route("/admin/users/<int:uid>/watchlist")
@admin_required
def admin_user_watchlist(uid):
    conn = get_connection(DB_PATH)
    u = _admin_user_or_404(conn, uid)
    items = [dict(r) for r in conn.execute(
        "SELECT species_display, sex, min_size, max_size, max_price, max_landed, notes "
        "FROM watchlist WHERE user_id=? ORDER BY species_display", (uid,)).fetchall()]
    conn.close()
    return render_template("admin_user_data.html", u=u, kind="Watchlist", items=items)


@app.route("/profile/save", methods=["POST"])
@login_required
def profile_save():
    conn = get_connection(DB_PATH)
    _ensure_profile_cols(conn)
    is_public = 1 if request.form.get("is_public") == "on" else 0
    handle = _slugify_handle(request.form.get("handle", ""))
    if is_public and not handle:
        conn.close()
        flash("Pick a handle for your public profile (letters, numbers, dashes).", "error")
        return redirect(url_for("settings"))
    if handle:
        clash = conn.execute("SELECT 1 FROM users WHERE handle=? AND id!=?",
                             (handle, current_user_id())).fetchone()
        if clash:
            conn.close()
            flash(f"The handle “{handle}” is taken — try another.", "error")
            return redirect(url_for("settings"))
    conn.execute("UPDATE users SET is_public=?, handle=? WHERE id=?",
                 (is_public, handle or None, current_user_id()))
    conn.commit()
    conn.close()
    _leaderboard_cache["data"] = None
    flash("Public profile updated." + (f" Live at /u/{handle}" if is_public and handle else ""),
          "success")
    return redirect(url_for("settings"))


@app.route("/collection/share", methods=["POST"])
@login_required
def collection_share():
    """One-click opt-in (from the Collection page) to share the collection on the
    public leaderboard. OFF by default — a collection is private unless the owner
    explicitly shares it. Auto-assigns a handle so sharing is a single click."""
    conn = get_connection(DB_PATH)
    _ensure_profile_cols(conn)
    share = request.form.get("share") == "on"
    if share:
        row = conn.execute("SELECT handle, display_name, email FROM users WHERE id=?",
                           (current_user_id(),)).fetchone()
        handle = row["handle"]
        if not handle:   # auto-generate a unique handle from name/email
            base = _slugify_handle(row["display_name"] or (row["email"] or "").split("@")[0]) or "keeper"
            handle, n = base, 1
            while conn.execute("SELECT 1 FROM users WHERE handle=? AND id!=?",
                               (handle, current_user_id())).fetchone():
                n += 1; handle = f"{base}-{n}"
        conn.execute("UPDATE users SET is_public=1, handle=? WHERE id=?", (handle, current_user_id()))
        msg = f"Your collection is now on the leaderboard — public at /u/{handle}."
    else:
        conn.execute("UPDATE users SET is_public=0 WHERE id=?", (current_user_id(),))
        msg = "Your collection is private — off the leaderboard."
    conn.commit()
    conn.close()
    _leaderboard_cache["data"] = None
    flash(msg, "success")
    return redirect(url_for("collection"))


def _vendor_qa_list():
    """Enriched website-vendor list for the QA table: platform, homepage,
    listing counts, latest crawl status. Shared by Sellers + Vendors pages."""
    from vendors import REGISTRY
    conn = get_connection(DB_PATH)
    rows = conn.execute("""
        SELECT ph.vendor_key AS vk, COUNT(*) AS n,
               SUM(CASE WHEN ph.availability!='out_of_stock' THEN 1 ELSE 0 END) AS instock
        FROM price_history ph
        WHERE ph.crawl_run_id IN (
            SELECT MAX(id) FROM crawl_runs
            WHERE status IN ('complete','partial') GROUP BY vendor_key)
        GROUP BY ph.vendor_key
    """).fetchall()
    conn.close()
    counts = {r["vk"]: dict(r) for r in rows}
    last = {}
    for r in get_crawl_summary(DB_PATH):   # newest-first; keep the newest
        last.setdefault(r["vendor_key"], r)
    out = []
    for vk in sorted(REGISTRY.keys()):
        cls = REGISTRY[vk]
        c = counts.get(vk) or {}
        lr = last.get(vk) or {}
        out.append({
            "key": vk,
            "name": getattr(cls, "VENDOR_NAME", vk),
            "platform": getattr(cls, "PLATFORM", ""),
            "homepage": _vendor_homepage(vk),
            "listings": c.get("n", 0),
            "instock": c.get("instock", 0),
            "status": lr.get("status", "never crawled"),
            "last": (lr.get("finished_at") or lr.get("started_at") or "")[:16],
        })
    return out


@app.route("/sellers")
def sellers():
    from vendors import REGISTRY
    vendor_list = sorted(REGISTRY.keys())
    last_crawl = {}
    for r in get_crawl_summary(DB_PATH):   # newest-first; keep the newest
        last_crawl.setdefault(r["vendor_key"], r)

    # Private sellers (imported lists) are PER-USER private: each account sees only
    # the sellers it uploaded — never another user's, never logged-out visitors'.
    from auth import current_user
    private_sellers = []
    if current_user() is not None:
        conn = get_connection(DB_PATH)
        try:
            private_sellers = [dict(r) for r in conn.execute("""
                SELECT vendor_key, vendor_name, base_url AS contact
                FROM vendors WHERE platform = 'private_seller' AND user_id = ?
                ORDER BY vendor_name
            """, (current_user_id(),)).fetchall()]
        except Exception:
            private_sellers = []
        conn.close()

    return render_template("sellers.html",
                           vendors=vendor_list, last_crawl=last_crawl,
                           private_sellers=private_sellers,
                           crawl_state=_crawl_state,
                           vendors_qa=_vendor_qa_list())


@app.route("/sellers/crawl", methods=["POST"])
@admin_required
def sellers_crawl():
    import crawl_lock
    # Cross-process guard: refuse if ANY crawl is running, incl. a CLI or the scheduled job.
    if _crawl_state["running"] or crawl_lock.is_active():
        origin = (crawl_lock.status().get("origin") or "another process")
        flash(f"A crawl is already running ({origin}). Wait for it to finish.", "error")
        return redirect(request.form.get("return_to") or url_for("history"))
    vendors_arg = request.form.get("vendors", "all")
    if vendors_arg == "all":
        from vendors import REGISTRY
        vendor_keys = list(REGISTRY.keys())
    else:
        vendor_keys = [v.strip() for v in vendors_arg.split(",")]
    t = threading.Thread(target=run_crawl_thread, args=(vendor_keys,), daemon=True)
    t.start()
    flash(f"Crawl started for {len(vendor_keys)} vendors", "success")
    return redirect(request.form.get("return_to") or url_for("history"))


@app.route("/sellers/delete/<vendor_key>", methods=["POST"])
@login_required
def sellers_delete(vendor_key):
    """Delete an imported private-seller list. Only the OWNER (or an admin) may
    delete it; never a website vendor."""
    from vendors import REGISTRY
    if vendor_key in REGISTRY:
        flash("That's a website vendor and can't be deleted.", "error")
        return redirect(url_for("sellers"))
    conn = get_connection(DB_PATH)
    _own = conn.execute("SELECT user_id FROM vendors WHERE vendor_key=?", (vendor_key,)).fetchone()
    _u = current_user()
    if not (_u and (_u["is_admin"] or (_own and _own["user_id"] == current_user_id()))):
        conn.close()
        abort(403)
    runs = [r["id"] for r in conn.execute(
        "SELECT id FROM crawl_runs WHERE vendor_key=?", (vendor_key,)).fetchall()]
    if runs:
        ph = ",".join("?" * len(runs))
        conn.execute(f"DELETE FROM price_history WHERE crawl_run_id IN ({ph})", runs)
    conn.execute("DELETE FROM price_history WHERE vendor_key=?", (vendor_key,))
    conn.execute("DELETE FROM crawl_runs WHERE vendor_key=?", (vendor_key,))
    conn.execute("DELETE FROM vendors WHERE vendor_key=?", (vendor_key,))
    conn.commit()
    conn.close()
    _snapshot_cache["data"] = None
    flash(f"Deleted imported list: {vendor_key}", "success")
    return redirect(url_for("sellers"))


@app.route("/sellers/import", methods=["POST"])
@login_required
def sellers_import():
    # Private-seller import is available to ANY registered user. What they upload
    # is theirs alone (owned by their user_id, visible only to them).
    seller_name = request.form.get("seller_name","").strip()
    raw_text    = request.form.get("raw_text","").strip()
    if not seller_name or not raw_text:
        flash("Seller name and list text are required", "error")
        return redirect(url_for("sellers"))
    try:
        # Check if this is a versioned update — scoped to THIS user's own sellers.
        conn = get_connection(DB_PATH)
        prev = conn.execute("""
            SELECT COUNT(*) as n, MAX(observed_at) as last_seen
            FROM price_history ph
            JOIN vendors v ON ph.vendor_key = v.vendor_key
            WHERE v.vendor_name = ? AND v.platform = 'private_seller' AND v.user_id = ?
        """, (seller_name, current_user_id())).fetchone()
        is_update = (prev["n"] or 0) > 0
        conn.close()

        from tools.import_seller import parse_with_regex, insert_listings
        listings = parse_with_regex(raw_text)
        if not listings:
            flash("No listings could be parsed from the text", "error")
            return redirect(url_for("sellers"))

        contact = request.form.get("contact", "").strip()
        count = insert_listings(listings, seller_name, db_path=DB_PATH,
                                contact=contact, user_id=current_user_id())
        _snapshot_cache["data"] = None  # invalidate

        if is_update:
            flash(f"Updated: {count} listings imported from {seller_name} (versioned update — history preserved)", "success")
        else:
            flash(f"Imported {count} listings from {seller_name}", "success")
    except Exception as e:
        flash(f"Import error: {e}", "error")
    return redirect(url_for("sellers"))


@app.route("/species")
def species_search():
    query   = request.args.get("q", "").strip()
    # Defensive: strip a trailing "(Common Name)" so a legacy/pasted
    # "Genus species (Common)" value still matches (the combobox navigates by key,
    # so this only guards free-text and old links).
    import re as _re_q
    query = _re_q.sub(r"\s*\([^)]*\)\s*$", "", query).strip()
    page    = request.args.get("page", 1, type=int)
    f_genus = request.args.get("genus", "")
    f_orig  = request.args.get("origin", "")
    f_tier  = request.args.get("tier", "")
    f_band  = request.args.get("band", "")
    f_hem   = request.args.get("hem", "")
    f_hab   = request.args.get("habitat", "")
    f_tsize = request.args.get("tsize", "")
    f_temp  = request.args.get("temp", "")
    f_exp   = request.args.get("exp", "")
    f_clim  = request.args.get("climate", "")
    f_instock = request.args.get("instock", "")   # "1" → only species in stock now
    sort_by = request.args.get("sort", "name")

    catalog = get_species_browse()
    if query:
        ql = query.lower()
        catalog = [s for s in catalog
                   if ql in s["display"].lower() or ql in (s["common"] or "").lower()
                   or ql in s["key"]]
    # In-Stock-Only: a base filter (like the search box) — narrows BOTH the facet
    # option counts and the results to species with ≥1 live listing as of last scrape.
    if f_instock:
        catalog = [s for s in catalog if (s.get("live") or 0) > 0]

    # A facet's own option counts must reflect every OTHER selected facet (the
    # intersection) — otherwise "$250+" showed its global 63 even after Advanced was
    # picked, when only 4 species are both. So each facet is counted over the catalog
    # filtered by all active facets EXCEPT itself.
    _FACET_FILTERS = [
        ("genus", f_genus), ("origin", f_orig), ("rarity_tier", f_tier),
        ("price_band", f_band), ("hemisphere", f_hem), ("habitat", f_hab),
        ("t_size", f_tsize), ("temperament", f_temp), ("experience", f_exp),
        ("climate", f_clim),
    ]

    def _apply_facets(items, exclude_field=None):
        out = items
        for field, val in _FACET_FILTERS:
            if val and field != exclude_field:
                out = [s for s in out if s.get(field) == val]
        return out

    def facet_counts(field):
        c = {}
        for s in _apply_facets(catalog, exclude_field=field):
            v = s.get(field)
            if v:
                c[v] = c.get(v, 0) + 1
        return c
    from normalize.genus_meta import PRICE_BAND_ORDER
    # Rarity always renders in linear scale order (rarest → most common), never by
    # count, so the scale reads the same everywhere it appears.
    _TIER_ORDER = ["Mythic", "Legendary", "Rare", "Uncommon", "Common", "Ubiquitous"]
    # Trait facets render in a meaningful order (not by count).
    _ORD = {
        "hemisphere":  ["New World", "Old World"],
        "habitat":     ["Terrestrial", "Arboreal", "Fossorial", "Semi-arboreal"],
        "t_size":      ["Dwarf", "Medium", "Large"],
        "temperament": ["Docile", "Skittish", "Defensive"],
        "experience":  ["Beginner", "Intermediate", "Advanced"],
        "climate":     ["Tropical", "Temperate", "Arid"],
    }
    def ordered(field):
        order = _ORD[field]
        return sorted(facet_counts(field).items(),
                      key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)
    facets = {
        "genus":  sorted(facet_counts("genus").items(), key=lambda kv: -kv[1])[:40],
        "origin": sorted(facet_counts("origin").items(), key=lambda kv: -kv[1]),
        "tier":   sorted(facet_counts("rarity_tier").items(),
                         key=lambda kv: _TIER_ORDER.index(kv[0]) if kv[0] in _TIER_ORDER else 99),
        "band":   sorted(facet_counts("price_band").items(),
                         key=lambda kv: PRICE_BAND_ORDER.index(kv[0]) if kv[0] in PRICE_BAND_ORDER else 99),
        "hemisphere":  ordered("hemisphere"),
        "habitat":     ordered("habitat"),
        "t_size":      ordered("t_size"),
        "temperament": ordered("temperament"),
        "experience":  ordered("experience"),
        "climate":     ordered("climate"),
    }

    matched = _apply_facets(catalog)   # all active facets applied (intersection)

    # Direction toggle: each sort has a natural default (A-Z, priciest, rarest,
    # most-listed). Clicking the active sort again flips it.
    _DEFAULT_DIR = {"name": "asc", "price": "desc", "rarity": "desc", "listings": "desc"}
    direction = request.args.get("dir", "")
    if direction not in ("asc", "desc"):
        direction = _DEFAULT_DIR.get(sort_by, "asc")
    # Rarity sorts by TIER first (all Mythic, then Legendary, …) — the named
    # tier is a percentile rank, so sorting by the raw 1-10 score mixed tiers.
    _RARITY_RANK = {"Mythic": 5, "Legendary": 4, "Rare": 3, "Uncommon": 2,
                    "Common": 1, "Ubiquitous": 0}
    keyfn = {
        "name":   lambda s: s["display"].lower(),
        "price":  lambda s: s.get("min_p") or 9e9,
        "rarity": lambda s: (_RARITY_RANK.get(s.get("rarity_tier"), -1), s.get("rarity_score") or 0),
        "listings": lambda s: s.get("live") or 0,
    }.get(sort_by, lambda s: s["display"].lower())
    matched = sorted(matched, key=keyfn, reverse=(direction == "desc"))

    per = 50   # was 75 → lighter tile grid (each tile carries a sparkline SVG),
               # snappier browse/paint on mobile.
    total = len(matched)
    pages = max(1, (total + per - 1) // per)
    page = max(1, min(page, pages))
    tiles = matched[(page - 1) * per: page * per]
    active = {"genus": f_genus, "origin": f_orig, "tier": f_tier, "band": f_band,
              "hem": f_hem, "habitat": f_hab, "tsize": f_tsize, "temp": f_temp,
              "exp": f_exp, "climate": f_clim, "instock": f_instock,
              "sort": sort_by, "dir": direction, "q": query}
    rarity_legend = _cached_rarity_legend()
    return render_template("species.html", tiles=tiles, query=query,
                           page=page, pages=pages, total=total, page_base=_page_base(),
                           facets=facets, active=active, rarity_legend=rarity_legend)


@app.route("/species/<path:species_key>")
def species_detail(species_key):
    history = get_species_price_history(species_key, db_path=DB_PATH)
    # Per-user private-seller isolation: hide every private seller the current
    # user doesn't own from BOTH the price-history chart and the live listings.
    _hidden_priv = {vk for vk, owner in get_private_owner_map(DB_PATH).items()
                    if owner != current_user_id()}
    if _hidden_priv:
        history = [h for h in history if h.get("vendor_key") not in _hidden_priv]
    snap = _visible_to_user(get_snapshot())
    current = [l for l in snap if (l.get("scientific_name_key") or "") == species_key]
    current = _apply_private_pref(current)
    # Private sellers are account-only: scrub them from EVERY data path on this
    # card (history/chart/inferred sales), not just the "Available now" table,
    # so a logged-out visitor can't see their name or prices anywhere.
    _hide_priv = _hide_private()
    _priv_keys = get_private_seller_keys(DB_PATH) if _hide_priv else set()
    if _hide_priv:
        history = [h for h in history if h.get("vendor_key") not in _priv_keys]
    # No listings, no history → a stale/garbage key. Show a clean 404 instead of a
    # broken empty shell (which reads as a dead link).
    if not history and not current:
        return render_template("error.html", code=404,
                               msg="We don't have data for that species — it may have "
                                   "sold out and left our latest crawls."), 404
    from normalize.common_names_map import pick_common
    _candidates = list({h.get("common_name") for h in history if h.get("common_name")})
    common = pick_common(species_key, _candidates)
    scr = get_size_class_rarity()   # cached: was a ~0.9s whole-DB scan per card

    # Market microstructure (StockX-style stat strip / range bar / Market Price)
    stats = get_market_stats().get(species_key) or {}
    # Species-level rarity score + percentile-ranked named tier (from stats)
    rarity_score = stats.get("rarity_score")
    # Inferred recent sales (honest sold-price proxy)
    try:
        sales = get_inferred_sales().get(species_key, [])   # cached: was ~1.4s per card
    except Exception:
        sales = []
    if _hide_priv:
        sales = [s for s in sales
                 if (s.get("vendor_key") or s.get("vendor")) not in _priv_keys]
    genus = species_key.split()[0] if species_key.split() else ""
    from normalize.traits import trait_badges
    traits = trait_badges(species_key)
    # Downsample the inline chart payload — the SVG is ~760px wide, so hundreds of
    # points aren't visible. Evenly decimate (keep the last point) to bound the
    # inline JSON + client parse for heavily-traded species. `history` stays full
    # for the all-time-low fallback + common-name candidates above.
    chart_history = history
    if len(history) > 400:
        step = len(history) / 400.0
        idxs = sorted({int(i * step) for i in range(400)} | {len(history) - 1})
        chart_history = [history[i] for i in idxs]
    return render_template("species_detail.html",
                           traits=traits,
                           species_key=species_key,
                           display=_display_from_key(species_key),
                           common=common,
                           history=history,
                           chart_history=chart_history,
                           current=current,
                           size_class_rarity=scr,
                           stats=stats,
                           rarity_score=rarity_score,
                           inferred_sales=sales,
                           genus=genus,
                           owned=(species_key in _req_owned()))


@app.route("/family/<genus>")
def family(genus):
    """Genus landing page: all species in the genus + a family price index."""
    import statistics as _stats
    g = (genus or "").strip().lower()
    tiles = [s for s in get_species_browse() if (s.get("genus") or "").lower() == g]
    tiles.sort(key=lambda s: s["display"].lower())
    mkts = [s["market_price"] for s in tiles if s.get("market_price")]
    lows = [s["min_p"] for s in tiles if s.get("min_p")]
    index = {
        "species": len(tiles),
        "listings": sum(s.get("live") or 0 for s in tiles),   # true live in-stock count
        "median_market": round(_stats.median(mkts), 0) if mkts else None,
        "cheapest": round(min(lows), 0) if lows else None,
        "origin": tiles[0]["origin"] if tiles else "",
    }
    return render_template("family.html", genus=g.capitalize(),
                           tiles=tiles, index=index)


def _fmt_eastern(iso_utc: str) -> str:
    """Format a UTC ISO timestamp as US Eastern time with the right abbreviation
    (EDT in summer, EST in winter). No external tz dependency — uses the US DST rule
    (2nd Sun Mar → 1st Sun Nov). Approximate at the transition hour; fine for display."""
    if not iso_utc:
        return ""
    from datetime import datetime, timedelta
    s = str(iso_utc).replace("T", " ")
    dt = None
    for length, fmt in ((19, "%Y-%m-%d %H:%M:%S"), (16, "%Y-%m-%d %H:%M")):
        try:
            dt = datetime.strptime(s[:length], fmt)
            break
        except ValueError:
            continue
    if dt is None:
        return str(iso_utc)

    def nth_sunday(year, month, n):
        d = datetime(year, month, 1)
        return d + timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))

    dst_start = nth_sunday(dt.year, 3, 2) + timedelta(hours=2)
    dst_end = nth_sunday(dt.year, 11, 1) + timedelta(hours=2)
    is_dst = dst_start <= dt < dst_end
    eastern = dt + timedelta(hours=(-4 if is_dst else -5))
    return eastern.strftime("%Y-%m-%d %H:%M") + (" EDT" if is_dst else " EST")


@app.route("/history")
@admin_required
def history():
    crawl_runs = get_crawl_summary(DB_PATH)
    from crawl_report import get_speed_report
    speed = _crawl_state.get("speed") or get_speed_report(DB_PATH)
    finished_est = _fmt_eastern(speed.get("finished_at")) if speed else ""
    return render_template("history.html", crawl_runs=crawl_runs, speed=speed,
                           finished_est=finished_est)


# ── Vendors admin (QA: does our data match the vendor's real site?) ─────────
# Intended admin-only once auth lands; for now it's a plain page.

@app.route("/vendors")
@admin_required
def vendors_admin():
    # Standalone QA page kept as a deep-link target; the same table is also
    # embedded at the bottom of the Sellers/Vendors page.
    vendors = _vendor_qa_list()
    total_listings = sum(v["listings"] for v in vendors)

    # ── Source-policy panel: per-vendor CB/WC/unknown + what we may claim ────
    from normalize.source_type import VENDOR_SOURCE_POLICY
    snap = get_snapshot()
    pol_rows = get_vendor_policy_rows(DB_PATH)
    agg = {}
    for l in snap:
        vk = l.get("vendor_key")
        a = agg.setdefault(vk, {"cb": 0, "wc": 0, "unk": 0, "stated_wc": 0})
        st = l.get("source_type") or "unknown"
        if st == "unknown":
            a["unk"] += 1
        elif st == "WC":
            a["wc"] += 1
            if l.get("source_provenance") == "stated":
                a["stated_wc"] += 1
        else:
            a["cb"] += 1
    srcs = []
    for vk, a in sorted(agg.items(), key=lambda kv: -kv[1]["unk"]):
        row = pol_rows.get(vk, {})
        srcs.append({
            "key": vk, **a,
            "total": a["cb"] + a["wc"] + a["unk"],
            "policy": row.get("policy", ""),
            "note": row.get("note", ""),
            "scraped": VENDOR_SOURCE_POLICY.get(vk, ""),
            # a vendor that has NEVER stated WC can safely be confirmed CB-only
            "confirmable": a["stated_wc"] == 0 and a["unk"] > 0,
        })
    marked = sum(1 for l in snap if (l.get("source_type") or "unknown") != "unknown")
    src_summary = {"total": len(snap), "marked": marked,
                   "pct": round(marked / len(snap) * 100, 1) if snap else 0}

    return render_template("vendors_admin.html", vendors=vendors,
                           total_listings=total_listings,
                           srcs=srcs, src_summary=src_summary)


@app.route("/vendors/<vendor_key>")
def vendor_detail(vendor_key):
    from vendors import REGISTRY
    cls = REGISTRY.get(vendor_key)
    conn = get_connection(DB_PATH)
    mx = conn.execute("""SELECT MAX(id) m FROM crawl_runs
                         WHERE vendor_key=? AND status IN ('complete','partial')""",
                      (vendor_key,)).fetchone()
    listings = []
    run_when = ""
    if mx and mx["m"]:
        run = conn.execute("SELECT finished_at, started_at FROM crawl_runs WHERE id=?",
                           (mx["m"],)).fetchone()
        run_when = (run["finished_at"] or run["started_at"] or "")[:16] if run else ""
        listings = [dict(r) for r in conn.execute("""
            SELECT scientific_name, scientific_name_key, common_name, size_text,
                   sex, price_usd, availability, product_url, raw_title
            FROM price_history WHERE crawl_run_id=?
            ORDER BY availability='out_of_stock', scientific_name_key, price_usd
        """, (mx["m"],)).fetchall()]
    conn.close()
    _attach_clean_names(listings)   # clean "Genus species" + common, like Deals
    instock = sum(1 for l in listings if l.get("availability") != "out_of_stock")
    return render_template("vendor_detail.html",
                           vendor_key=vendor_key,
                           name=getattr(cls, "VENDOR_NAME", vendor_key) if cls else vendor_key,
                           homepage=_vendor_homepage(vendor_key),
                           platform=getattr(cls, "PLATFORM", "") if cls else "",
                           listings=listings, instock=instock, run_when=run_when)


# ── Alerts + saved searches (Keepa-style retention loop) ────────────────────

@app.route("/alerts")
@login_required
def alerts():
    from analytics.alerts import load_feed, load_saved_searches, mark_all_read
    uid = current_user_id()
    cats = _user_alert_categories(uid)
    feed = load_feed(200, user_id=uid, categories=cats)
    searches = load_saved_searches(user_id=uid)
    if request.args.get("read") == "1":
        mark_all_read(user_id=uid, categories=cats)
        return redirect(url_for("alerts"))
    return render_template("alerts.html", feed=feed, searches=searches,
                           alert_cats=cats)


@app.route("/alerts/search/add", methods=["POST"])
@login_required
def alerts_search_add():
    from analytics.alerts import add_saved_search
    name = request.form.get("name", "").strip()
    crit = {
        "species":    request.form.get("species", "").strip(),
        "genus":      request.form.get("genus", "").strip(),
        "sex":        request.form.get("sex", "").strip(),
        "max_price":  request.form.get("max_price", type=float),
        "min_rarity": request.form.get("min_rarity", type=int),
        "deal":       request.form.get("deal", "").strip(),
    }
    crit = {k: v for k, v in crit.items() if v}
    if not crit:
        flash("Add at least one filter to save a search.", "error")
        return redirect(url_for("alerts"))
    add_saved_search(name, crit, notify=True, now=datetime.now().isoformat(),
                     user_id=current_user_id())
    flash(f"Saved search '{name or 'unnamed'}' — you'll be alerted on new matches.", "success")
    return redirect(url_for("alerts"))


@app.route("/alerts/search/remove/<int:sid>", methods=["POST"])
@login_required
def alerts_search_remove(sid):
    from analytics.alerts import remove_saved_search
    remove_saved_search(sid, user_id=current_user_id())
    flash("Saved search removed.", "success")
    return redirect(url_for("alerts"))


@app.route("/api/alerts-unread")
def api_alerts_unread():
    try:
        from analytics.alerts import unread_count
        uid = current_user_id()
        return jsonify({"unread": unread_count(user_id=uid,
                                               categories=_user_alert_categories(uid))})
    except Exception:
        return jsonify({"unread": 0})


@app.route("/settings", methods=["GET","POST"])
@admin_required
def settings():
    # The settings UI now lives on /account (the gear was redundant with the name
    # link). Keep this endpoint for the POST (admin site-settings form still targets
    # it); a GET just redirects to the consolidated page.
    if request.method == "GET":
        return redirect(url_for("account"))
    if request.method == "POST":
        # digest_path is NOT user-writable: /digest reads it, so accepting it from a
        # form was an arbitrary-file-read hole. Keep it fixed here.
        data = {
            "dest_zip":       request.form.get("dest_zip","72712"),
            "notify_email":   request.form.get("notify_email",""),
            "smtp_host":      request.form.get("smtp_host","smtp.gmail.com"),
            "smtp_port":      int(request.form.get("smtp_port",587)),
            "smtp_user":      request.form.get("smtp_user",""),
            "smtp_pass":      request.form.get("smtp_pass",""),
            "digest_path":    "output/daily_digest.txt",
        }
        save_settings(data)
        flash("Settings saved", "success")
        return redirect(url_for("account"))
    return redirect(url_for("account"))



# ── Vendor homepage lookup ─────────────────────────────────────────────────
_homepage_cache: dict[str, str] = {}


def _vendor_homepage(vendor_key: str) -> str:
    """Best homepage URL for a vendor: the manual map, else the scraper's
    BASE_URL from the registry, else the private-seller contact/base_url."""
    if not vendor_key:
        return ""
    if vendor_key in _homepage_cache:
        return _homepage_cache[vendor_key]
    url = VENDOR_HOMEPAGES.get(vendor_key, "")
    if not url:
        try:
            from vendors import REGISTRY
            cls = REGISTRY.get(vendor_key)
            url = getattr(cls, "BASE_URL", "") if cls else ""
        except Exception:
            url = ""
    _homepage_cache[vendor_key] = url or ""
    return _homepage_cache[vendor_key]


VENDOR_HOMEPAGES = {
    "urban_tarantulas":    "https://www.urbantarantulas.com",
    "jamies_tarantulas":   "https://www.jamiesontheweb.com",
    "fear_not_tarantulas": "https://fearnottarantulas.com",
    "spider_room":         "https://thespiderroom.com",
    "marshall_arachnids":  "https://marshallarachnids.com",
    "tydye_exotics":       "https://tydyeexotic.com",
    "fang_hub":            "https://www.fanghubtarantulas.com",
    "ghostys_tarantulas":  "https://ghostystarantulas.com",
    "exotics_unlimited":   "https://exoticsunlimitedusa.com",
    "hardcore_arachnids":  "https://hardcorearachnids.com",
    "wonderland_exotics":  "https://www.wonderlandexoticsllc.com",
    "eight_deadly_sins":   "https://www.eightdeadlysins.net",
    "micro_wilderness":    "https://www.microwilderness.com",
    "spider_shoppe":       "https://spidershoppe.com",
    "arachnoeden":         "https://arachnoeden.org",
}


def _site_counts(snap=None) -> dict:
    """Canonical SITE-ONLY vendor + listing counts (private sellers excluded).
    One source of truth so the dashboard header and the What-is-FangTrack page
    always agree — both count crawled websites, never imported private lists."""
    from vendors import REGISTRY
    if snap is None:
        snap = get_snapshot()
    site = [l for l in snap if l.get("vendor_key") in REGISTRY]
    vendors = len({l.get("vendor_key") for l in site})
    return {"vendor_count": vendors or len(REGISTRY), "listing_count": len(site)}


def _live_counts() -> dict:
    """Alias kept for the About/guide templates."""
    return _site_counts()


@app.route("/transparency")
def transparency():
    return render_template("transparency.html", **_live_counts())


@app.route("/guide")
def guide():
    return render_template("guide.html", **_live_counts())


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/admin/discounts")
@admin_required
def admin_discounts():
    conn = get_connection(DB_PATH)
    rows = [dict(r) for r in conn.execute("""
        SELECT id, vendor_key, code, discount_type, discount_value, is_verified,
               is_active, source_context, source_url, scraped_at
        FROM discount_codes
        ORDER BY vendor_key, is_verified DESC, discount_value DESC, code
    """).fetchall()]
    conn.close()
    # Group per vendor so the admin sees every code a seller has, together.
    by_vendor: dict[str, list] = {}
    for c in rows:
        by_vendor.setdefault(c["vendor_key"], []).append(c)
    grouped = sorted(by_vendor.items())
    from vendors import REGISTRY
    return render_template("admin_discounts.html", codes=rows, grouped=grouped,
                           vendors=sorted(REGISTRY.keys()))


@app.route("/admin/discounts/action", methods=["POST"])
@admin_required
def admin_discounts_action():
    action = request.form.get("action")
    cid = request.form.get("id", type=int)
    conn = get_connection(DB_PATH)
    if action == "verify" and cid:
        conn.execute("UPDATE discount_codes SET is_verified=1, is_active=1 WHERE id=?", (cid,))
    elif action == "unverify" and cid:
        conn.execute("UPDATE discount_codes SET is_verified=0 WHERE id=?", (cid,))
    elif action == "deactivate" and cid:
        conn.execute("UPDATE discount_codes SET is_active=0 WHERE id=?", (cid,))
    elif action == "delete" and cid:
        conn.execute("DELETE FROM discount_codes WHERE id=?", (cid,))
    elif action == "purge_zero":
        # Remove scraped noise: codes with no real saving, but KEEP the
        # informational sale flags (SITEWIDE SALE / HOLIDAY SALE / BOGO).
        conn.execute("""
            DELETE FROM discount_codes
            WHERE (discount_value IS NULL OR discount_value <= 0)
              AND COALESCE(discount_type,'') != 'info'
              AND code NOT IN ('SITEWIDE SALE','HOLIDAY SALE','BOGO')
        """)
    elif action == "add":
        vk = request.form.get("vendor_key", "").strip()
        code = request.form.get("code", "").strip().upper()
        val = request.form.get("discount_value", type=float)
        dtype = request.form.get("discount_type", "pct")
        if vk and code and val:
            from database.db import upsert_discount_code
            upsert_discount_code(vendor_key=vk, code=code, discount_type=dtype,
                                 discount_value=val, source_context="Added by admin",
                                 is_verified=1, db_path=DB_PATH)
    conn.commit()
    conn.close()
    _snapshot_cache["data"] = None
    flash("Discount codes updated.", "success")
    return redirect(url_for("admin_discounts"))


def _init_submissions(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind         TEXT NOT NULL,     -- vendor | bug | idea
            vendor_name  TEXT,
            vendor_url   TEXT,
            message      TEXT NOT NULL,
            contact      TEXT,
            status       TEXT DEFAULT 'new',
            created_at   TEXT DEFAULT (datetime('now'))
        );
    """)


@app.route("/submit")
def submit():
    conn = get_connection(DB_PATH)
    _init_submissions(conn)
    recent = [dict(r) for r in conn.execute(
        "SELECT kind, vendor_name, message, created_at FROM submissions "
        "ORDER BY id DESC LIMIT 15").fetchall()]
    conn.close()
    return render_template("submit.html", recent=recent)


@app.route("/submit/save", methods=["POST"])
def submit_save():
    kind = request.form.get("kind", "idea").strip()
    message = request.form.get("message", "").strip()
    vendor_name = request.form.get("vendor_name", "").strip()
    vendor_url = request.form.get("vendor_url", "").strip()
    contact = request.form.get("contact", "").strip()

    if kind == "vendor" and not (vendor_name or vendor_url):
        flash("Please enter the vendor's name or website.", "error")
        return redirect(url_for("submit"))
    if not message and kind != "vendor":
        flash("Please describe your report or idea.", "error")
        return redirect(url_for("submit"))

    conn = get_connection(DB_PATH)
    _init_submissions(conn)
    conn.execute(
        "INSERT INTO submissions (kind, vendor_name, vendor_url, message, contact) "
        "VALUES (?,?,?,?,?)",
        (kind, vendor_name or None, vendor_url or None,
         message or f"Vendor suggestion: {vendor_name} {vendor_url}".strip(), contact or None))
    conn.commit()
    conn.close()
    label = {"vendor": "Vendor suggestion", "bug": "Error report",
             "idea": "Improvement idea"}.get(kind, "Submission")
    # Notify the FangTrack team so submissions don't sit unseen in the DB. Degrades
    # gracefully: if SMTP isn't configured yet it just logs (submission is already
    # saved). Once SMTP is wired this lands in mike@fangtrack.com.
    try:
        notify_to = (os.environ.get("FANGTRACK_NOTIFY_EMAIL")
                     or os.environ.get("NOTIFY_EMAIL") or "mike@fangtrack.com")
        body = (f"New {label.lower()} on FangTrack\n\n"
                f"Type:    {kind}\n"
                f"Vendor:  {vendor_name or '—'}\n"
                f"URL:     {vendor_url or '—'}\n"
                f"Contact: {contact or '—'}\n\n"
                f"Message:\n{message or '—'}\n")
        send_email(notify_to, f"[FangTrack] {label}", body)
    except Exception as e:
        logger.warning(f"submission email skipped (submission still saved): {e}")
    flash(f"{label} received — thank you! We review these regularly.", "success")
    return redirect(url_for("submit"))


@app.route("/digest")
@admin_required
def digest():
    settings = load_settings()
    p = Path(settings.get("digest_path","output/daily_digest.txt"))
    content = p.read_text(encoding="utf-8") if p.exists() else "No digest generated yet. Run a crawl first."
    return render_template("digest.html", content=content,
                           digest_path=str(p), settings=settings)


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.route("/api/crawl-status")
def api_crawl_status():
    import crawl_lock
    lock = crawl_lock.status()
    # `active` is the cross-process truth (any origin); `running` stays the in-process view.
    return jsonify({**_crawl_state, "active": lock["active"], "origin": lock.get("origin")})


@app.route("/api/snapshot-stats")
def api_snapshot_stats():
    snap = get_snapshot()
    return jsonify({
        "total":   len(snap),
        "fire":    sum(1 for l in snap if l.get("is_fire_deal")),
        "gem2":    sum(1 for l in snap if l.get("deal_rating")=="💎💎"),
        "females": sum(1 for l in snap if l.get("sex")=="F"),
    })


@app.route("/api/trigger-digest", methods=["POST"])
@login_required
def api_trigger_digest():
    snap = get_snapshot()
    init_watchlist_tables(DB_PATH)
    hits_raw = check_watchlist(snap, DB_PATH)
    _write_digest(snap, hits_raw)
    return jsonify({"ok": True, "hits": len(hits_raw)})


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import webbrowser

    # Init DB tables
    init_db(DB_PATH)
    init_discount_tables(DB_PATH)
    init_watchlist_tables(DB_PATH)

    # Create collection table if needed
    conn = get_connection(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS collection (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            species_key TEXT NOT NULL,
            species_display TEXT NOT NULL,
            sex TEXT,
            quantity INTEGER DEFAULT 1,
            size_notes TEXT,
            notes TEXT,
            added_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    # Backfill the per-user columns now that collection/watchlist exist (see wsgi.py).
    import auth
    auth.init_auth_tables()

    os.makedirs("output", exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    print("\n" + "="*55)
    print("  🕷  Tarantula Market Tracker")
    print("  Opening at http://localhost:5000")
    print("  Press Ctrl+C to stop")
    print("="*55 + "\n")

    threading.Timer(1.5, lambda: webbrowser.open("http://localhost:5000")).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("FANGTRACK_PORT", 5000)),
            debug=False, use_reloader=False)
