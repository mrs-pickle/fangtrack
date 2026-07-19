#!/usr/bin/env python3
"""
Move one account's Collection (and optionally Watchlist) rows to another account.

One-off admin migration. Re-points the per-user `user_id` on the `collection`
(and, with --watchlist, `watchlist`) rows from a SOURCE user to a TARGET user.
No listing/species data is touched - only which account owns the rows.

Runs against whatever DB the app is configured for: SQLite locally, or prod
Postgres when DATABASE_URL is set (same routing as the app via get_connection).

DRY-RUN BY DEFAULT - prints exactly what it would do and changes nothing.
Add --commit to actually write.

    # inspect (safe):
    python tools/move_collection.py --from mrs2200 --to mike@fangtrack.com
    # execute:
    python tools/move_collection.py --from mrs2200 --to mike@fangtrack.com --commit

--from / --to match a user by email, display_name, or handle (case-insensitive,
exact). If a term is ambiguous or missing, the script lists candidates and stops.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import get_connection


def _resolve_user(conn, term):
    """Return the single matching user row for `term`, or None. Prints candidates
    when zero or many match so the operator can disambiguate."""
    t = term.strip().lower()
    # Match exact email / display_name / handle, OR the local-part of the email
    # (so "mrs2200" resolves "mrs2200@proton.me").
    rows = [dict(r) for r in conn.execute(
        "SELECT id, email, display_name, handle, is_admin FROM users "
        "WHERE lower(email)=? OR lower(display_name)=? OR lower(handle)=? "
        "OR lower(email) LIKE ?",
        (t, t, t, t + "@%")).fetchall()]
    if len(rows) == 1:
        return rows[0]
    if not rows:
        print(f"  [X] no user matches '{term}' (by email / display_name / handle).")
        # Help the operator: show a few users containing the term.
        like = f"%{t}%"
        near = [dict(r) for r in conn.execute(
            "SELECT id, email, display_name, handle FROM users "
            "WHERE lower(email) LIKE ? OR lower(display_name) LIKE ? OR lower(handle) LIKE ? "
            "ORDER BY id LIMIT 10", (like, like, like)).fetchall()]
        if near:
            print("    did you mean:")
            for r in near:
                print(f"      id={r['id']}  email={r['email']}  name={r['display_name']}  handle={r['handle']}")
    else:
        print(f"  [X] '{term}' is ambiguous - {len(rows)} users match:")
        for r in rows:
            print(f"      id={r['id']}  email={r['email']}  name={r['display_name']}  handle={r['handle']}")
    return None


def _count(conn, table, user_id):
    return conn.execute(f"SELECT COUNT(*) c FROM {table} WHERE user_id=?", (user_id,)).fetchone()["c"]


def main():
    ap = argparse.ArgumentParser(description="Move a user's collection/watchlist to another user.")
    ap.add_argument("--from", dest="src", required=True, help="source account (email/display_name/handle)")
    ap.add_argument("--to", dest="dst", required=True, help="target account (email/display_name/handle)")
    ap.add_argument("--watchlist", action="store_true", help="also move watchlist rows (default: collection only)")
    ap.add_argument("--commit", action="store_true", help="actually write (default: dry-run)")
    args = ap.parse_args()

    tables = ["collection"] + (["watchlist"] if args.watchlist else [])
    conn = get_connection()

    backend = "Postgres (DATABASE_URL)" if os.environ.get("DATABASE_URL") else "SQLite (local)"
    print(f"DB backend: {backend}")
    print(f"Tables in scope: {', '.join(tables)}")
    print()

    print("Resolving accounts...")
    src = _resolve_user(conn, args.src)
    dst = _resolve_user(conn, args.dst)
    if not src or not dst:
        print("\nAborting - could not uniquely resolve both accounts.")
        return 2
    if src["id"] == dst["id"]:
        print("\nSource and target are the SAME account. Nothing to do.")
        return 2

    print(f"  SOURCE  id={src['id']}  {src['email']}  (name={src['display_name']}, admin={src['is_admin']})")
    print(f"  TARGET  id={dst['id']}  {dst['email']}  (name={dst['display_name']}, admin={dst['is_admin']})")
    print()

    total = 0
    plan = []
    for tbl in tables:
        s = _count(conn, tbl, src["id"])
        d = _count(conn, tbl, dst["id"])
        total += s
        plan.append((tbl, s, d))
        print(f"  {tbl:11s}  source has {s:4d} row(s)  |  target already has {d:4d} row(s)")
    print()

    if total == 0:
        print("Source has 0 rows to move. Nothing to do.")
        return 0

    if not args.commit:
        print("DRY-RUN - no changes written. Re-run with --commit to move the rows above.")
        print(f"Effect: re-point {total} row(s) from user_id={src['id']} to user_id={dst['id']}.")
        if any(d > 0 for _, _, d in plan):
            print("NOTE: target already owns some rows - after the move both sets coexist "
                  "(possible duplicate species). Review the collection page afterward.")
        return 0

    # Execute.
    moved = 0
    for tbl in tables:
        cur = conn.execute(f"UPDATE {tbl} SET user_id=? WHERE user_id=?", (dst["id"], src["id"]))
        n = getattr(cur, "rowcount", None)
        n = n if (n is not None and n >= 0) else _count(conn, tbl, dst["id"])
        print(f"  {tbl}: moved rows (source->target).")
        moved += (n if isinstance(n, int) and n >= 0 else 0)
    conn.commit()

    print("\nVerification (post-move counts):")
    for tbl in tables:
        s = _count(conn, tbl, src["id"])
        d = _count(conn, tbl, dst["id"])
        print(f"  {tbl:11s}  source now {s:4d}  |  target now {d:4d}")
    print(f"\nOK - Done. Committed to {backend}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
