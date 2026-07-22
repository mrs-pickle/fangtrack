#!/usr/bin/env python3
"""
Species-catalog fragment audit (read-only).

Surfaces the "messy species list": entries likely to be the SAME animal split
across DIFFERENT scientific_name_keys — the class of bug behind Augacephalus
rufus showing three times.

It is deliberately CONSERVATIVE about what it SUGGESTS, because a naive merge is
worse than none:

  AUTO-SUGGESTED (safe): NEAR-DUPLICATE DISPLAY within one genus (≥0.90 similar)
    = a spelling variant / typo, e.g. "Brachypelma boehmei" vs "boehemi".

  REVIEW ONLY (listed, never suggested — a human decides):
    · same epithet across different genera — mostly COINCIDENTAL (shared
      epithets/localities like gigas, metallica, versicolor, 'peru' collide
      across unrelated animals: Archispirostreptus gigas ≠ Hysterocrates gigas),
      but occasionally a real genus synonym (Cyriopagopus/Melopoeus lividus).
    · shared common name across different epithets — usually DISTINCT species
      that share a generic common name (Heterometrus silenus vs spinifer).

NOTHING is changed. Add accepted SUGGESTED lines to normalize/key_aliases.py
(they self-heal on the next crawl). Runs against the app's configured DB
(SQLite locally / Postgres on prod) via get_species_catalog.

    python tools/species_audit.py
    python tools/species_audit.py --sim 0.92
"""
import sys, os, argparse
from difflib import SequenceMatcher
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app  # noqa: E402

_PLACEHOLDER = {"sp", "sp.", "cf", "cf.", "aff", "aff."}


def _norm(s):
    return " ".join((s or "").lower().split())


def _epithet(key):
    t = (key or "").split()
    if len(t) < 2:
        return ""
    return " ".join(t[2:]) if t[1] in _PLACEHOLDER else t[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", type=float, default=0.90, help="display similarity threshold")
    args = ap.parse_args()

    cat = app.get_species_catalog(app.DB_PATH)
    print(f"Catalog: {len(cat)} canonical species\n")
    suggestions = {}   # loser_key -> winner_key

    # ── AUTO-SUGGESTED: near-duplicate display within a genus (typo) ─────────
    by_genus = defaultdict(list)
    for s in cat:
        by_genus[(s.get("key") or "").split()[0]].append(s)
    print(f"── NEAR-DUPLICATE DISPLAY within a genus (≥{args.sim}, likely typo) ──")
    seen, hits = set(), 0
    for genus, rows in by_genus.items():
        if not genus:
            continue
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                if a["key"] == b["key"]:
                    continue
                ratio = SequenceMatcher(None, _norm(a["display"]), _norm(b["display"])).ratio()
                pair = tuple(sorted((a["key"], b["key"])))
                if ratio >= args.sim and pair not in seen:
                    seen.add(pair)
                    hits += 1
                    lo, hi = (a, b) if (a.get("n") or 0) <= (b.get("n") or 0) else (b, a)
                    suggestions.setdefault(lo["key"], hi["key"])
                    print(f"  {ratio:.2f}  {a['display']!r} ({a.get('n') or 0})  ~  "
                          f"{b['display']!r} ({b.get('n') or 0})")
    if not hits:
        print("  none")

    print(f"\n── SUGGESTED KEY_ALIASES ({len(suggestions)}) — verify each, then paste ──")
    for loser, winner in sorted(suggestions.items()):
        print(f'    "{loser}": "{winner}",')

    # ── REVIEW ONLY 1: same epithet, different genus ────────────────────────
    by_ep = defaultdict(list)
    for s in cat:
        e = _epithet(s["key"])
        if e:
            by_ep[e].append(s)
    print("\n── REVIEW ONLY: same epithet, different genus (verify — usually coincidental) ──")
    shown = 0
    for e, rows in sorted(by_ep.items()):
        if len(rows) >= 2 and len({r["key"].split()[0] for r in rows}) >= 2 and shown < 40:
            shown += 1
            print(f'  "{e}": ' + ", ".join(f"{r['display']}({r.get('n') or 0})"
                                            for r in sorted(rows, key=lambda r: -(r.get('n') or 0))))

    # ── REVIEW ONLY 2: shared common name across different epithets ─────────
    by_common = defaultdict(list)
    for s in cat:
        c = _norm(s.get("common"))
        if c:
            by_common[c].append(s)
    print("\n── REVIEW ONLY: shared common name across DIFFERENT epithets ──")
    print("   (usually DISTINCT species sharing a generic common name — do NOT blindly merge)")
    shown = 0
    for c, rows in sorted(by_common.items(), key=lambda kv: -len(kv[1])):
        if len({r["key"] for r in rows}) >= 2 and len({_epithet(r["key"]) for r in rows}) >= 2 and shown < 20:
            shown += 1
            print(f'  "{c}": ' + ", ".join(f"{r['display']}({r.get('n') or 0})"
                                            for r in sorted(rows, key=lambda r: -(r.get('n') or 0))))
    print("\nDone. Add accepted SUGGESTED lines to normalize/key_aliases.py "
          "(they self-heal on the next crawl).")


if __name__ == "__main__":
    main()
