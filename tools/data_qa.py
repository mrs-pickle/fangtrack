#!/usr/bin/env python3
"""
Data QA sweep over the current in-stock snapshot (latest run per vendor). Flags the
things a tester would notice first: junk/non-species titles, bad prices, in-vendor
duplicates, missing canonical keys, and price outliers vs each species' own median.

Read-only. Run:  python tools/data_qa.py
"""
import sys, os, re, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

from database.db import get_connection, DB_PATH


def latest_snapshot():
    conn = get_connection(DB_PATH)
    runs = [r["mx"] for r in conn.execute(
        "SELECT MAX(id) mx FROM crawl_runs WHERE status IN ('complete','partial') "
        "GROUP BY vendor_key").fetchall()]
    if not runs:
        return []
    ph = ",".join("?" * len(runs))
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM price_history WHERE crawl_run_id IN ({ph}) "
        f"AND availability!='out_of_stock'", runs).fetchall()]
    conn.close()
    return rows


# words that betray a non-livestock or junk listing slipping through the filter.
# NB: avoid tokens that collide with real common names — "patch" (Pumpkin Patch
# tarantula), "bark" (bark scorpion), "pin" (pinktoe) — those caused false positives.
_JUNK_WORDS = re.compile(r"\b(gift\s*card|sticker|shirt|hoodie|enclosure|substrate|"
                         r"deli\s*cup|water\s*dish|\bbook\b|\bprint\b|poster|artwork|"
                         r"mystery\s*box|dubia|mealworm|springtail\s*culture|"
                         r"tongs|calendar|magnet|keychain|decor)\b", re.I)
# a real scientific title should contain at least one alphabetic genus-like token
_HAS_ALPHA = re.compile(r"[A-Za-z]{3,}")


def run():
    snap = latest_snapshot()
    n = len(snap)
    print(f"=== Data QA sweep — {n} in-stock listings across "
          f"{len({r['vendor_key'] for r in snap})} vendors ===\n")
    if not n:
        print("No snapshot rows — run a crawl first.")
        return

    bad_price, junk, no_key, dupes, outliers = [], [], [], [], []

    # per-species price list for outlier detection (by canonical key)
    by_key = {}
    for r in snap:
        k = (r.get("scientific_name_key") or "").strip()
        p = r.get("price_usd")
        if k and isinstance(p, (int, float)) and p > 0:
            by_key.setdefault(k, []).append(p)

    seen = {}  # (vendor, key, size, price) -> count, for in-vendor dupes
    for r in snap:
        name = (r.get("scientific_name") or r.get("raw_title") or "").strip()
        key = (r.get("scientific_name_key") or "").strip()
        p = r.get("price_usd")
        vk = r.get("vendor_key")

        # 1) bad prices
        if p is None or not isinstance(p, (int, float)) or p <= 0:
            bad_price.append((vk, name, p))
        elif p > 5000:
            bad_price.append((vk, name, p))   # implausibly high — likely a parse error

        # 2) junk / non-species titles
        if _JUNK_WORDS.search(name) or not _HAS_ALPHA.search(name):
            junk.append((vk, name))

        # 3) missing canonical key (won't group onto a species card)
        if not key:
            no_key.append((vk, name))

        # 4) in-vendor exact duplicates
        sig = (vk, key, r.get("size_text"), p)
        seen[sig] = seen.get(sig, 0) + 1

        # 5) price outlier vs this species' median (needs >=4 samples)
        if key and isinstance(p, (int, float)) and p > 0:
            prices = by_key.get(key, [])
            if len(prices) >= 4:
                med = statistics.median(prices)
                if med > 0 and (p > med * 6 or p < med / 6):
                    outliers.append((vk, name, p, round(med, 2)))

    dupes = [(sig, c) for sig, c in seen.items() if c > 1]

    def section(title, rows, fmt, limit=25):
        print(f"── {title}: {len(rows)} ──")
        for row in rows[:limit]:
            print("   " + fmt(row))
        if len(rows) > limit:
            print(f"   … +{len(rows)-limit} more")
        print()

    section("Bad prices ($0 / null / >$5000)", bad_price,
            lambda r: f"[{r[0]}] {r[1][:60]!r} → {r[2]}")
    section("Junk / non-species titles", junk,
            lambda r: f"[{r[0]}] {r[1][:70]!r}")
    section("Missing canonical species key", no_key,
            lambda r: f"[{r[0]}] {r[1][:70]!r}")
    section("In-vendor exact duplicates", dupes,
            lambda r: f"[{r[0][0]}] key={r[0][1]!r} size={r[0][2]!r} ${r[0][3]} ×{r[1]}")
    section("Price outliers (>6× or <1/6× species median)", outliers,
            lambda r: f"[{r[0]}] {r[1][:50]!r} ${r[2]} vs median ${r[3]}")

    total = len(bad_price)+len(junk)+len(no_key)+len(dupes)+len(outliers)
    print(f"=== {total} total flags "
          f"({len(bad_price)} price, {len(junk)} junk, {len(no_key)} no-key, "
          f"{len(dupes)} dupe, {len(outliers)} outlier) ===")


if __name__ == "__main__":
    run()
