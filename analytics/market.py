"""
Market microstructure analytics — the StockX/Keepa/TCG "market data" layer.

One reusable pass over price_history that produces, per canonical species:

  lowest_ask        current cheapest in-stock listing (what StockX calls Lowest Ask)
  all_time_low      cheapest price ever recorded
  all_time_high     most expensive price ever recorded
  market_price      trimmed median of recent asks (TCGplayer "Market Price")
  median_all        plain median across all history
  low_90d/high_90d  90-day price range (for the 52-week-style range bar)
  listings_live_now  in-stock listings in the latest run per vendor
  vendors_live       distinct vendors offering it right now
  vendors_all        distinct vendors that have ever listed it (liquidity)
  listings_90d       observation count in the last 90 days (liquidity)
  first_seen/last_seen
  spark              downsampled [ [ymd, price], ... ] daily-median series
  trend              rising | falling | stable | new  (30-day velocity)
  trend_pct          % per 30 days
  inferred_sales     listings that vanished near a price between crawls
                     ("recently taken at ~$X") — an honest sold-price proxy

Everything degrades gracefully with only one crawl of history and sharpens as
the daily 5 AM crawls accumulate. Nothing here fabricates data we don't have —
"Lowest Ask" is labelled as an ask, inferred sales are labelled as inferred.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone
from pathlib import Path

from database.db import get_connection, DB_PATH

# The identity of a single sellable listing = its product page AND its specific
# variant (size/sex/option). A Shopify product URL is shared across all its
# variants, so matching on URL alone collapses a $50 sling and a $3500 adult
# female into one "listing" and invents huge price swings. This distinguishes
# them, so price-drop / back-in-stock / sold tracking follows the same item.
_IDENT_SQL = ("COALESCE(scientific_name_key,'')||'¦'||product_url||'¦'||"
              "COALESCE(variant_name,'')||'¦'||COALESCE(size_text,'')||'¦'||"
              "COALESCE(sex,'')")


# ── Rarity tier presentation (name + colour) ────────────────────────────────
# The rarity SCORE (1-10) comes from scoring/rarity.py; this maps it to a
# TCG-style named, coloured tier. Colours are NOT defined here — theme.py is the
# single source of truth (see theme.RARITY_TIERS). Derived so they can't drift.
from theme import RARITY_TIERS as _THEME_TIERS, TIER_BANDS as _THEME_BANDS

RARITY_TIERS = {
    score: (name, t["css"])
    for name, t in _THEME_TIERS.items()
    for score in t["scores"]
}


def rarity_tier(score) -> tuple[str, str]:
    """(tier_name, css_class) for a 1-10 rarity score; ('', '') if none."""
    try:
        return RARITY_TIERS[int(score)]
    except (TypeError, ValueError, KeyError):
        return ("", "")


# Percentile bands for the NAMED rarity tier (a real TCG pyramid). The numeric
# 1-10 rarity score stays untouched; this only decides the label/colour, ranked
# across the whole catalog so "Mythic" is genuinely the apex, not a quarter of it.
# Derived from theme.py — the single source of truth.
_TIER_BANDS = _THEME_BANDS


def catalog_rarity_tiers(db_path: Path = DB_PATH) -> dict[str, dict]:
    """Assign each species a percentile-ranked rarity tier across the catalog.

    Rank key = (rarity score desc, fewer vendors ever, fewer observations) so
    genuinely singular species float to the apex and ties break on real
    scarcity signals rather than arbitrarily. Returns
    {key: {"score":int, "tier":str, "tier_class":str}}.
    """
    try:
        from scoring.rarity import compute_all_rarity
        rd = compute_all_rarity(db_path)
    except Exception:
        return {}
    from normalize.livestock import GENUS_SET
    items = [(k, v) for k, v in rd.items()
             if k.split() and k.split()[0] in GENUS_SET]
    # rarest first
    items.sort(key=lambda kv: (-(kv[1].score or 0), kv[1].vendor_count or 0,
                               kv[1].obs_count or 0))
    n = len(items) or 1
    out: dict[str, dict] = {}
    for i, (k, v) in enumerate(items):
        pct = (i + 1) / n
        for thr, name, cls in _TIER_BANDS:
            if pct <= thr:
                out[k] = {"score": v.score, "tier": name, "tier_class": cls}
                break
    return out


# Plain-English meaning for each named tier, in rank order (rarest first).
_TIER_MEANING = [
    ("Mythic",     "r-mythic", "rarest 5%",  "Almost never listed — single-source, grail-tier."),
    ("Legendary",  "r-veryr",  "next 10%",   "Very hard to find; a lucky-to-see-in-stock species."),
    ("Rare",       "r-rare",   "next 15%",   "Uncommon in the trade — a few sellers, sells fast."),
    ("Uncommon",   "r-uncomm", "next 25%",   "Around, but you'll shop a handful of sellers to find it."),
    ("Common",     "r-common", "next 25%",   "Widely carried — most well-stocked shops have it."),
    ("Ubiquitous", "r-ubiq",   "most common 20%", "Everywhere, always in stock (Curly Hair / GBB tier)."),
]


def rarity_tier_legend(db_path: Path = DB_PATH) -> list[dict]:
    """Grounded legend for the six named rarity tiers. Each entry carries the
    plain meaning, its percentile band, and — mined from the live data — the
    typical number of sellers and how many catalog species sit in that tier, so
    "Common" vs "Uncommon" vs "Ubiquitous" become concrete instead of abstract."""
    tiers = catalog_rarity_tiers(db_path)
    try:
        from scoring.rarity import compute_all_rarity
        rd = compute_all_rarity(db_path)
    except Exception:
        rd = {}
    buckets: dict[str, list[int]] = {name: [] for name, *_ in _TIER_MEANING}
    counts: dict[str, int] = {name: 0 for name, *_ in _TIER_MEANING}
    for k, t in tiers.items():
        name = t["tier"]
        if name not in counts:
            continue
        counts[name] += 1
        vc = getattr(rd.get(k), "vendor_count", None)
        if vc:
            buckets[name].append(vc)
    out = []
    for name, cls, pct, meaning in _TIER_MEANING:
        vcs = buckets[name]
        if vcs:
            med = int(round(statistics.median(vcs)))
            hi = max(vcs)
            sellers = f"~{med} seller" + ("" if med == 1 else "s")
            if hi > med:
                sellers += f" (up to {hi})"
        else:
            sellers = "—"
        out.append({"tier": name, "tier_class": cls, "pct": pct,
                    "meaning": meaning, "sellers": sellers, "count": counts[name]})
    return out


def _trimmed_median(prices: list[float]) -> float:
    """Median after dropping the single highest and lowest ask (>=4 points),
    so one lowball or one gouger can't define the market price."""
    if not prices:
        return 0.0
    if len(prices) >= 4:
        s = sorted(prices)
        s = s[1:-1]
        return round(statistics.median(s), 2)
    return round(statistics.median(prices), 2)


def _days_since(iso: str, now: datetime) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso)[:19].replace(" ", "T"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).days
    except Exception:
        return None


def private_seller_keys(cur_or_db) -> set:
    """Vendor keys that belong to a per-user PRIVATE seller upload. These must
    never contribute to the public MARKET analytics (all-time-low, market price,
    movers, rarity, trends) — they are one user's private data, not "the market".
    Accepts an open cursor or a db path."""
    own_conn = None
    try:
        if hasattr(cur_or_db, "execute"):
            cur = cur_or_db
        else:
            own_conn = get_connection(cur_or_db)
            cur = own_conn.cursor()
        rows = cur.execute(
            "SELECT vendor_key FROM vendors WHERE platform='private_seller'").fetchall()
        return {r["vendor_key"] for r in rows}
    except Exception:
        return set()
    finally:
        if own_conn is not None:
            own_conn.close()


def species_market_stats(db_path: Path = DB_PATH,
                         only_keys: set | None = None) -> dict[str, dict]:
    """Return {species_key: stats_dict} for every canonical species.

    `only_keys` optionally restricts the computation to a subset (e.g. the one
    species on a detail page) for speed.

    PRIVATE-SELLER SAFETY: rows from `platform='private_seller'` vendors are
    excluded — the market stats are the public website market only, so one user's
    private upload can never move the all-time-low / market price / rarity that
    everyone sees (the 2026-07-20 trust leak: mrs2200's list surfaced as global
    all-time-low alerts).
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    priv = private_seller_keys(cur)

    # Latest run per vendor → defines what is "live" right now.
    cur.execute("""
        SELECT vendor_key, MAX(id) AS mx FROM crawl_runs
        WHERE status IN ('complete','partial') GROUP BY vendor_key
    """)
    latest_runs = {r["vendor_key"]: r["mx"] for r in cur.fetchall()
                   if r["vendor_key"] not in priv}
    live_run_ids = set(latest_runs.values())

    cur.execute("""
        SELECT scientific_name_key AS k, vendor_key, price_usd, availability,
               observed_at, crawl_run_id, sex, size_text, size_midpoint
        FROM price_history
        WHERE price_usd > 0 AND scientific_name_key IS NOT NULL
        ORDER BY observed_at ASC
    """)
    rows = [r for r in cur.fetchall() if r["vendor_key"] not in priv]
    conn.close()

    now = datetime.now(timezone.utc)
    cutoff90 = None
    try:
        from datetime import timedelta
        cutoff90 = (now - timedelta(days=90))
    except Exception:
        pass

    agg: dict[str, dict] = {}
    for r in rows:
        k = r["k"]
        if only_keys is not None and k not in only_keys:
            continue
        a = agg.get(k)
        if a is None:
            a = agg[k] = {
                "prices_all": [], "prices_90d": [], "recent_asks": [],
                "vendors_all": set(), "vendors_live": set(),
                "live_prices": [], "n_live": 0, "n_90d": 0,
                "first_seen": r["observed_at"], "last_seen": r["observed_at"],
                "by_day": {},
            }
        p = float(r["price_usd"])
        a["prices_all"].append(p)
        a["vendors_all"].add(r["vendor_key"])
        oa = r["observed_at"] or ""
        if oa < a["first_seen"]:
            a["first_seen"] = oa
        if oa > a["last_seen"]:
            a["last_seen"] = oa
        # daily-median series (min per day keeps the sparkline a "cheapest" line)
        day = oa[:10]
        if day:
            a["by_day"].setdefault(day, []).append(p)
        # 90-day window
        ds = _days_since(oa, now)
        if ds is not None and ds <= 90:
            a["prices_90d"].append(p)
            a["recent_asks"].append(p)
            a["n_90d"] += 1
        # live (in the latest run for its vendor, in stock)
        if r["crawl_run_id"] in live_run_ids and r["availability"] != "out_of_stock":
            a["vendors_live"].add(r["vendor_key"])
            a["live_prices"].append(p)
            a["n_live"] += 1

    out: dict[str, dict] = {}
    for k, a in agg.items():
        pa = a["prices_all"]
        if not pa:
            continue
        recent = a["recent_asks"] or pa
        live = a["live_prices"]
        spark = [[d, round(min(v), 2)] for d, v in sorted(a["by_day"].items())]
        out[k] = {
            "lowest_ask":       round(min(live), 2) if live else None,
            "all_time_low":     round(min(pa), 2),
            "all_time_high":    round(max(pa), 2),
            "market_price":     _trimmed_median(recent),
            "median_all":       round(statistics.median(pa), 2),
            "low_90d":          round(min(a["prices_90d"]), 2) if a["prices_90d"] else round(min(pa), 2),
            "high_90d":         round(max(a["prices_90d"]), 2) if a["prices_90d"] else round(max(pa), 2),
            "listings_live_now": a["n_live"],
            "vendors_live":     len(a["vendors_live"]),
            "vendors_all":      len(a["vendors_all"]),
            "listings_90d":     a["n_90d"],
            "obs_count":        len(pa),
            "first_seen":       (a["first_seen"] or "")[:10],
            "last_seen":        (a["last_seen"] or "")[:10],
            "spark":            spark,
        }

    _attach_trends(out, db_path)
    # percentile-ranked rarity tier (label only; score stays as-is)
    tiers = catalog_rarity_tiers(db_path)
    for k, st in out.items():
        t = tiers.get(k)
        if t:
            st["rarity_score"] = t["score"]
            st["rarity_tier"] = t["tier"]
            st["rarity_class"] = t["tier_class"]
        else:
            st["rarity_score"] = None
            st["rarity_tier"] = ""
            st["rarity_class"] = ""
    return out


def _attach_trends(stats: dict[str, dict], db_path: Path) -> None:
    """Aggregate the per-(species,sex,size) trend to a single species verdict:
    heating up (median rising), cooling (falling), or steady.

    A trend is only trustworthy once there's real time spread. With just a
    couple of crawls a day apart, a linear velocity extrapolates to absurd
    monthly %s — so we require >=3 distinct observation days spanning >=14 days
    before classifying anything; otherwise the species is 'new' (building
    history). This keeps us honest until the daily 5 AM crawls accumulate.
    """
    MIN_POINTS, MIN_SPAN_DAYS = 3, 14
    try:
        from scoring.trends import compute_price_trends
        trends = compute_price_trends(db_path)
    except Exception:
        trends = {}
    by_species: dict[str, list[float]] = {}
    for (key, _sex, _sb), td in trends.items():
        mp = td.get("monthly_pct")
        if mp is None or td.get("data_points", 0) < MIN_POINTS:
            continue
        span = _date_span_days(td.get("oldest_date"), td.get("newest_date"))
        if span is None or span < MIN_SPAN_DAYS:
            continue
        by_species.setdefault(key, []).append(mp)
    for k, st in stats.items():
        pcts = by_species.get(k, [])
        if not pcts:
            st["trend"] = "new"; st["trend_pct"] = None
            continue
        avg = sum(pcts) / len(pcts)
        st["trend_pct"] = round(avg, 1)
        st["trend"] = "heating" if avg > 5 else ("cooling" if avg < -5 else "steady")


def _date_span_days(oldest: str | None, newest: str | None) -> int | None:
    if not oldest or not newest:
        return None
    try:
        o = datetime.fromisoformat(str(oldest)[:10])
        n = datetime.fromisoformat(str(newest)[:10])
        return (n - o).days
    except Exception:
        return None


def _vendor_run_pairs(cur) -> dict[str, tuple[int, int]]:
    """{vendor: (latest_run_id, baseline_run_id)} where baseline is the most
    recent run on an EARLIER calendar day than the latest. This makes movers a
    true day-over-day comparison, so several test crawls on the same day don't
    hide (or invent) changes. Vendors with only one day of history are omitted."""
    cur.execute("""SELECT vendor_key, id, DATE(COALESCE(finished_at, started_at)) d
                   FROM crawl_runs WHERE status IN ('complete','partial')
                   ORDER BY vendor_key, id DESC""")
    by_vendor: dict[str, list] = {}
    for r in cur.fetchall():
        by_vendor.setdefault(r["vendor_key"], []).append((r["id"], r["d"]))
    pairs = {}
    for vk, runs in by_vendor.items():
        latest_id, latest_day = runs[0]
        baseline = next((rid for rid, d in runs[1:] if d and d < latest_day), None)
        if baseline is not None:
            pairs[vk] = (latest_id, baseline)
    return pairs


def inferred_sales(db_path: Path = DB_PATH, only_key: str | None = None) -> dict[str, list]:
    """Listings that were present in a vendor's previous crawl and are gone (or
    out of stock) in its latest crawl → inferred "recently taken at ~$X".

    Honest proxy for sold price: we never see closes, only that an ask
    disappeared. Returns {species_key: [ {price, date, vendor}, ... ]}.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    pairs = _vendor_run_pairs(cur)

    out: dict[str, list] = {}
    for vk, (latest, prev) in pairs.items():
        # exact listing variants (url + variant + size + sex) live in latest run
        cur.execute(f"""SELECT DISTINCT {_IDENT_SQL} AS ident FROM price_history
                        WHERE crawl_run_id=? AND availability!='out_of_stock'
                          AND product_url IS NOT NULL AND product_url!=''""", (latest,))
        live = {r["ident"] for r in cur.fetchall()}
        cur.execute(f"""SELECT scientific_name_key AS k, price_usd, observed_at,
                               {_IDENT_SQL} AS ident
                        FROM price_history WHERE crawl_run_id=? AND price_usd>0
                          AND availability!='out_of_stock'
                          AND product_url IS NOT NULL AND product_url!=''""", (prev,))
        for r in cur.fetchall():
            k = r["k"]
            if only_key and k != only_key:
                continue
            if r["ident"] in live:
                continue
            out.setdefault(k, []).append({
                "price": round(float(r["price_usd"]), 2),
                "date": (r["observed_at"] or "")[:10],
                "vendor": vk,
            })
    conn.close()
    return out


# Vendors banned from the front-page movers. Urban Tarantulas lists volatile
# premium "display specimens" and repeatedly inflates then cuts, so their
# "biggest drop" / all-time-low tiles are noise, not real market signal
# (Mike's call, 2026-07-20). They still appear normally on /deals + species
# cards — this only keeps them out of the dashboard movers.
BANNED_MOVER_VENDORS = {"urban_tarantulas"}


def market_movers(snapshot: list, db_path: Path = DB_PATH, limit: int = 8) -> dict:
    """Front-page "market movers": biggest drops, back-in-stock, fresh fire
    deals, and heating/cooling species. `snapshot` is the annotated live
    snapshot (already carries is_fire_deal / price_trend / is_price_drop)."""
    stats = species_market_stats(db_path)

    # PRIVATE-SELLER SAFETY: never let a per-user private upload appear in the
    # public movers (all-time-low / drops / restocks). drops/back already require
    # a product_url (private sellers have none), but the snapshot-based fire list
    # must be filtered explicitly, and legacy private keys may lack the priv_
    # prefix so we check the authoritative vendors table too.
    _priv = private_seller_keys(db_path)
    def _excluded(l):
        vk = l.get("vendor_key") or ""
        return (bool(l.get("is_private")) or vk in _priv or vk.startswith("priv_")
                or vk in BANNED_MOVER_VENDORS)

    # Fresh fire deals (all-time-low delivered cost, right now)
    fire = sorted([l for l in snapshot if l.get("is_fire_deal") and not _excluded(l)],
                  key=lambda l: l.get("landed_cost") or l.get("price_usd") or 9e9)[:limit]

    # Biggest drops vs the previous crawl for the same vendor.
    drops = [d for d in _biggest_drops(db_path, limit + 10)
             if d.get("vendor_key") not in BANNED_MOVER_VENDORS][:limit]

    # Back in stock: present+in-stock now, was out/absent in the previous run.
    back = [l for l in _back_in_stock(db_path, snapshot, limit + 10)
            if not _excluded(l)][:limit]

    # Heating / cooling species (needs multi-date history; empty until then).
    heating = sorted([(k, s) for k, s in stats.items() if s.get("trend") == "heating"],
                     key=lambda kv: -(kv[1].get("trend_pct") or 0))[:limit]
    cooling = sorted([(k, s) for k, s in stats.items() if s.get("trend") == "cooling"],
                     key=lambda kv: (kv[1].get("trend_pct") or 0))[:limit]

    return {"fire": fire, "drops": drops, "back_in_stock": back,
            "heating": heating, "cooling": cooling, "stats": stats}


def _biggest_drops(db_path: Path, limit: int) -> list[dict]:
    """Real price drops = the SAME listing variant (url + variant + size + sex)
    cheaper now than in the vendor's previous crawl. Matching on the full variant
    identity — not the shared product URL — is what makes this defensible: we are
    comparing the exact same animal at the exact same seller between two scans."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    pairs = _vendor_run_pairs(cur)

    drops: list[dict] = []
    for vk, (latest, prev) in pairs.items():
        cur.execute(f"""SELECT scientific_name_key AS k, scientific_name, sex, size_text,
                               price_usd, product_url, {_IDENT_SQL} AS ident
                        FROM price_history
                        WHERE crawl_run_id=? AND price_usd>0 AND availability!='out_of_stock'
                          AND product_url IS NOT NULL AND product_url!=''""", (latest,))
        cur_rows, cur_dupes = {}, set()
        for r in cur.fetchall():
            if r["ident"] in cur_rows:
                cur_dupes.add(r["ident"])
            cur_rows[r["ident"]] = dict(r)
        cur.execute(f"""SELECT {_IDENT_SQL} AS ident, price_usd FROM price_history
                        WHERE crawl_run_id=? AND price_usd>0
                          AND product_url IS NOT NULL AND product_url!=''""", (prev,))
        prev_rows, prev_dupes = {}, set()
        for r in cur.fetchall():
            if r["ident"] in prev_rows:
                prev_dupes.add(r["ident"])
            prev_rows[r["ident"]] = float(r["price_usd"])
        seen = set()
        for ident, was in prev_rows.items():
            now_row = cur_rows.get(ident)
            # Only compare an identity that is UNAMBIGUOUS in both runs — if the
            # same identity maps to several rows in either scan, we can't be sure
            # we're following the same listing, so we skip it rather than guess.
            if not now_row or ident in seen or ident in cur_dupes or ident in prev_dupes:
                continue
            seen.add(ident)
            is_ = float(now_row["price_usd"])
            # Genuine markdown: cheaper by >3%. Guard only against a >95% collapse,
            # which is almost always a data error rather than a real cut.
            if is_ < was * 0.97 and is_ >= was * 0.05:
                drops.append({**now_row, "prev_price": round(was, 2),
                              "new_price": round(is_, 2),
                              "pct": round((was - is_) / was * 100, 0),
                              "vendor_key": vk})
    conn.close()
    drops.sort(key=lambda d: -(d["prev_price"] - d["new_price"]))
    return drops[:limit]


def _back_in_stock(db_path: Path, snapshot: list, limit: int) -> list[dict]:
    """Same listing variant out-of-stock last crawl, in-stock now."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    pairs = _vendor_run_pairs(cur)
    back_idents: set = set()
    for vk, (latest, prev) in pairs.items():
        cur.execute(f"""SELECT DISTINCT {_IDENT_SQL} AS ident FROM price_history
                        WHERE crawl_run_id=? AND availability='out_of_stock'
                          AND product_url IS NOT NULL AND product_url!=''""", (prev,))
        was_out = {r["ident"] for r in cur.fetchall()}
        cur.execute(f"""SELECT DISTINCT {_IDENT_SQL} AS ident FROM price_history
                        WHERE crawl_run_id=? AND availability!='out_of_stock'
                          AND product_url IS NOT NULL AND product_url!=''""", (latest,))
        now_in = {r["ident"] for r in cur.fetchall()}
        back_idents |= (was_out & now_in)
    conn.close()
    def _ident(l):
        return "¦".join([l.get("scientific_name_key") or "", l.get("product_url") or "",
                         l.get("variant_name") or "", l.get("size_text") or "",
                         l.get("sex") or ""])
    out = [l for l in snapshot if l.get("product_url") and _ident(l) in back_idents]
    return out[:limit]


def _biggest_single_move(db_path: Path, direction: str) -> dict | None:
    """The single largest same-listing price move (up or down) between a vendor's
    two most recent crawls. `direction` is 'up' or 'down'. Returns one dict or
    None. Same unambiguous-identity matching as _biggest_drops."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    pairs = _vendor_run_pairs(cur)
    best = None
    for vk, (latest, prev) in pairs.items():
        cur.execute(f"""SELECT scientific_name_key AS k, scientific_name, sex, size_text,
                               price_usd, product_url, {_IDENT_SQL} AS ident
                        FROM price_history
                        WHERE crawl_run_id=? AND price_usd>0 AND availability!='out_of_stock'
                          AND product_url IS NOT NULL AND product_url!=''""", (latest,))
        cur_rows, cur_dupes = {}, set()
        for r in cur.fetchall():
            if r["ident"] in cur_rows:
                cur_dupes.add(r["ident"])
            cur_rows[r["ident"]] = dict(r)
        cur.execute(f"""SELECT {_IDENT_SQL} AS ident, price_usd FROM price_history
                        WHERE crawl_run_id=? AND price_usd>0
                          AND product_url IS NOT NULL AND product_url!=''""", (prev,))
        prev_rows, prev_dupes = {}, set()
        for r in cur.fetchall():
            if r["ident"] in prev_rows:
                prev_dupes.add(r["ident"])
            prev_rows[r["ident"]] = float(r["price_usd"])
        for ident, was in prev_rows.items():
            now_row = cur_rows.get(ident)
            if not now_row or ident in cur_dupes or ident in prev_dupes:
                continue
            now = float(now_row["price_usd"])
            # guard against data-error extremes (>95% collapse / >10x spike)
            if direction == "down":
                if not (now < was * 0.97 and now >= was * 0.05):
                    continue
                delta = was - now
            else:
                if not (now > was * 1.03 and now <= was * 10):
                    continue
                delta = now - was
            if best is None or delta > best["_delta"]:
                pct = round((now - was) / was * 100)
                best = {**now_row, "prev_price": round(was, 2), "new_price": round(now, 2),
                        "pct": pct, "vendor_key": vk, "_delta": round(delta, 2)}
    conn.close()
    return best


def _species_price_moves(db_path: Path) -> dict:
    """Species-level market moves between the two most recent crawl DATES a species
    appears on. Used when there's no true same-listing day-over-day delta yet
    (early on, vendor re-crawls record identical prices). Compares the median
    asking price on each date — real data, honestly a market-composite move, not a
    single tag change. Returns {"up": row|None, "down": row|None} where each row is
    {k, prev, new, pct, prev_date, new_date, n}."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT scientific_name_key AS k, DATE(observed_at) AS d,
               price_usd
        FROM price_history
        WHERE price_usd > 0 AND scientific_name_key IS NOT NULL AND scientific_name_key <> ''
    """)
    from collections import defaultdict
    by = defaultdict(lambda: defaultdict(list))
    for r in cur.fetchall():
        by[r["k"]][r["d"]].append(float(r["price_usd"]))
    conn.close()

    from normalize.livestock import GENUS_SET
    up = down = None
    for k, dates in by.items():
        if not k.split() or k.split()[0] not in GENUS_SET:
            continue
        ds = sorted(dates.keys())
        if len(ds) < 2:
            continue
        d_prev, d_new = ds[-2], ds[-1]
        pv, nv = dates[d_prev], dates[d_new]
        # Need several asks on each side so the median reflects the market, not
        # one listing appearing/disappearing (composition noise).
        if len(pv) < 3 or len(nv) < 3:
            continue
        prev = statistics.median(pv)
        new = statistics.median(nv)
        if prev <= 0 or new <= 0 or prev == new:
            continue
        # Keep only believable market moves (±60%); anything larger is almost
        # always a change in which specimens are listed, not a real re-price.
        ratio = new / prev
        if ratio > 1.6 or ratio < 0.4:
            continue
        delta = new - prev
        row = {"k": k, "prev": round(prev, 2), "new": round(new, 2),
               "pct": round((new - prev) / prev * 100), "prev_date": d_prev,
               "new_date": d_new, "n": len(nv), "_delta": round(delta, 2)}
        if delta > 0 and (up is None or delta > up["_delta"]):
            up = row
        if delta < 0 and (down is None or delta < down["_delta"]):
            down = row
    return {"up": up, "down": down}


def market_intelligence(db_path: Path, snapshot: list, owned_keys=None) -> dict:
    """Headline stats mined from the whole dataset for the dashboard Market
    Intelligence panel, grouped for the redesigned layout:
      {price_action:{median_ask, jump, drop},
       coverage:{species, genera, listings, vendors, biggest_genus…, most_listed…},
       standouts:[{badge, bg, fg, sci, value, caption, href}…],
       new_this_crawl:int}
    Everything is derived live from the latest crawl so it matches the catalog."""
    from normalize.common_names_map import best_common
    from normalize.livestock import GENUS_SET
    from normalize.species_canonical import _display_from_key
    stats = species_market_stats(db_path)
    # Restrict to clean canonical species (genus is a known invert genus), so the
    # counts match the species browse and no supply/junk keys leak into the stats.
    stats = {k: v for k, v in stats.items()
             if k.split() and k.split()[0] in GENUS_SET}
    if not stats:
        # Empty DB (e.g. fresh deploy before the first crawl) — return the documented
        # dict shape, never a list, so callers can safely .get() into it.
        return {"price_action": {}, "coverage": {}, "standouts": [], "new_this_crawl": 0}
    from urllib.parse import quote

    def link(key):
        return "/species/" + quote(key)

    def disp(k):
        return _display_from_key(k) or k.title()

    live_key_ok = set(stats)

    # ── genus rollup ────────────────────────────────────────────────────────
    genus_species: dict[str, set] = {}
    for k in stats:
        g = k.split()[0] if k.split() else ""
        if g:
            genus_species.setdefault(g, set()).add(k)
    n_species = len(stats)
    n_genera = len(genus_species)
    big_genus, big_set = max(genus_species.items(), key=lambda kv: len(kv[1]))

    # ── live listing / vendor totals (catalog species only) ─────────────────
    live = [l for l in snapshot if (l.get("price_usd") or 0) > 0
            and l.get("scientific_name_key") in live_key_ok]
    total_live = len(live)
    vendors_live = len({l.get("vendor_key") or l.get("vendor") for l in live})

    # ── most listed species (live) ──────────────────────────────────────────
    most_listed_k = max(stats, key=lambda k: stats[k].get("listings_live_now") or 0)
    ml = stats[most_listed_k]

    # ── grail: priciest listing among apex-rarity (Mythic) species ──────────
    mythic_keys = {k for k, s in stats.items() if s.get("rarity_tier") == "Mythic"}
    grail = None
    priciest = None
    for l in live:
        p = l.get("price_usd") or 0
        k = l.get("scientific_name_key")
        if priciest is None or p > (priciest.get("price_usd") or 0):
            priciest = l
        if k in mythic_keys and (grail is None or p > (grail.get("price_usd") or 0)):
            grail = l

    # ── rarest species available right now ──────────────────────────────────
    live_keys = {l.get("scientific_name_key") for l in live}
    rare_in_stock = None
    for k in live_keys:
        s = stats.get(k)
        if not s or not s.get("rarity_score"):
            continue
        if rare_in_stock is None or (s["rarity_score"], -(s.get("listings_live_now") or 0)) > \
           (stats[rare_in_stock]["rarity_score"], -(stats[rare_in_stock].get("listings_live_now") or 0)):
            rare_in_stock = k

    # ── most collected (from user collection) ───────────────────────────────
    most_collected = None
    try:
        conn = get_connection(db_path)
        rows = conn.execute("""SELECT species_key, SUM(quantity) q FROM collection
                               GROUP BY species_key ORDER BY q DESC LIMIT 1""").fetchall()
        conn.close()
        if rows and rows[0]["species_key"]:
            most_collected = (rows[0]["species_key"], rows[0]["q"])
    except Exception:
        pass

    # ── biggest price moves ─────────────────────────────────────────────────
    # Prefer a true same-listing day-over-day move; if the crawl history has no
    # per-listing delta yet, fall back to a species-level median move between the
    # two most recent crawl dates so the tiles still show real motion.
    up = _biggest_single_move(db_path, "up")
    down = _biggest_single_move(db_path, "down")
    sp_moves = None
    if not up or not down:
        sp_moves = _species_price_moves(db_path)

    # ── new species this crawl ──────────────────────────────────────────────
    new_ct = sum(1 for l in live if l.get("new_to_system"))

    # ── median market price across the catalog ──────────────────────────────
    mkt_prices = [s["market_price"] for s in stats.values() if s.get("market_price")]
    median_mkt = round(statistics.median(mkt_prices)) if mkt_prices else 0

    def abbrev(d):
        """'Typhochlaena seladonia' -> 'T. seladonia' (leave sp. forms whole)."""
        p = d.split()
        if len(p) >= 2 and p[0][:1].isalpha() and p[1] != "sp.":
            return f"{p[0][0].upper()}. " + " ".join(p[1:])
        return d

    # tier → (badge label, bg, fg) for the Standouts pills.
    # Derived from theme.py — no rarity hex is written here.
    _TIER_BADGE = {
        name: (t["label"], t["bg"], t["text"])
        for name, t in _THEME_TIERS.items()
    }

    # Only surface moves whose species still has live listings, so the link never
    # lands on an empty/dead species page.
    _live_keys = {l.get("scientific_name_key") for l in (snapshot or [])}

    def _move(real, spm, positive):
        """Normalize a price move (real per-listing, else species-median) to
        {label, sci, prev, new, href} or None. Skips species no longer live."""
        if real and real["k"] in _live_keys:
            return {"label": f"{real['pct']:+d}%", "sci": abbrev(disp(real["k"])),
                    "prev": round(real["prev_price"]), "new": round(real["new_price"]),
                    "href": link(real["k"])}
        if spm and spm["k"] in _live_keys:
            return {"label": f"{spm['pct']:+d}%", "sci": abbrev(disp(spm["k"])),
                    "prev": round(spm["prev"]), "new": round(spm["new"]),
                    "href": link(spm["k"])}
        return None

    # ── Price action ────────────────────────────────────────────────────────
    price_action = {
        "median_ask": median_mkt,
        "jump": _move(up, sp_moves["up"] if sp_moves else None, True),
        "drop": _move(down, sp_moves["down"] if sp_moves else None, False),
    }

    # ── Coverage ────────────────────────────────────────────────────────────
    coverage = {
        "species": n_species, "genera": n_genera,
        "listings": total_live, "vendors": vendors_live,
        "biggest_genus": big_genus.capitalize(), "biggest_genus_n": len(big_set),
        "biggest_genus_href": f"/genus/{big_genus}",
        "most_listed": abbrev(disp(most_listed_k)),
        "most_listed_common": best_common(most_listed_k) or "",
        "most_listed_n": ml.get("listings_live_now"),
        "most_listed_href": link(most_listed_k),
    }

    # ── Standouts ───────────────────────────────────────────────────────────
    standouts = []
    if grail:
        gk = grail.get("scientific_name_key")
        gtier = stats.get(gk, {}).get("rarity_tier") or "Mythic"
        b = _TIER_BADGE.get(gtier, _TIER_BADGE["Mythic"])
        standouts.append({"badge": b[0], "bg": b[1], "fg": b[2], "sci": disp(gk),
                          "value": f"${grail.get('price_usd'):,.0f}",
                          "caption": "current grail", "href": link(gk)})
    if rare_in_stock:
        s = stats[rare_in_stock]
        b = _TIER_BADGE.get(s.get("rarity_tier"), _TIER_BADGE["Legendary"])
        n = s.get("listings_live_now") or 1
        standouts.append({"badge": b[0], "bg": b[1], "fg": b[2],
                          "sci": disp(rare_in_stock),
                          "value": f"{n} left" if n <= 3 else f"{n} listed",
                          "caption": "rarest in stock", "href": link(rare_in_stock)})
    if priciest:
        pk = priciest.get("scientific_name_key")
        standouts.append({"badge": "$$$$", "bg": "#374151", "fg": "#d1d5db",
                          "sci": disp(pk), "value": f"${priciest.get('price_usd'):,.0f}",
                          "caption": "priciest specimen", "href": link(pk)})
    if most_collected:
        mk, mq = most_collected
        standouts.append({"badge": "OWNED", "bg": "#065f46", "fg": "#6ee7b7",
                          "sci": disp(mk), "value": f"×{mq}",
                          "caption": "most collected", "href": link(mk)})

    return {"price_action": price_action, "coverage": coverage,
            "standouts": standouts, "new_this_crawl": new_ct}
