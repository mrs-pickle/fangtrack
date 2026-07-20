#!/usr/bin/env python3
"""Read-only: show each ACTIVE vendor's latest run status/products vs the
dashboard 'honest health' classification, to explain dashboard-vs-history
mismatches."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
from database.db import get_connection, DB_PATH
from vendors import REGISTRY

conn = get_connection(DB_PATH)
rows = conn.execute("""
    SELECT cr.vendor_key vk, cr.status status, cr.products_found pf, cr.notes notes
    FROM crawl_runs cr
    JOIN (SELECT vendor_key, MAX(id) mid FROM crawl_runs GROUP BY vendor_key) m
      ON cr.id = m.mid
""").fetchall()
conn.close()
active = set(REGISTRY.keys())
for r in sorted(rows, key=lambda r: r["vk"]):
    if r["vk"] not in active:
        continue
    st = (r["status"] or "").lower(); pf = r["pf"] or 0
    if st == "partial": health = "partial"
    elif st == "complete" and pf > 0: health = "healthy"
    else: health = "DOWN"
    if health != "healthy":
        print(f"{r['vk']:24} run_status={st:10} products={pf:5} -> dashboard={health}")
        if r["notes"]: print(f"    note: {str(r['notes'])[:100]}")
