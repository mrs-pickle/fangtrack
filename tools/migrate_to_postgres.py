"""
Copy the local SQLite database into a Postgres target (e.g. Render Postgres).

Usage (PowerShell):
    $env:DATABASE_URL = "postgres://user:pass@host:5432/dbname"
    python tools/migrate_to_postgres.py [path/to/source.sqlite]

Steps:
  1. Creates the full schema on the Postgres target via the app's own init functions
     (they route through database.get_connection, which sees DATABASE_URL → Postgres).
  2. Copies every table's rows, preserving primary keys, then fixes each id sequence.

Idempotent: rows use ON CONFLICT DO NOTHING, so re-running won't duplicate.
"""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_COLLECTION_DDL = """
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
"""


def main():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        sys.exit("Set DATABASE_URL to the target Postgres connection string first.")
    src_path = sys.argv[1] if len(sys.argv) > 1 else "database/market_history.sqlite"
    if not os.path.exists(src_path):
        sys.exit(f"Source SQLite not found: {src_path}")

    # ── 1. Build the schema on Postgres (get_connection routes to PG via DATABASE_URL) ──
    from database.db import init_db, init_discount_tables, get_connection
    from scoring.watchlist import init_watchlist_tables
    import auth
    print("Creating schema on Postgres…")
    init_db()
    init_discount_tables()
    init_watchlist_tables()
    auth.init_auth_tables()
    tgt = get_connection()
    tgt.executescript(_COLLECTION_DDL)
    # collection also gained purchase + user_id columns over time; add if missing.
    for col, decl in (("price_paid", "DOUBLE PRECISION"), ("acquired_date", "TEXT"),
                      ("source", "TEXT"), ("user_id", "INTEGER")):
        try:
            tgt.execute(f"ALTER TABLE collection ADD COLUMN IF NOT EXISTS {col} {decl}")
        except Exception as e:
            print(f"  (collection.{col}: {e})")
    tgt.commit()

    # ── 1b. Drop FK constraints ─────────────────────────────────────────────────
    # SQLite doesn't enforce foreign keys by default, so the source has orphaned
    # rows (e.g. crawl_runs for retired vendors). Postgres DOES enforce them, which
    # blocks the bulk copy. Drop the FKs (they're advisory here) so every row loads.
    try:
        fks = tgt.execute(
            "SELECT conrelid::regclass::text AS tbl, conname FROM pg_constraint "
            "WHERE contype = 'f'").fetchall()
        for fk in fks:
            tgt.execute(f'ALTER TABLE {fk["tbl"]} DROP CONSTRAINT IF EXISTS "{fk["conname"]}"')
        tgt.commit()
        print(f"Dropped {len(fks)} foreign-key constraint(s) for bulk load.")
    except Exception as e:
        print(f"  (dropping FKs: {e})")
        tgt.commit()

    # ── 2. Copy every table, preserving ids ─────────────────────────────────────
    src = sqlite3.connect(src_path)
    src.row_factory = sqlite3.Row
    tables = [r[0] for r in src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    total = 0
    for t in tables:
        # Skip any source table the target schema doesn't have (keeps one missing
        # table from aborting the whole copy).
        exists = tgt.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = ? AND table_schema = current_schema()", (t,)).fetchone()
        if not exists:
            print(f"  {t}: SKIPPED (no such table on target)")
            continue
        rows = src.execute(f"SELECT * FROM {t}").fetchall()
        if not rows:
            print(f"  {t}: 0 rows")
            continue
        cols = list(rows[0].keys())
        collist = ",".join(cols)
        ph = ",".join(["?"] * len(cols))
        cur = tgt.cursor()
        sql = f"INSERT OR IGNORE INTO {t} ({collist}) VALUES ({ph})"
        # Batch with executemany (psycopg pipelines it) instead of a network
        # round-trip per row — turns a ~40-min price_history copy into ~1 min.
        CHUNK = 1000
        for i in range(0, len(rows), CHUNK):
            cur.executemany(sql, [tuple(r[c] for c in cols) for r in rows[i:i + CHUNK]])
            if len(rows) > CHUNK:
                print(f"    {t}: {min(i + CHUNK, len(rows))}/{len(rows)}", end="\r")
        tgt.commit()
        if "id" in cols:
            # advance the BIGSERIAL sequence past the copied ids
            try:
                cur.execute(
                    f"SELECT setval(pg_get_serial_sequence('{t}','id'), "
                    f"COALESCE((SELECT MAX(id) FROM {t}), 1))")
                tgt.commit()
            except Exception as e:
                print(f"  (seq {t}: {e})")
        total += len(rows)
        print(f"  {t}: {len(rows)} rows")
    src.close()
    # Update planner statistics after the bulk load — without this Postgres uses
    # stale stats and picks slow sequential scans, which times the dashboard out.
    try:
        tgt.execute("ANALYZE")
        tgt.commit()
        print("Ran ANALYZE (planner statistics refreshed).")
    except Exception as e:
        print(f"  (ANALYZE: {e})")
    tgt.close()
    print(f"Done. Copied {total} rows across {len(tables)} tables.")
    print("Verify: point the app at DATABASE_URL and load /deals + /collection.")


if __name__ == "__main__":
    main()
