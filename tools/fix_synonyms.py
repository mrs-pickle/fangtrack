#!/usr/bin/env python3
"""
DB Migration: Remap scientific_name_key for all existing price_history rows
using the current synonym table. Run once after updating synonyms.py.

Also updates the tliltocatl albopilosum → albopilosus normalization
and merges any split pools caused by synonym divergence.

Safe to run multiple times (idempotent).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import get_connection, DB_PATH
from normalize.species import normalize_species_key

def run_migration(db_path=DB_PATH, dry_run=False):
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT scientific_name, scientific_name_key FROM price_history")
    rows = cur.fetchall()

    updates = []
    for row in rows:
        raw_name = row["scientific_name"]
        old_key  = row["scientific_name_key"]
        new_key  = normalize_species_key(raw_name)
        if new_key != old_key:
            updates.append((new_key, raw_name, old_key))

    print(f"Rows needing remapping: {len(updates)}")
    for new_key, name, old_key in updates:
        print(f"  '{name}': '{old_key}' → '{new_key}'")

    if not dry_run and updates:
        for new_key, name, old_key in updates:
            conn.execute("""
                UPDATE price_history
                SET scientific_name_key = ?
                WHERE scientific_name = ? AND scientific_name_key = ?
            """, (new_key, name, old_key))
        conn.commit()
        print(f"\n{len(updates)} keys remapped in DB.")
    elif dry_run:
        print("\n(dry run — no changes made)")
    else:
        print("\nNo remapping needed.")

    conn.close()

if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    run_migration(DB_PATH, dry_run=dry)
