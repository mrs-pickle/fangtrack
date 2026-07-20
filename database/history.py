"""
Price History Engine
All functions that read historical data from price_history and use it to:
  - Populate historical lows on current listings before deal scoring
  - Detect price drops vs the previous crawl for the same vendor
  - Produce time-series price data for any species
  - Summarise crawl run history

This module is the bridge between the append-only price_history table
and the deal-scoring engine. Every crawl should call:
    1. compute_price_changes(new_listings, db_path)   -- sets is_price_drop / is_price_increase
    2. populate_historical_lows(new_listings, db_path) -- sets historical_low / is_new_historical_low
BEFORE calling score_all_listings().
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from database.db import get_connection, DB_PATH


# ──────────────────────────────────────────────────────────────────────────────
# 1.  HISTORICAL LOWS
# ──────────────────────────────────────────────────────────────────────────────

def get_all_historical_lows(db_path: Path = DB_PATH) -> dict:
    """
    Return a dict mapping (scientific_name_key, sex) → min(price_usd)
    computed from ALL rows in price_history regardless of vendor or date.
    Sex values: 'F', 'M', 'PF', 'PM', 'U', 'Unknown'

    Used to seed the historical_low field on current listings before scoring.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT scientific_name_key, sex, MIN(price_usd) as min_price
        FROM price_history
        WHERE price_usd > 0
          AND availability != 'out_of_stock'
        GROUP BY scientific_name_key, sex
    """)
    lows = {}
    for row in cur.fetchall():
        key = row["scientific_name_key"]
        sex = row["sex"] or "U"
        lows[(key, sex)] = float(row["min_price"])
    conn.close()
    return lows


def populate_historical_lows(listings: list, db_path: Path = DB_PATH) -> None:
    """
    For each listing, query price_history for the all-time low price for the
    same species + sex combination, and set:
      listing.historical_low        → that all-time low
      listing.is_new_historical_low → True if current price ≤ historical low

    Modifies listings in place. Works with both Listing dataclass objects
    and plain dicts.
    """
    lows = get_all_historical_lows(db_path)

    for l in listings:
        # Support both Listing objects and dicts
        is_dict = isinstance(l, dict)
        key  = l.get("scientific_name_key")  if is_dict else l.scientific_name_key
        sex  = (l.get("sex") or "U")         if is_dict else (l.sex or "U")
        price = l.get("price_usd")           if is_dict else l.price_usd

        if not key or not price:
            continue

        hist_low = lows.get((key, sex))
        if hist_low is None:
            # Try unsexed fallback
            hist_low = lows.get((key, "U"))

        if hist_low is None:
            continue

        is_new_low = price <= hist_low

        if is_dict:
            l["historical_low"]           = hist_low
            l["is_new_historical_low"]    = is_new_low
        else:
            l.historical_low           = hist_low
            l.is_new_historical_low    = is_new_low


# ──────────────────────────────────────────────────────────────────────────────
# 2.  PRICE CHANGE DETECTION (price drops vs previous crawl)
# ──────────────────────────────────────────────────────────────────────────────

def get_previous_prices(vendor_key: str, db_path: Path = DB_PATH) -> dict:
    """
    Return a dict mapping (scientific_name_key, sex, size_text) → last_price
    from the most recent completed crawl run for this vendor (before the current one).

    Used to detect price drops and price increases.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    # Get the second-most-recent crawl run id for this vendor
    cur.execute("""
        SELECT id FROM crawl_runs
        WHERE vendor_key = ?
          AND status IN ('complete', 'partial')
        ORDER BY id DESC
        LIMIT 2
    """, (vendor_key,))
    rows = cur.fetchall()

    if len(rows) < 2:
        conn.close()
        return {}

    prev_run_id = rows[1]["id"]

    cur.execute("""
        SELECT scientific_name_key, sex, size_text, price_usd
        FROM price_history
        WHERE crawl_run_id = ?
          AND price_usd > 0
    """, (prev_run_id,))

    prev = {}
    for row in cur.fetchall():
        k = (row["scientific_name_key"], row["sex"] or "U", row["size_text"] or "")
        prev[k] = float(row["price_usd"])

    conn.close()
    return prev


def compute_price_changes(listings: list, vendor_key: str,
                          db_path: Path = DB_PATH) -> None:
    """
    Compare each new listing against the previous crawl for the same vendor.
    Sets is_price_drop, is_price_increase, previous_price on each listing.
    Modifies listings in place.
    """
    prev = get_previous_prices(vendor_key, db_path)
    if not prev:
        return  # First crawl for this vendor — no comparison possible

    for l in listings:
        is_dict = isinstance(l, dict)
        key   = l.get("scientific_name_key")  if is_dict else l.scientific_name_key
        sex   = (l.get("sex") or "U")         if is_dict else (l.sex or "U")
        size  = (l.get("size_text") or "")    if is_dict else (l.size_text or "")
        price = l.get("price_usd")            if is_dict else l.price_usd

        if not key or not price:
            continue

        prev_price = prev.get((key, sex, size))
        if prev_price is None:
            prev_price = prev.get((key, sex, ""))  # size-agnostic fallback

        if prev_price is None:
            continue

        drop = price < prev_price * 0.99   # >1% drop
        rise = price > prev_price * 1.01   # >1% rise

        if is_dict:
            l["previous_price"]    = prev_price
            l["is_price_drop"]     = drop
            l["is_price_increase"] = rise
        else:
            l.previous_price    = prev_price
            l.is_price_drop     = drop
            l.is_price_increase = rise


# ──────────────────────────────────────────────────────────────────────────────
# 3.  MARKET CONTEXT FOR SCORING
# ──────────────────────────────────────────────────────────────────────────────

def get_market_context(db_path: Path = DB_PATH,
                       days_back: int = 180) -> dict:
    """
    Build a rich market context from ALL historical data for deal scoring.

    Returns:
      {(species_key, sex, size_bucket): {
          'all_time_low':   float,
          'median_90d':     float,   # median across last 90 days
          'median_all':     float,   # median across all history
          'obs_count':      int,
          'vendor_count':   int,
          'latest_date':    str,
      }}

    Size buckets: xs (<0.5), sling (0.5-1), juvenile (1-2),
                  subadult (2-3.5), adult_sm (3.5-5.5), adult_lg (5.5+)
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    cutoff_90d = f"datetime('now', '-90 days')"
    cutoff_hist = f"datetime('now', '-{days_back} days')"

    cur.execute(f"""
        SELECT
            scientific_name_key,
            sex,
            size_midpoint,
            price_usd,
            observed_at,
            vendor_key,
            CASE
                WHEN size_midpoint IS NULL THEN 'unknown'
                WHEN size_midpoint < 0.5   THEN 'xs'
                WHEN size_midpoint < 1.0   THEN 'sling'
                WHEN size_midpoint < 2.0   THEN 'juvenile'
                WHEN size_midpoint < 3.5   THEN 'subadult'
                WHEN size_midpoint < 5.5   THEN 'adult_sm'
                ELSE 'adult_lg'
            END as size_bucket
        FROM price_history
        WHERE price_usd > 0
          AND availability != 'out_of_stock'
          AND observed_at >= {cutoff_hist}
        ORDER BY observed_at DESC
    """)

    rows = cur.fetchall()
    conn.close()

    # Group into context buckets
    groups: dict = {}
    for row in rows:
        key = (row["scientific_name_key"], row["sex"] or "U", row["size_bucket"])
        if key not in groups:
            groups[key] = {"prices_all": [], "prices_90d": [], "vendors": set(), "latest": ""}
        g = groups[key]
        g["prices_all"].append(float(row["price_usd"]))
        g["vendors"].add(row["vendor_key"])
        if row["observed_at"] > g["latest"]:
            g["latest"] = row["observed_at"]
        # 90d subset
        if row["observed_at"] >= datetime.now(timezone.utc).strftime("%Y-%m-%d"):
            g["prices_90d"].append(float(row["price_usd"]))

    context = {}
    for key, g in groups.items():
        pa = g["prices_all"]
        p90 = g["prices_90d"] or pa
        context[key] = {
            "all_time_low":  min(pa),
            "median_90d":    statistics.median(p90),
            "median_all":    statistics.median(pa),
            "obs_count":     len(pa),
            "vendor_count":  len(g["vendors"]),
            "latest_date":   g["latest"][:10],
        }

    return context


# ──────────────────────────────────────────────────────────────────────────────
# 4.  SPECIES PRICE TIME SERIES
# ──────────────────────────────────────────────────────────────────────────────

def get_species_price_history(species_key: str,
                               sex: str = None,
                               db_path: Path = DB_PATH) -> list[dict]:
    """
    Return all price observations for a species, sorted by date.
    Optional sex filter ('F', 'M', 'U', etc.).

    Returns list of dicts with keys:
      vendor_key, vendor_name (if joinable), verification_level,
      sex, size_text, price_usd, observed_at, crawl_run_id, notes
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    query = """
        SELECT
            ph.vendor_key,
            v.vendor_name,
            ph.verification_level,
            ph.sex,
            ph.sex_display,
            ph.size_text,
            ph.size_midpoint,
            ph.price_usd,
            ph.regular_price_usd,
            ph.is_price_drop,
            ph.is_new_historical_low,
            ph.deal_rating,
            ph.observed_at,
            ph.crawl_run_id,
            ph.notes
        FROM price_history ph
        LEFT JOIN vendors v ON v.vendor_key = ph.vendor_key
        WHERE ph.scientific_name_key = ?
          AND ph.price_usd > 0
    """
    params = [species_key]   # exact match uses idx_ph_key (was a leading-wildcard
                             # LIKE = full scan of the biggest table on every /species hit)

    if sex:
        query += " AND ph.sex = ?"
        params.append(sex)

    query += " ORDER BY ph.observed_at ASC, ph.price_usd ASC"

    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def print_species_history(species_name: str, db_path: Path = DB_PATH) -> None:
    """CLI helper: print price history for a species to stdout."""
    from normalize.species import normalize_species_key
    key = normalize_species_key(species_name)
    rows = get_species_price_history(key, db_path=db_path)

    if not rows:
        print(f"No history found for '{species_name}'")
        return

    print(f"\nPrice history: {species_name} ({len(rows)} records)")
    print(f"{'Date':<12} {'Vendor':<28} {'Size':>6} {'Sex':>4} {'Price':>8} {'Level':<18} {'Flags'}")
    print("─" * 95)

    for r in rows:
        flags = []
        if r["is_price_drop"]:       flags.append("↓DROP")
        if r["is_new_historical_low"]: flags.append("★LOW")
        if r["deal_rating"] in ("💎💎", "💎"): flags.append(r["deal_rating"])

        date   = str(r["observed_at"])[:10]
        vendor = (r["vendor_name"] or r["vendor_key"] or "?")[:28]
        size   = f"{r['size_text']}\"" if r.get("size_text") else "—"
        sex    = r.get("sex_display", r.get("sex", "?"))[:4]
        price  = f"${r['price_usd']:.2f}"
        level  = (r.get("verification_level") or "?")[:18]
        flag_s = " ".join(flags)

        print(f"{date:<12} {vendor:<28} {size:>6} {sex:>4} {price:>8} {level:<18} {flag_s}")

    prices = [r["price_usd"] for r in rows]
    print(f"\n  All-time low:  ${min(prices):.2f}")
    print(f"  All-time high: ${max(prices):.2f}")
    print(f"  Median:        ${statistics.median(prices):.2f}")
    print(f"  Sources:       {len({r['vendor_key'] for r in rows})} vendors/sellers")


# ──────────────────────────────────────────────────────────────────────────────
# 5.  CRAWL RUN SUMMARY
# ──────────────────────────────────────────────────────────────────────────────

def get_crawl_summary(db_path: Path = DB_PATH) -> list[dict]:
    """
    Return summary of every crawl run with source type and listing count.
    Used for the Excel 'Crawl Status' and 'History' sheets.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            cr.id,
            cr.vendor_key,
            v.vendor_name,
            v.platform,
            cr.status,
            cr.variants_found,
            cr.started_at,
            cr.finished_at,
            cr.notes,
            COUNT(ph.id) as ph_rows,
            MIN(ph.price_usd) as min_price,
            MAX(ph.price_usd) as max_price
        FROM crawl_runs cr
        LEFT JOIN vendors v ON v.vendor_key = cr.vendor_key
        LEFT JOIN price_history ph ON ph.crawl_run_id = cr.id
        GROUP BY cr.id, cr.vendor_key, v.vendor_name, v.platform, cr.status,
                 cr.variants_found, cr.started_at, cr.finished_at, cr.notes
        ORDER BY cr.id DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_all_history_for_export(db_path: Path = DB_PATH,
                                limit: int = 50_000) -> list[dict]:
    """
    Return all price_history rows for the Excel Price History sheet.
    Limited to most recent `limit` rows for workbook size management.
    Joins vendor_name for display.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT
            ph.observed_at,
            ph.vendor_key,
            v.vendor_name,
            v.platform,
            ph.verification_level,
            ph.scientific_name,
            ph.common_name,
            ph.sex_display,
            ph.size_text,
            ph.price_usd,
            ph.regular_price_usd,
            ph.deal_rating,
            ph.is_price_drop,
            ph.is_new_historical_low,
            ph.notes,
            ph.crawl_run_id
        FROM price_history ph
        LEFT JOIN vendors v ON v.vendor_key = ph.vendor_key
        ORDER BY ph.observed_at DESC
        LIMIT {limit}
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
