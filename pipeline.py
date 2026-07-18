"""
Crawl Pipeline
Orchestrates everything that happens after a vendor scrape completes:
  1. Save every new listing to price_history (append-only, never overwrites)
  2. Detect price drops vs the previous crawl for the same vendor
  3. Annotate each listing with its all-time historical low
  4. Score deals against current cross-vendor pricing AND historical data
  5. Rebuild the master Excel workbook

Every crawl run gets its own crawl_runs record with:
  - vendor_key, status, started_at, finished_at
  - products_found, variants_found count
  - notes (source type, date, any warnings)

Private seller uploads and seeded community data all go through the same
pipeline so the historical DB grows consistently regardless of source.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from database.db import (
    MarketDB, get_connection, init_db, upsert_vendor,
    init_discount_tables, DB_PATH,
)
from database.history import (
    populate_historical_lows,
    compute_price_changes,
    get_crawl_summary,
    get_all_history_for_export,
)
from scoring.deals import rate_all, score_all_listings, compute_fire_deals
from scoring.rarity    import compute_all_rarity, annotate_listings_with_rarity
from scoring.watchlist import init_watchlist_tables, check_watchlist, print_watchlist_hits
from scoring.trends    import annotate_with_trends
from normalize.source_type import annotate_source_types
from normalize.common_names import enrich_listings_with_common_names

import shutil
from datetime import datetime as _dt

def backup_db(db_path=DB_PATH):
    """Copy SQLite DB to database/backups/ with datestamp. Non-fatal on failure."""
    try:
        backup_dir = Path(db_path).parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        stamp = _dt.now().strftime("%Y-%m-%d")
        dest = backup_dir / f"market_history_{stamp}.sqlite"
        if not dest.exists():  # one backup per day max
            shutil.copy2(db_path, dest)
            import logging
            logging.getLogger(__name__).info(f"[BACKUP] DB backed up to {dest}")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[BACKUP] Failed: {e}")


def check_vendor_health(vendor_url: str, timeout: int = 10) -> bool:
    """Quick HEAD request to verify vendor URL is reachable before crawling."""
    try:
        import httpx
        r = httpx.head(vendor_url, timeout=timeout, follow_redirects=True)
        return r.status_code < 500
    except Exception:
        return False


from export.excel import build_workbook

logger = logging.getLogger(__name__)

XLSX_PATH = "output/tarantula_market_tracker.xlsx"


# ──────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ──────────────────────────────────────────────────────────────────────────────

def run_pipeline(
    new_listings:      list,
    vendor_key:        str,
    vendor_name:       str,
    crawl_notes:       str = "",
    db_path:           str | Path = DB_PATH,
    xlsx_path:         str | Path = XLSX_PATH,
    all_active:        Optional[list] = None,
) -> str:
    """
    Save a completed vendor crawl and rebuild the workbook.

    Parameters
    ----------
    new_listings : list
        Listing objects or dicts from the vendor scraper.
    vendor_key : str
        Slug identifying the vendor (e.g. 'jamies', 'eric_madrid').
    vendor_name : str
        Human-readable display name.
    crawl_notes : str
        Any warning or metadata string to attach to the crawl_run record.
    db_path : path
        Path to the SQLite DB.
    xlsx_path : path
        Output path for the Excel workbook.
    all_active : list, optional
        If running multiple vendors in one session, pass the merged
        snapshot here so the workbook reflects the full market.
    """
    db_path   = Path(db_path)
    xlsx_path = Path(xlsx_path)

    db = MarketDB(db_path)

    # Ensure schema is up to date
    init_discount_tables(db_path)

    # Register vendor if new
    db.upsert_vendor(vendor_key, vendor_name)

    # ── 1. Detect price changes BEFORE saving (compares vs previous run) ──
    compute_price_changes(new_listings, vendor_key, db_path)

    # ── 2. Annotate with historical lows BEFORE saving so the flag is stored ──
    populate_historical_lows(new_listings, db_path)

    # ── 3. Persist to price_history ──
    now = datetime.now(timezone.utc).isoformat()
    run_id = db.start_run(vendor_key)

    saved = 0
    for l in new_listings:
        try:
            d = _to_dict(l)
            if not _is_stocked(d) or not _is_livestock(d):
                continue
            db.record(run_id, d)
            saved += 1
        except Exception as e:
            logger.warning(f"[{vendor_key}] Failed to save listing: {e}")

    db.finish_run(run_id, saved,
                  notes=crawl_notes or f"Live crawl — {now[:10]}")

    logger.info(f"[{vendor_key}] Saved {saved} listings (run_id={run_id})")

    # ── 4. Score the full active snapshot ──
    snapshot = all_active if all_active is not None else new_listings
    history_lows = db.historical_lows()
    rate_all(snapshot, history_lows)

    # ── 5. Rebuild workbook ──
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    crawl_summary = get_crawl_summary(db_path)
    build_workbook(snapshot, get_all_history_for_export(db_path),
                   crawl_summary, str(xlsx_path))

    logger.info(f"Workbook rebuilt: {xlsx_path}")
    db.close()
    return str(xlsx_path)


def run_multi_vendor_pipeline(
    vendor_results:  list[tuple[str, str, list]],
    db_path:         str | Path = DB_PATH,
    xlsx_path:       str | Path = XLSX_PATH,
) -> str:
    """
    Process multiple vendor crawls in one session.

    vendor_results: list of (vendor_key, vendor_name, listings) tuples
    All listings are merged into one snapshot for workbook generation,
    but each vendor gets its own crawl_run record.
    """
    db_path   = Path(db_path)
    xlsx_path = Path(xlsx_path)

    db = MarketDB(db_path)
    init_discount_tables(db_path)

    all_saved: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for row in vendor_results:
        # Accept (vk, name, listings), + optional (scrape_started, scrape_finished, truncated)
        # so crawl_runs can record the real scrape window and flag truncated runs.
        vendor_key, vendor_name, listings = row[0], row[1], row[2]
        scrape_started = row[3] if len(row) > 3 else None
        scrape_finished = row[4] if len(row) > 4 else None
        truncated = row[5] if len(row) > 5 else False
        if not listings:
            continue

        db.upsert_vendor(vendor_key, vendor_name)
        compute_price_changes(listings, vendor_key, db_path)
        populate_historical_lows(listings, db_path)

        run_id = db.start_run(vendor_key, started_at=scrape_started)
        saved = 0
        for l in listings:
            try:
                d = _to_dict(l)
                if not _is_stocked(d) or not _is_livestock(d):
                    continue
                db.record(run_id, d)
                all_saved.append(d)
                saved += 1
            except Exception as e:
                logger.warning(f"[{vendor_key}] {e}")

        db.finish_run(run_id, saved,
                      status="partial" if truncated else "complete",
                      notes=f"Multi-vendor crawl — {now[:10]}"
                            + (" (truncated)" if truncated else ""),
                      finished_at=scrape_finished, truncated=truncated)
        logger.info(f"[{vendor_key}] {saved} listings saved (run_id={run_id})"
                    + (" [TRUNCATED — snapshot keeps last good run]" if truncated else ""))

    # Score combined snapshot against all history
    history_lows = db.historical_lows()
    rate_all(all_saved, history_lows)

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    crawl_summary = get_crawl_summary(db_path)
    build_workbook(all_saved, get_all_history_for_export(db_path),
                   crawl_summary, str(xlsx_path))

    logger.info(f"Workbook rebuilt with {len(all_saved)} listings from "
                f"{len(vendor_results)} vendors: {xlsx_path}")
    db.close()
    return str(xlsx_path)


# ──────────────────────────────────────────────────────────────────────────────
# EXPORT-ONLY (rebuild workbook from existing DB, no new crawl)
# ──────────────────────────────────────────────────────────────────────────────

def export_only(db_path: str | Path = DB_PATH,
                xlsx_path: str | Path = XLSX_PATH) -> str:
    """
    Rebuild the workbook from whatever is in the DB — no crawling.
    Useful after manually adding community prices or fixing data.
    """
    db_path   = Path(db_path)
    xlsx_path = Path(xlsx_path)

    # Pull the most recent snapshot (latest crawl per vendor)
    backup_db(db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()

    # Latest run per vendor
    cur.execute("""
        SELECT vendor_key, MAX(id) as max_run
        FROM crawl_runs
        WHERE status IN ('complete', 'partial')
        GROUP BY vendor_key
    """)
    latest_runs = {r["vendor_key"]: r["max_run"] for r in cur.fetchall()}

    snapshot = []
    if latest_runs:
        placeholders = ",".join("?" * len(latest_runs))
        cur.execute(f"""
            SELECT * FROM price_history
            WHERE crawl_run_id IN ({placeholders})
              AND availability != 'out_of_stock'
            ORDER BY scientific_name_key, sex, price_usd
        """, list(latest_runs.values()))
        snapshot = [dict(r) for r in cur.fetchall()]
    conn.close()

    # Annotate with history then score
    populate_historical_lows(snapshot, db_path)
    history_lows = MarketDB(db_path).historical_lows()
    try:
        rate_all(snapshot, history_lows)
    except Exception as _e:
        import logging; logging.getLogger(__name__).warning(f"Scoring non-fatal: {_e}")

    # 🔥 Landed cost records
    from database.db import get_all_shipping
    shipping_lookup = get_all_shipping(db_path)
    compute_fire_deals(snapshot, shipping_lookup, db_path=db_path)

    # Source type (WC vs CB) — must happen before deal scoring
    annotate_source_types(snapshot)
    enrich_listings_with_common_names(snapshot)

    # Rarity Index (species-level + per-size-class)
    rarity_data = compute_all_rarity(db_path)
    annotate_listings_with_rarity(snapshot, db_path)
    from scoring.rarity import compute_size_class_rarity, annotate_with_size_class_rarity
    size_class_rarity = compute_size_class_rarity(db_path)
    annotate_with_size_class_rarity(snapshot, size_class_rarity)

    # Price trends (→ ↑ ↓) — meaningful after 2+ crawl dates
    annotate_with_trends(snapshot, db_path)

    # Watchlist hits
    init_watchlist_tables(db_path)
    wl_hits = check_watchlist(snapshot, db_path)
    if wl_hits:
        print_watchlist_hits(wl_hits)

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    crawl_summary = get_crawl_summary(db_path)
    build_workbook(snapshot, get_all_history_for_export(db_path),
                   crawl_summary, str(xlsx_path),
                   rarity_data=rarity_data,
                   size_class_rarity=size_class_rarity)

    logger.info(f"Export-only rebuild: {len(snapshot)} listings → {xlsx_path}")
    return str(xlsx_path)


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────


# ── Stock filter ──────────────────────────────────────────────────────────────
_SOLD_OUT_VALUES = {"out_of_stock", "sold_out", "soldout", "sold-out", "unavailable"}
_SOLD_OUT_TEXT = ("sold out", "out of stock")

def _is_stocked(d: dict) -> bool:
    """Return False for listings marked or titled as sold out / out of stock."""
    avail = str(d.get("availability") or "").strip().lower().replace(" ", "_")
    if avail in _SOLD_OUT_VALUES:
        return False
    blob = " ".join(str(d.get(k) or "") for k in ("raw_title", "notes", "size_text")).lower()
    return not any(t in blob for t in _SOLD_OUT_TEXT)


def _is_livestock(d: dict) -> bool:
    """Return True only for live invertebrate listings (drop supplies/decor/etc)."""
    from normalize.livestock import is_livestock
    title = d.get("scientific_name") or d.get("raw_title") or ""
    return is_livestock(title)


def _to_dict(listing) -> dict:
    """Convert a Listing dataclass to a plain dict if needed."""
    if isinstance(listing, dict):
        return listing
    # Listing dataclass → dict via __dict__ or dataclasses.asdict
    try:
        import dataclasses
        return dataclasses.asdict(listing)
    except Exception:
        return vars(listing)


# ──────────────────────────────────────────────────────────────────────────────
# LEGACY SHIM — preserves backward compat with old pipeline.persist_and_export
# ──────────────────────────────────────────────────────────────────────────────

def persist_and_export(new_listings: list[dict], crawl_status: list[dict],
                       db_path: str = str(DB_PATH),
                       xlsx_path: str = XLSX_PATH,
                       current_snapshot: list[dict] | None = None):
    """
    Legacy entrypoint kept for backward compatibility.
    Groups listings by vendor, saves each, then rebuilds the workbook.
    """
    by_vendor: dict[str, tuple[str, list]] = {}
    for l in new_listings:
        vk = l.get("vendor_key") or l.get("vendor") or "unknown"
        vn = l.get("vendor_name") or vk
        by_vendor.setdefault(vk, (vn, []))
        by_vendor[vk][1].append(l)

    vendor_results = [
        (vk, vn, listings)
        for vk, (vn, listings) in by_vendor.items()
    ]

    snapshot = current_snapshot if current_snapshot is not None else new_listings
    return run_multi_vendor_pipeline(vendor_results, db_path=db_path, xlsx_path=xlsx_path)
