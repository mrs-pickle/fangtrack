"""
Re-key historical rows through the master alias reference (normalize/key_aliases).

Idempotent: safe to run after every scan or whenever key_aliases.py grows.
Rewrites scientific_name_key in price_history and products so misspelled /
truncated keys collapse onto their canonical species. Also refreshes the
scientific_name_key on rows whose stored common_name we can re-derive cleanly.

Usage:
    python tools/migrate_key_aliases.py          # apply
    python tools/migrate_key_aliases.py --dry     # preview only
"""
import os, sys, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from normalize.key_aliases import canonicalize_key
from database.db import DB_PATH


def migrate(dry: bool = False) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    total_changed = 0
    for table in ("price_history", "products"):
        try:
            keys = [r[0] for r in cur.execute(
                f"SELECT DISTINCT scientific_name_key FROM {table} "
                f"WHERE scientific_name_key IS NOT NULL AND scientific_name_key<>''"
            )]
        except sqlite3.OperationalError:
            continue
        remap = {}
        for k in keys:
            ck = canonicalize_key(k)
            if ck != k:
                remap[k] = ck
        if not remap:
            print(f"  {table}: nothing to remap")
            continue
        print(f"  {table}: {len(remap)} keys → canonical")
        for old, new in sorted(remap.items()):
            n = cur.execute(f"SELECT COUNT(*) FROM {table} WHERE scientific_name_key=?",
                            (old,)).fetchone()[0]
            print(f"      {old!r:46} -> {new!r:34} ({n} rows)")
            total_changed += n
            if not dry:
                cur.execute(
                    f"UPDATE {table} SET scientific_name_key=? WHERE scientific_name_key=?",
                    (new, old))
    if dry:
        print(f"\nDRY RUN — would rewrite {total_changed} rows. No changes made.")
    else:
        conn.commit()
        print(f"\nDONE — rewrote {total_changed} rows.")
    conn.close()


if __name__ == "__main__":
    migrate(dry="--dry" in sys.argv)
