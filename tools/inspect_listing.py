#!/usr/bin/env python3
"""Read-only: dump snapshot rows matching a name substring, with raw fields.
Usage: python tools/inspect_listing.py actaeon
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
from database.db import get_connection, DB_PATH

needle = (sys.argv[1] if len(sys.argv) > 1 else "actaeon").lower()

conn = get_connection(DB_PATH)
runs = [r["mx"] for r in conn.execute(
    "SELECT MAX(id) mx FROM crawl_runs WHERE status IN ('complete','partial') "
    "GROUP BY vendor_key").fetchall()]
ph = ",".join("?" * len(runs))
rows = [dict(r) for r in conn.execute(
    f"SELECT * FROM price_history WHERE crawl_run_id IN ({ph})", runs).fetchall()]
conn.close()

hits = [r for r in rows if needle in ((r.get("scientific_name") or "") + " " +
                                      (r.get("raw_title") or "")).lower()]
print(f"{len(hits)} rows matching {needle!r} (all availabilities):\n")
for r in hits:
    print(f"[{r.get('vendor_key')}] name={r.get('scientific_name')!r}")
    print(f"    price_usd={r.get('price_usd')}  raw_price={r.get('raw_price')!r}  "
          f"regular={r.get('regular_price_usd')}")
    print(f"    size_text={r.get('size_text')!r}  sex={r.get('sex')}  "
          f"avail={r.get('availability')}  variant={r.get('variant_name')!r}")
    print(f"    url={r.get('product_url')}")
    print(f"    raw_variant={r.get('raw_variant')!r}")
    d = r.get('description')
    if d:
        import re as _re
        print("    DESC:", _re.sub(r'<[^>]+>', ' ', d)[:700].strip())
    print()
