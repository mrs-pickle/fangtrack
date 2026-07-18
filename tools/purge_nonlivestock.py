"""
Purge non-livestock rows from the DB so deals / species / stats stay spotless.

Re-evaluates every stored listing through the SAME `normalize.livestock.is_livestock`
gate the crawler uses, and deletes anything that isn't a live invertebrate —
enclosures, substrate, decor, feeders, apparel, merch, minerals, vertebrates.
Because it reuses the one filter, it never diverges from crawl-time behaviour;
strengthen the deny lists in livestock.py and this purge enforces them everywhere.

Idempotent and safe to run after every crawl (pipeline calls purge_db() on finish).

Usage:
    python tools/purge_nonlivestock.py --dry    # preview what would be removed
    python tools/purge_nonlivestock.py          # delete
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from normalize.livestock import is_livestock
from database.db import DB_PATH


def _title(row) -> str:
    # same signal the crawler filters on: parsed name first, else the raw title
    return (row["scientific_name"] or "") or (row["raw_title"] or "")


def purge_db(db_path=DB_PATH, dry: bool = False, verbose: bool = True) -> int:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    removed_total = 0
    for table in ("price_history", "products"):
        try:
            cols = {r[1] for r in cur.execute(f"PRAGMA table_info({table})")}
        except sqlite3.OperationalError:
            continue
        if "scientific_name" not in cols:
            continue
        has_raw = "raw_title" in cols
        rows = cur.execute(
            f"SELECT rowid AS rid, scientific_name, "
            f"{'raw_title' if has_raw else 'NULL AS raw_title'} FROM {table}"
        ).fetchall()
        drop_ids, samples = [], {}
        for r in rows:
            if not is_livestock(_title(r)):
                drop_ids.append(r["rid"])
                key = _title(r)[:60]
                samples[key] = samples.get(key, 0) + 1
        if verbose and samples:
            print(f"\n  {table}: {len(drop_ids)} rows to remove "
                  f"({len(samples)} distinct titles). Top:")
            for t, n in sorted(samples.items(), key=lambda kv: -kv[1])[:25]:
                print(f"      {n:4}×  {t!r}")
        removed_total += len(drop_ids)
        if not dry and drop_ids:
            cur.executemany(f"DELETE FROM {table} WHERE rowid=?",
                            [(i,) for i in drop_ids])
    if dry:
        print(f"\nDRY RUN — would remove {removed_total} rows. No changes made.")
    else:
        conn.commit()
        if verbose:
            print(f"\nDONE — removed {removed_total} non-livestock rows.")
    conn.close()
    return removed_total


if __name__ == "__main__":
    purge_db(dry="--dry" in sys.argv)
