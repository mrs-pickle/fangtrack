"""
SQLite database layer for the Tarantula Market Tracker.
Handles all persistence: crawl runs, products, variants, price history.
Never overwrites old price observations -- append only.
"""
import os
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from models import Listing, CrawlResult


# DB location is env-configurable so a hosted deploy (e.g. Render) can point it at a
# persistent disk mount (SQLite on an ephemeral web filesystem is wiped on every redeploy).
DB_PATH = Path(os.environ.get("FANGTRACK_DB_PATH", "database/market_history.sqlite"))


# When DATABASE_URL is set we run on Postgres via the opt-in adapter (database/pg.py);
# otherwise everything below is the original, untouched SQLite path.
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection(db_path: Path = DB_PATH):
    if DATABASE_URL:
        from database import pg
        return pg.connect(DATABASE_URL)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    """Create all tables if they don't exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS vendors (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_key  TEXT UNIQUE NOT NULL,
        vendor_name TEXT NOT NULL,
        base_url    TEXT,
        platform    TEXT,
        created_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS crawl_runs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_key      TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'pending',
        pages_crawled   INTEGER DEFAULT 0,
        products_found  INTEGER DEFAULT 0,
        variants_found  INTEGER DEFAULT 0,
        failures_json   TEXT,
        started_at      TEXT,
        finished_at     TEXT,
        notes           TEXT,
        FOREIGN KEY (vendor_key) REFERENCES vendors(vendor_key)
    );

    CREATE TABLE IF NOT EXISTS products (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_key          TEXT NOT NULL,
        scientific_name     TEXT NOT NULL,
        scientific_name_key TEXT NOT NULL,
        common_name         TEXT,
        product_url         TEXT,
        first_seen          TEXT,
        last_seen           TEXT,
        FOREIGN KEY (vendor_key) REFERENCES vendors(vendor_key)
    );

    CREATE TABLE IF NOT EXISTS variants (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id      INTEGER NOT NULL,
        vendor_key      TEXT NOT NULL,
        variant_name    TEXT,
        sex             TEXT,
        size_text       TEXT,
        size_min        REAL,
        size_max        REAL,
        product_url     TEXT,
        first_seen      TEXT,
        last_seen       TEXT,
        FOREIGN KEY (product_id) REFERENCES products(id)
    );

    CREATE TABLE IF NOT EXISTS price_history (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_key          TEXT NOT NULL,
        scientific_name     TEXT NOT NULL,
        scientific_name_key TEXT NOT NULL,
        common_name         TEXT,
        sex                 TEXT,
        sex_display         TEXT,
        size_text           TEXT,
        size_min            REAL,
        size_max            REAL,
        size_midpoint       REAL,
        price_usd           REAL NOT NULL,
        regular_price_usd   REAL,
        availability        TEXT,
        quantity            INTEGER,
        product_url         TEXT,
        variant_name        TEXT,
        notes               TEXT,
        deal_rating         TEXT,
        deal_reason         TEXT,
        current_lowest      REAL,
        market_average      REAL,
        historical_low      REAL,
        price_per_inch      REAL,
        is_new              INTEGER DEFAULT 0,
        is_price_drop       INTEGER DEFAULT 0,
        is_new_historical_low INTEGER DEFAULT 0,
        is_returned_to_stock INTEGER DEFAULT 0,
        is_sold_out         INTEGER DEFAULT 0,
        is_price_increase   INTEGER DEFAULT 0,
        previous_price      REAL,
        verification_level  TEXT,
        raw_title           TEXT,
        raw_variant         TEXT,
        raw_price           TEXT,
        description         TEXT,
        crawl_run_id        INTEGER,
        observed_at         TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (crawl_run_id) REFERENCES crawl_runs(id)
    );

    CREATE INDEX IF NOT EXISTS idx_ph_key ON price_history(scientific_name_key, sex, vendor_key);
    CREATE INDEX IF NOT EXISTS idx_ph_observed ON price_history(observed_at);
    CREATE INDEX IF NOT EXISTS idx_ph_vendor ON price_history(vendor_key);
    """)

    # Additive migrations for existing DBs (new columns added over time).
    ph_cols = {r[1] for r in cur.execute("PRAGMA table_info(price_history)")}
    if "description" not in ph_cols:
        cur.execute("ALTER TABLE price_history ADD COLUMN description TEXT")
    cr_cols = {r[1] for r in cur.execute("PRAGMA table_info(crawl_runs)")}
    if "truncated" not in cr_cols:
        cur.execute("ALTER TABLE crawl_runs ADD COLUMN truncated INTEGER DEFAULT 0")

    conn.commit()
    conn.close()
    print(f"[DB] Database initialized at {db_path}")


def upsert_vendor(vendor_key: str, vendor_name: str, base_url: str, platform: str,
                  db_path: Path = DB_PATH) -> None:
    conn = get_connection(db_path)
    conn.execute("""
        INSERT OR IGNORE INTO vendors (vendor_key, vendor_name, base_url, platform)
        VALUES (?, ?, ?, ?)
    """, (vendor_key, vendor_name, base_url, platform))
    conn.commit()
    conn.close()


def insert_crawl_run(result: CrawlResult, db_path: Path = DB_PATH) -> int:
    """Insert a crawl run record and return its ID."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO crawl_runs
            (vendor_key, status, pages_crawled, products_found, variants_found,
             failures_json, started_at, finished_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result.vendor_key,
        result.status,
        result.pages_crawled,
        result.products_found,
        result.variants_found,
        json.dumps(result.failures) if result.failures else None,
        result.started_at.isoformat() if result.started_at else None,
        result.finished_at.isoformat() if result.finished_at else None,
        result.notes,
    ))
    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def save_listings(listings: List[Listing], crawl_run_id: int,
                  db_path: Path = DB_PATH) -> None:
    """Append all listings from a crawl to price_history. Never overwrites."""
    if not listings:
        return

    conn = get_connection(db_path)
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()

    rows = []
    for l in listings:
        rows.append((
            l.vendor_key, l.scientific_name, l.scientific_name_key or "",
            l.common_name, l.sex, l.sex_display,
            l.size_text, l.size_min_inches, l.size_max_inches, l.size_midpoint,
            l.price_usd, l.regular_price_usd, l.availability,
            l.quantity, l.product_url, l.variant_name, l.notes,
            l.deal_rating, l.deal_reason,
            l.current_lowest_price, l.market_average, l.historical_low,
            l.price_per_inch,
            int(l.is_new), int(l.is_price_drop), int(l.is_new_historical_low),
            int(l.is_returned_to_stock), int(l.is_sold_out), int(l.is_price_increase),
            l.previous_price, l.verification_level,
            l.raw_title, l.raw_variant, l.raw_price, l.description,
            crawl_run_id, now,
        ))

    cur.executemany("""
        INSERT INTO price_history
            (vendor_key, scientific_name, scientific_name_key, common_name,
             sex, sex_display, size_text, size_min, size_max, size_midpoint,
             price_usd, regular_price_usd, availability, quantity,
             product_url, variant_name, notes,
             deal_rating, deal_reason, current_lowest, market_average, historical_low,
             price_per_inch, is_new, is_price_drop, is_new_historical_low,
             is_returned_to_stock, is_sold_out, is_price_increase,
             previous_price, verification_level,
             raw_title, raw_variant, raw_price, description,
             crawl_run_id, observed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, rows)

    conn.commit()
    conn.close()


def get_historical_low(scientific_name_key: str, sex: str,
                       db_path: Path = DB_PATH) -> Optional[float]:
    """Return the all-time lowest price for a taxon+sex combination."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT MIN(price_usd) FROM price_history
        WHERE scientific_name_key = ?
          AND sex = ?
          AND availability != 'out_of_stock'
    """, (scientific_name_key, sex))
    row = cur.fetchone()
    conn.close()
    if row and row[0] is not None:
        return float(row[0])
    return None


def get_previous_price(vendor_key: str, scientific_name_key: str, sex: str,
                       size_text: Optional[str], db_path: Path = DB_PATH) -> Optional[float]:
    """Return the most recent previously observed price for this variant."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT price_usd FROM price_history
        WHERE vendor_key = ?
          AND scientific_name_key = ?
          AND sex = ?
          AND (size_text = ? OR (size_text IS NULL AND ? IS NULL))
        ORDER BY observed_at DESC
        LIMIT 1
    """, (vendor_key, scientific_name_key, sex, size_text, size_text))
    row = cur.fetchone()
    conn.close()
    if row:
        return float(row[0])
    return None


def get_all_active_listings(db_path: Path = DB_PATH) -> list[dict]:
    """
    Return all listings from the most recent crawl per vendor.
    Used for deal scoring across the full dataset.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    # Get the latest crawl run per vendor
    cur.execute("""
        SELECT vendor_key, MAX(id) as max_run
        FROM crawl_runs
        WHERE status IN ('complete', 'partial')
        GROUP BY vendor_key
    """)
    latest_runs = {row["vendor_key"]: row["max_run"] for row in cur.fetchall()}

    if not latest_runs:
        conn.close()
        return []

    run_ids = list(latest_runs.values())
    placeholders = ",".join("?" * len(run_ids))

    cur.execute(f"""
        SELECT * FROM price_history
        WHERE crawl_run_id IN ({placeholders})
          AND availability != 'out_of_stock'
        ORDER BY scientific_name_key, sex, price_usd
    """, run_ids)

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# DISCOUNT CODES TABLE
# ---------------------------------------------------------------------------

def init_discount_tables(db_path: Path = DB_PATH) -> None:
    """Add discount_codes and vendor_shipping tables if they don't exist."""
    conn = get_connection(db_path)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS discount_codes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_key      TEXT NOT NULL,
        code            TEXT NOT NULL,
        discount_type   TEXT NOT NULL DEFAULT 'pct',  -- 'pct' | 'flat' | 'free_shipping'
        discount_value  REAL,         -- % for pct, $ for flat
        min_order       REAL,         -- minimum order total to apply
        max_uses        INTEGER,      -- null = unlimited per order
        expires         TEXT,         -- ISO date string or null
        source_url      TEXT,
        source_context  TEXT,         -- snippet of page text where found
        scraped_at      TEXT DEFAULT (datetime('now')),
        is_active       INTEGER DEFAULT 1,
        is_verified     INTEGER DEFAULT 0,  -- manually confirmed working
        UNIQUE(vendor_key, code)
    );

    CREATE TABLE IF NOT EXISTS vendor_shipping (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_key      TEXT NOT NULL UNIQUE,
        vendor_name     TEXT,
        origin_zip      TEXT,         -- vendor's ship-from zip code (if known)
        carrier         TEXT,         -- 'FedEx' | 'UPS' | 'USPS' | 'multiple'
        service         TEXT,         -- 'overnight' | '2-day' | 'ground'
        flat_rate       REAL,         -- fixed shipping fee in $
        free_threshold  REAL,         -- order total for free shipping (null = never free)
        min_order       REAL,         -- minimum order to ship at all
        heat_cold_pack  REAL,         -- extra cost for seasonal pack (null = included)
        live_guarantee  INTEGER DEFAULT 1,
        notes           TEXT,
        source_url      TEXT,
        scraped_at      TEXT DEFAULT (datetime('now'))
    );
    """)
    conn.commit()
    conn.close()


def normalize_code(code: str) -> str:
    """Canonical form of a promo code: uppercase, no whitespace.

    Discount codes are single tokens — they never contain spaces. Scraped text
    sometimes splits a code across HTML spans ("TARANTULAT ALK"), so we strip
    ALL internal whitespace (not just the ends) and uppercase. Any other
    character a code legitimately uses (- _ .) is preserved.
    """
    import re
    return re.sub(r"\s+", "", (code or "")).upper().strip()


def upsert_discount_code(vendor_key: str, code: str, discount_type: str,
                         discount_value: float, min_order: float = None,
                         expires: str = None, source_url: str = None,
                         source_context: str = None, is_verified: int = 0,
                         db_path: Path = DB_PATH) -> None:
    code = normalize_code(code)
    conn = get_connection(db_path)
    conn.execute("""
        INSERT INTO discount_codes
            (vendor_key, code, discount_type, discount_value, min_order,
             expires, source_url, source_context, is_verified)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(vendor_key, code) DO UPDATE SET
            discount_value  = excluded.discount_value,
            discount_type   = excluded.discount_type,
            min_order       = excluded.min_order,
            expires         = excluded.expires,
            source_url      = excluded.source_url,
            source_context  = excluded.source_context,
            is_verified     = excluded.is_verified,
            scraped_at      = datetime('now'),
            is_active       = 1
    """, (vendor_key, code, discount_type, discount_value,
          min_order, expires, source_url, source_context, is_verified))
    conn.commit()
    conn.close()


def upsert_shipping(vendor_key: str, vendor_name: str, flat_rate: float = None,
                    free_threshold: float = None, min_order: float = None,
                    carrier: str = None, service: str = None,
                    origin_zip: str = None, live_guarantee: int = 1,
                    heat_cold_pack: float = None, notes: str = None,
                    source_url: str = None, db_path: Path = DB_PATH) -> None:
    conn = get_connection(db_path)
    conn.execute("""
        INSERT INTO vendor_shipping
            (vendor_key, vendor_name, origin_zip, carrier, service,
             flat_rate, free_threshold, min_order, heat_cold_pack,
             live_guarantee, notes, source_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(vendor_key) DO UPDATE SET
            vendor_name    = excluded.vendor_name,
            origin_zip     = COALESCE(excluded.origin_zip, origin_zip),
            carrier        = COALESCE(excluded.carrier, carrier),
            service        = COALESCE(excluded.service, service),
            flat_rate      = COALESCE(excluded.flat_rate, flat_rate),
            free_threshold = COALESCE(excluded.free_threshold, free_threshold),
            min_order      = COALESCE(excluded.min_order, min_order),
            heat_cold_pack = COALESCE(excluded.heat_cold_pack, heat_cold_pack),
            live_guarantee = excluded.live_guarantee,
            notes          = COALESCE(excluded.notes, notes),
            source_url     = COALESCE(excluded.source_url, source_url),
            scraped_at     = datetime('now')
    """, (vendor_key, vendor_name, origin_zip, carrier, service,
          flat_rate, free_threshold, min_order, heat_cold_pack,
          live_guarantee, notes, source_url))
    conn.commit()
    conn.close()


def get_active_discount_codes(db_path: Path = DB_PATH) -> dict:
    """Return {vendor_key: [code_dicts]} for all active codes."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT vendor_key, code, discount_type, discount_value, min_order,
               expires, source_url, is_verified
        FROM discount_codes
        WHERE is_active = 1
          AND (expires IS NULL OR expires >= date('now'))
        ORDER BY vendor_key, discount_value DESC
    """)
    result = {}
    for row in cur.fetchall():
        vk = row[0]
        result.setdefault(vk, []).append(dict(row))
    conn.close()
    return result


def get_all_shipping(db_path: Path = DB_PATH) -> dict:
    """Return {vendor_key: shipping_dict} for all vendors."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM vendor_shipping ORDER BY vendor_key")
    result = {row["vendor_key"]: dict(row) for row in cur.fetchall()}
    conn.close()
    return result


# ──────────────────────────────────────────────────────────────────────────────
# MarketDB CLASS
# Provides the object-oriented interface expected by pipeline.py
# ──────────────────────────────────────────────────────────────────────────────

class MarketDB:
    """
    Thin wrapper around the db module functions.
    Pipeline.py uses this class; the underlying functions remain usable standalone.
    """

    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        init_db(self.db_path)

    def upsert_vendor(self, vendor_key: str, vendor_name: str,
                      base_url: str = "", platform: str = "unknown") -> None:
        upsert_vendor(vendor_key, vendor_name, base_url, platform, self.db_path)

    def start_run(self, vendor_key: str, started_at=None) -> int:
        """Create a crawl_run record and return its id. `started_at` (ISO string) lets the
        caller record the real scrape-start time so the speed report reflects the scrape,
        not the save; defaults to now."""
        conn = get_connection(self.db_path)
        now = started_at or datetime.utcnow().isoformat()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO crawl_runs (vendor_key, status, started_at)
            VALUES (?, 'running', ?)
        """, (vendor_key, now))
        run_id = cur.lastrowid
        conn.commit()
        conn.close()
        return run_id

    def record(self, run_id: int, listing: dict) -> None:
        """Insert a single listing dict into price_history."""
        from normalize.species import normalize_species_key
        from normalize.species_canonical import canonical_species
        from normalize.size import parse_size
        now = datetime.utcnow().isoformat()

        name = listing.get("scientific_name") or listing.get("name") or ""
        # Prefer a canonical key already computed upstream (_make_listing); else
        # canonicalize here so every save path yields ONE key per species.
        name_key = listing.get("scientific_name_key")
        common = listing.get("common_name")
        if not name_key:
            try:
                ckey, _disp, ccommon = canonical_species(name)
                name_key = ckey or normalize_species_key(name)
                common = common or ccommon
            except Exception:
                name_key = name.lower()
        # Master alias pass — clean the key no matter which path produced it, so
        # a key precomputed upstream is collapsed too. See normalize/key_aliases.
        try:
            from normalize.key_aliases import canonicalize_key
            name_key = canonicalize_key(name_key)
        except Exception:
            pass

        # Prefer the size already computed upstream (_make_listing). Only derive
        # here when it's missing — and derive it the SAME way (numeric-in-variant
        # + life-stage), never with a bare parse_size that drops "Female - 3in".
        sz_mid = listing.get("size_midpoint")
        size_text = listing.get("size_text") or listing.get("size")
        if sz_mid is not None:
            sz_min = listing.get("size_min_inches") or listing.get("size_min")
            sz_max = listing.get("size_max_inches") or listing.get("size_max")
        else:
            from normalize.size import derive_size
            size_text, sz_min, sz_max, sz_mid = derive_size(
                size_text, listing.get("raw_variant"), listing.get("variant_name"),
                listing.get("raw_title"), name)

        sex = listing.get("sex") or "U"

        conn = get_connection(self.db_path)
        conn.execute("""
            INSERT INTO price_history
                (vendor_key, scientific_name, scientific_name_key, common_name,
                 sex, sex_display, size_text, size_min, size_max, size_midpoint,
                 price_usd, regular_price_usd, availability, quantity,
                 product_url, variant_name, notes,
                 verification_level, raw_title, raw_variant, raw_price, description,
                 crawl_run_id, observed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            listing.get("vendor_key") or listing.get("vendor") or "",
            name, name_key,
            common,
            sex,
            listing.get("sex_display", sex),
            size_text, sz_min, sz_max, sz_mid,
            listing.get("price_usd") or listing.get("price") or 0,
            listing.get("regular_price_usd"),
            listing.get("availability", "in_stock"),
            listing.get("quantity"),
            listing.get("product_url"),
            listing.get("variant_name"),
            listing.get("notes"),
            listing.get("verification_level", "direct"),
            listing.get("raw_title"),
            listing.get("raw_variant"),
            listing.get("raw_price"),
            listing.get("description"),
            run_id,
            now,
        ))
        conn.commit()
        conn.close()

    def finish_run(self, run_id: int, count: int,
                   status: str = "complete", notes: str = None,
                   finished_at=None, truncated: bool = False) -> None:
        """Mark a crawl run as complete. `finished_at` (ISO string) records the real
        scrape-end time so the speed report reflects the scrape window, not the save.
        `truncated` flags a run that under-counts (pagination cut short) so the
        snapshot can skip it in favour of the vendor's last good run."""
        conn = get_connection(self.db_path)
        fin = finished_at or datetime.utcnow().isoformat()
        # The pipeline saves flat listings, so `count` is the meaningful figure for
        # both columns; set products_found too so the Vendors admin never shows "0
        # products" for a run that actually saved listings.
        conn.execute("""
            UPDATE crawl_runs
            SET status = ?, products_found = ?, variants_found = ?, finished_at = ?,
                notes = COALESCE(?, notes), truncated = ?
            WHERE id = ?
        """, (status, count, count, fin, notes, 1 if truncated else 0, run_id))
        conn.commit()
        conn.close()

    def historical_lows(self) -> dict:
        """Return {(species_key, sex): min_price} from all history."""
        from database.history import get_all_historical_lows
        return get_all_historical_lows(self.db_path)

    def all_history(self) -> list[dict]:
        """Return full price_history for Excel export."""
        from database.history import get_all_history_for_export
        return get_all_history_for_export(self.db_path)

    def close(self) -> None:
        pass  # Connections are closed per-operation in this implementation
