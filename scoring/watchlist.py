"""
Watchlist & Price Alert System
Set targets for specific species/sex/size/price and get notified when
any crawl finds a matching listing at or below your target price.

CLI usage:
  python scoring/watchlist.py --add "Grammostola pulchra" --sex F --max-size 4 --max-price 400
  python scoring/watchlist.py --add "Birupes simoroxigorum" --max-price 120
  python scoring/watchlist.py --list
  python scoring/watchlist.py --remove 3
  python scoring/watchlist.py --check   # check current DB snapshot manually

Pipeline: call check_watchlist(snapshot, db_path) after every crawl.
"""
from __future__ import annotations

import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from database.db import get_connection, DB_PATH
from normalize.species import normalize_species_key


# ─── DB schema ────────────────────────────────────────────────────────────────

WATCHLIST_DDL = """
CREATE TABLE IF NOT EXISTS watchlist (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    species_key     TEXT NOT NULL,
    species_display TEXT NOT NULL,          -- how user typed it
    sex             TEXT,                   -- 'F' | 'M' | null (any)
    min_size        REAL,                   -- null = no min
    max_size        REAL,                   -- null = no max
    max_price       REAL,                   -- null = any price (alert on any appearance)
    max_landed      REAL,                   -- null = ignore landed cost
    notes           TEXT,
    active          INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS watchlist_hits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    watchlist_id    INTEGER NOT NULL,
    vendor_key      TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    sex             TEXT,
    size_text       TEXT,
    price_usd       REAL,
    landed_cost     REAL,
    deal_rating     TEXT,
    rarity_score    INTEGER,
    observed_at     TEXT,
    hit_at          TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (watchlist_id) REFERENCES watchlist(id)
);
"""

def init_watchlist_tables(db_path: Path = DB_PATH) -> None:
    conn = get_connection(db_path)
    conn.executescript(WATCHLIST_DDL)
    conn.commit()
    conn.close()


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def add_target(species: str, sex: str = None,
               min_size: float = None, max_size: float = None,
               max_price: float = None, max_landed: float = None,
               notes: str = None, db_path: Path = DB_PATH,
               user_id: int = None) -> int:
    key = normalize_species_key(species)
    conn = get_connection(db_path)
    # `watchlist` may predate the user_id column; add it on demand.
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(watchlist)")]
    if "user_id" not in cols:
        conn.execute("ALTER TABLE watchlist ADD COLUMN user_id INTEGER")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO watchlist
            (species_key, species_display, sex, min_size, max_size,
             max_price, max_landed, notes, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (key, species, sex, min_size, max_size, max_price, max_landed, notes, user_id))
    wid = cur.lastrowid
    conn.commit()
    conn.close()
    return wid


def remove_target(wid: int, db_path: Path = DB_PATH, user_id: int = None) -> None:
    conn = get_connection(db_path)
    if user_id is None:
        conn.execute("UPDATE watchlist SET active = 0 WHERE id = ?", (wid,))
    else:                                   # only the owner may deactivate their target
        conn.execute("UPDATE watchlist SET active = 0 WHERE id = ? AND user_id = ?",
                     (wid, user_id))
    conn.commit()
    conn.close()


def list_targets(db_path: Path = DB_PATH, user_id: int = None) -> list[dict]:
    conn = get_connection(db_path)
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(watchlist)")]
    scoped = user_id is not None and "user_id" in cols
    cur = conn.cursor()
    cur.execute(f"""
        SELECT w.*,
               COUNT(h.id) as hit_count,
               MAX(h.hit_at) as last_hit
        FROM watchlist w
        LEFT JOIN watchlist_hits h ON h.watchlist_id = w.id
        WHERE w.active = 1 {"AND w.user_id = ?" if scoped else ""}
        GROUP BY w.id
        ORDER BY w.id
    """, (user_id,) if scoped else ())
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ─── MATCHING ─────────────────────────────────────────────────────────────────

@dataclass
class WatchlistHit:
    watchlist_id:    int
    target_display:  str
    vendor_key:      str
    scientific_name: str
    sex:             Optional[str]
    size_text:       Optional[str]
    price_usd:       float
    landed_cost:     Optional[float]
    deal_rating:     Optional[str]
    rarity_score:    Optional[int]
    is_fire_deal:    bool
    observed_at:     str
    notes:           str = ""


def check_watchlist(snapshot: list, db_path: Path = DB_PATH) -> list[WatchlistHit]:
    """
    Compare current snapshot against all active watchlist targets.
    Saves hits to watchlist_hits table and returns list of WatchlistHit objects.
    """
    targets = list_targets(db_path)
    if not targets:
        return []

    hits: list[WatchlistHit] = []
    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection(db_path)

    for l in snapshot:
        is_dict = isinstance(l, dict)
        def g(k, d=None):
            return l.get(k, d) if is_dict else getattr(l, k, d)

        l_key    = g("scientific_name_key") or ""
        l_sex    = g("sex") or "U"
        l_price  = g("price_usd") or 0
        l_landed = g("landed_cost")
        l_mid    = g("size_midpoint")
        l_avail  = g("availability", "in_stock")

        if l_avail == "out_of_stock" or not l_price:
            continue

        for t in targets:
            # Species match — require a precise, whole-word binomial match.
            # (The old bidirectional substring test matched EVERY listing whose
            # key was empty, since "" is a substring of anything — that inflated
            # a 4-species watchlist to hundreds of bogus hits.)
            tk = (t["species_key"] or "").strip()
            if not tk or not l_key:
                continue
            if not (l_key == tk
                    or l_key.startswith(tk + " ")     # target "genus species" ⊆ "…species locality"
                    or tk.startswith(l_key + " ")):     # listing is the broader binomial
                continue

            # Sex filter
            if t["sex"] and l_sex != t["sex"]:
                continue

            # Size filter
            if t["min_size"] and l_mid and l_mid < t["min_size"]:
                continue
            if t["max_size"] and l_mid and l_mid > t["max_size"]:
                continue

            # Price filter
            if t["max_price"] and l_price > t["max_price"]:
                continue

            # Landed cost filter
            if t["max_landed"] and l_landed and l_landed > t["max_landed"]:
                continue

            # Hit! Build the hit record
            deal   = g("deal_rating")
            rarity = g("size_class_rarity_score") or g("rarity_score")
            fire   = bool(g("is_fire_deal"))

            hit = WatchlistHit(
                watchlist_id    = t["id"],
                target_display  = t["species_display"],
                vendor_key      = g("vendor_key") or "",
                scientific_name = g("scientific_name") or "",
                sex             = l_sex,
                size_text       = g("size_text"),
                price_usd       = l_price,
                landed_cost     = l_landed,
                deal_rating     = deal,
                rarity_score    = rarity,
                is_fire_deal    = fire,
                observed_at     = str(g("observed_at") or now)[:16],
            )
            hits.append(hit)

            # Save to DB
            conn.execute("""
                INSERT INTO watchlist_hits
                    (watchlist_id, vendor_key, scientific_name, sex, size_text,
                     price_usd, landed_cost, deal_rating, rarity_score, observed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (t["id"], hit.vendor_key, hit.scientific_name, l_sex,
                  hit.size_text, l_price, l_landed, deal, rarity, now))

    conn.commit()
    conn.close()
    return hits


def print_watchlist_hits(hits: list[WatchlistHit]) -> None:
    """Print hits to terminal in a clean format."""
    if not hits:
        print("  No watchlist hits this crawl.")
        return

    print(f"\n{'='*70}")
    print(f"  WATCHLIST HITS ({len(hits)})")
    print(f"{'='*70}")
    for h in hits:
        badges = []
        if h.is_fire_deal:     badges.append("🔥")
        if h.deal_rating == "💎💎": badges.append("💎💎")
        elif h.deal_rating == "💎":  badges.append("💎")
        rarity_str = f" | Rarity {h.rarity_score}/10" if h.rarity_score else ""
        landed_str = f" | ${h.landed_cost:.2f} shipped" if h.landed_cost else ""
        print(f"\n  🎯 {h.target_display}")
        print(f"     {h.scientific_name}  {h.size_text or '?'}\"  {h.sex or '?'}")
        print(f"     ${h.price_usd:.2f}{landed_str}  @{h.vendor_key}  {' '.join(badges)}{rarity_str}")
        print(f"     Observed: {h.observed_at}")
    print(f"{'='*70}\n")


def print_watchlist(db_path: Path = DB_PATH) -> None:
    targets = list_targets(db_path)
    if not targets:
        print("Watchlist is empty. Add targets with --add.")
        return
    print(f"\n{'ID':<4} {'Target':<35} {'Sex':>4} {'Size Range':>12} {'Max Price':>10} {'Max Landed':>11} {'Hits':>5}")
    print("-" * 90)
    for t in targets:
        sz = ""
        if t["min_size"] or t["max_size"]:
            mn = f'{t["min_size"]}"' if t["min_size"] else "any"
            mx = f'{t["max_size"]}"' if t["max_size"] else "any"
            sz = f"{mn}–{mx}"
        mp  = f'${t["max_price"]:.0f}'   if t["max_price"]   else "any"
        ml  = f'${t["max_landed"]:.0f}'  if t["max_landed"]  else "—"
        print(f'{t["id"]:<4} {t["species_display"][:35]:<35} {t["sex"] or "any":>4} {sz:>12} {mp:>10} {ml:>11} {t["hit_count"]:>5}')


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage the species watchlist / price alerts")
    sub = parser.add_subparsers(dest="cmd")

    add_p = sub.add_parser("add", help="Add a watchlist target")
    add_p.add_argument("species",       help='Scientific name e.g. "Grammostola pulchra"')
    add_p.add_argument("--sex",   "-s", choices=["F","M","PF"], default=None)
    add_p.add_argument("--min-size",    type=float, default=None, metavar="INCHES")
    add_p.add_argument("--max-size",    type=float, default=None, metavar="INCHES")
    add_p.add_argument("--max-price",   type=float, default=None, metavar="USD")
    add_p.add_argument("--max-landed",  type=float, default=None, metavar="USD", help="Max price+shipping")
    add_p.add_argument("--notes",       default=None)

    rm_p = sub.add_parser("remove", help="Remove a target by ID")
    rm_p.add_argument("id", type=int)

    sub.add_parser("list", help="Show all active targets")

    chk_p = sub.add_parser("check", help="Check watchlist against current DB snapshot")

    args = parser.parse_args()

    init_watchlist_tables(DB_PATH)

    if args.cmd == "add":
        wid = add_target(
            args.species, sex=args.sex,
            min_size=args.min_size, max_size=args.max_size,
            max_price=args.max_price, max_landed=args.max_landed,
            notes=args.notes, db_path=DB_PATH,
        )
        print(f"✓ Target #{wid} added: {args.species}")
        print_watchlist(DB_PATH)

    elif args.cmd == "remove":
        remove_target(args.id, DB_PATH)
        print(f"✓ Target #{args.id} removed.")

    elif args.cmd == "list":
        print_watchlist(DB_PATH)

    elif args.cmd == "check":
        # Pull latest snapshot and check
        from pipeline import export_only
        from database.history import get_all_history_for_export
        conn = get_connection(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            SELECT vendor_key, MAX(id) AS max_run FROM crawl_runs
            WHERE status IN ('complete','partial') GROUP BY vendor_key
        """)
        run_ids = [r["max_run"] for r in cur.fetchall()]
        if run_ids:
            ph = ",".join("?"*len(run_ids))
            cur.execute(f"SELECT * FROM price_history WHERE crawl_run_id IN ({ph})", run_ids)
            snapshot = [dict(r) for r in cur.fetchall()]
        else:
            snapshot = []
        conn.close()
        hits = check_watchlist(snapshot, DB_PATH)
        print_watchlist_hits(hits)
        if not hits:
            print("  No hits against current DB snapshot.")

    else:
        parser.print_help()
