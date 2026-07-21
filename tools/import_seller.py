"""
Private Seller List Importer
AI-powered parser for unstructured price lists from Facebook, text messages,
screenshots, forum posts, etc.

Usage:
  python tools/import_seller.py --file seller_list.txt --name "John Smith"
  python tools/import_seller.py --file seller_list.txt --name "FB Seller" --dry-run
  python tools/import_seller.py --paste --name "FB Seller"   # interactive paste
  python tools/import_seller.py --list                        # show all community sellers

The parser uses Claude API to handle any format: tables, dashes, colons, plain text,
copy-paste from Facebook, screenshots OCR'd to text, etc.

Falls back to regex parser if API key is not available.
"""
import sys
import os
import re
import json
import argparse
import textwrap
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import get_connection, init_db, upsert_vendor, DB_PATH
from normalize.species import normalize_species_key
from normalize.size import parse_size

# ---------------------------------------------------------------------------
# AI PARSER (uses Claude API)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a tarantula market data extractor.
Extract every priced animal listing from the user's text and return ONLY valid JSON.
No preamble, no markdown, no code fences.

Output format — a JSON array of objects:
[
  {
    "scientific_name": "Grammostola pulchripes",
    "common_name": "Chaco Golden Knee",  // or null
    "size": "0.5",                        // inches as decimal string, or null
    "sex": null,                          // null | "F" | "M" | "PF" | "PM"
    "price": 31.00,                       // unit price as float
    "qty": 1,                             // quantity available
    "notes": null,                        // any extra notes (locale, CB, WC, etc.)
    "category": "T"                       // T=tarantula S=spider SC=scorpion C=centipede M=millipede O=other
  }
]

Rules:
- Only include entries that have BOTH a species name AND a price.
- Convert bulk pricing to per-unit: "10/$100" → price=10.0, qty=10
- Size must be in inches as a decimal: "1/4 inch" → "0.25", "2-3 inch" → "2-3"
- sex: F=confirmed female, M=confirmed male, PF=probable female, PM=probable male, null=unsexed/unknown
- Skip non-animal items (isopods, feeders, supplies, enclosures) unless they are clearly scorpions/centipedes/millipedes
- Do not include items with no price listed
- Return [] if no valid listings found
"""


def parse_with_claude(text: str, seller_name: str) -> list[dict]:
    """Use Claude API to parse any format of seller price list."""
    try:
        import urllib.request
        import urllib.error

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return []

        payload = json.dumps({
            "model": "claude-sonnet-4-6",
            "max_tokens": 4096,
            "system": SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": f"Seller: {seller_name}\n\n{text}"
                }
            ]
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())

        raw = data["content"][0]["text"].strip()
        # Strip any accidental markdown fences
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.M).strip()
        return json.loads(raw)

    except Exception as e:
        print(f"[AI parser] Error: {e} — falling back to regex parser")
        return []


# ---------------------------------------------------------------------------
# REGEX FALLBACK PARSER
# ---------------------------------------------------------------------------

def parse_with_regex(text: str) -> list[dict]:
    """
    Best-effort regex parser for common price list formats.
    Handles the formats we've seen from the Facebook sellers Mike shared.
    """
    listings = []
    current_category = "T"  # default: tarantula

    CAT_MAP = {
        "tarantula": "T", "spider": "S", "scorpion": "SC",
        "centipede": "C", "millipede": "M", "arachnid": "S",
        "mygalomorph": "S", "isopod": "O", "mantid": "O",
    }

    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Detect category headers like "Tarantulas:", "True Spiders & mygalomorphs:"
        for kw, cat in CAT_MAP.items():
            if re.match(rf'^{kw}', line, re.IGNORECASE) and ":" in line:
                current_category = cat
                break

        # Skip lines with no price
        if not re.search(r'\$\d+', line):
            continue

        # --- Price ---
        # Handle bulk: "10/$100" → per unit $10
        bulk = re.search(r'(\d+)/\$(\d+(?:\.\d+)?)', line)
        if bulk:
            qty_bulk = int(bulk.group(1))
            total_price = float(bulk.group(2))
            price = total_price / qty_bulk
            qty = qty_bulk
        else:
            pm = re.search(r'\$(\d+(?:\.\d+)?)', line)
            if not pm:
                continue
            price = float(pm.group(1))
            qty = 1
            # Check qty prefix: "2x", "(3x)", "3x "
            qm = re.match(r'[\(*]?(\d+)[x×)]\s+', line)
            if qm:
                qty = int(qm.group(1))

        # --- Species name ---
        # Strip leading quantity patterns
        name_line = re.sub(r'^[\(*]?\d+[x×)]\s+', '', line).strip()
        # Strip size and price from the end
        name_line = re.sub(r'\$[\d./]+.*$', '', name_line).strip()
        name_line = re.sub(r'\d+[/\s]+\$[\d.]+.*$', '', name_line).strip()

        # Extract size first (before it gets mixed into the name)
        size_match = re.search(
            r'((?:\d+\s+)?(?:\d+/\d+|\d+(?:\.\d+)?|\d+\s*½|\d+\s*¼)'
            r'(?:\s*[-–]\s*(?:\d+/\d+|\d+(?:\.\d+)?))?\s*(?:"|"|inch(?:es)?|\'))',
            name_line, re.IGNORECASE,
        )
        size_str = None
        if size_match:
            raw_size = size_match.group(0).strip()
            # Normalize
            raw_size = raw_size.replace("½", ".5").replace("¼", ".25")
            raw_size = re.sub(r'(?:inch(?:es)?|")', '', raw_size, flags=re.I).strip()
            size_str = raw_size
            # Remove from name
            name_line = name_line[:size_match.start()].strip()

        # Extract sex markers
        sex = None
        sex_patterns = [
            (r'\bprobable\s+female\b', "PF"),
            (r'\bprob(?:able)?\s*f(?:emale)?\b', "PF"),
            (r'\bpf\b', "PF"),
            (r'\bfemale\b', "F"),
            (r'\btcf\b', "F"),  # true confirmed female
            (r'\bmf\b', "F"),   # mature female
            (r'\bmature\s+female\b', "F"),
            (r'\bmale\b', "M"),
            (r'\bmm\b', "M"),   # mature male
            (r'\bmature\s+male\b', "M"),
        ]
        for pat, code in sex_patterns:
            if re.search(pat, name_line, re.IGNORECASE):
                sex = code
                name_line = re.sub(pat, '', name_line, flags=re.IGNORECASE).strip()
                break

        # Grab common name from parentheses if present
        common = None
        cm = re.search(r'\(([^)]+)\)', name_line)
        if cm:
            candidate = cm.group(1).strip()
            # Common names don't have digits (usually)
            if not re.search(r'\d', candidate) and len(candidate) > 3:
                common = candidate
            name_line = re.sub(r'\s*\([^)]+\)', '', name_line).strip()

        # What's left should be the scientific name
        sci_name = name_line.strip(" -*•·").strip()
        if not sci_name or len(sci_name) < 4:
            continue

        # Extract any locale notes (e.g. "Borneo", "Thailand", "TCF")
        notes = None
        locale_match = re.search(
            r'\b(CB|WC|CBB|TCF|Kigoma|Borneo|Thailand|Usambara|RCF|NCF'
            r'|probable female|probable|wild caught|captive bred)\b',
            line, re.IGNORECASE,
        )
        if locale_match:
            notes = locale_match.group(0).strip()

        listings.append({
            "scientific_name": sci_name,
            "common_name":     common,
            "size":            size_str,
            "sex":             sex,
            "price":           price,
            "qty":             qty,
            "notes":           notes,
            "category":        current_category,
        })

    return listings


# ---------------------------------------------------------------------------
# DB INSERTION
# ---------------------------------------------------------------------------

def _website_species_keys(db_path) -> list:
    """Canonical species keys that exist on WEBSITE vendors (not private sellers)."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT scientific_name_key FROM price_history "
            "WHERE scientific_name_key IS NOT NULL AND vendor_key NOT IN "
            "(SELECT vendor_key FROM vendors WHERE platform='private_seller')").fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []
    finally:
        conn.close()


def _snap_to_website_species(name_key: str, website_keys: list) -> str:
    """Mike's rule: a private-seller listing must CONNECT to the existing species its
    spelling most closely resembles, never create its own species page. If the key
    already matches a website species, keep it. Otherwise snap to the closest website
    species — but only on a VERY close spelling match (cutoff 0.9), so a genuine typo
    ('grammastola pulchra' → 'grammostola pulchra') connects while two distinct
    species ('augacephalus rufus' vs 'augacephalus junodi') never get merged."""
    import difflib
    if not name_key or not website_keys or name_key in website_keys:
        return name_key
    m = difflib.get_close_matches(name_key, website_keys, n=1, cutoff=0.9)
    return m[0] if m else name_key


def insert_listings(listings: list[dict], seller_name: str,
                    seller_key: str = None, db_path=DB_PATH,
                    dry_run: bool = False, contact: str = "",
                    user_id: int = None) -> int:
    """Insert parsed listings into price_history.

    `contact` (email / phone / FB handle) is stored on the vendor record so the
    owner viewing their own seller's listings knows how to reach them.

    `user_id` is the owner. Private-seller lists are PER-USER private: a user's
    imports are visible only to that account. The vendor_key is namespaced by
    user_id (`priv_<uid>_<slug>`) so two users importing the same seller name
    can't collide onto one shared vendor row.
    """
    if not listings:
        return 0

    if seller_key is None:
        slug = re.sub(r'[^a-z0-9_]', '_', seller_name.lower().strip())
        slug = re.sub(r'_+', '_', slug).strip('_')
        seller_key = f"priv_{user_id}_{slug}" if user_id is not None else slug

    if not dry_run:
        init_db(db_path)
        upsert_vendor(
            vendor_key=seller_key,
            vendor_name=seller_name,
            base_url=contact or "",   # contact info reuses the base_url column
            platform="private_seller",
            db_path=db_path,
            user_id=user_id,
        )

    now = datetime.now(timezone.utc).isoformat()
    website_keys = _website_species_keys(db_path)   # for the fuzzy connect-to-existing
    rows = []
    for entry in listings:
        name = entry.get("scientific_name", "").strip()
        if not name:
            continue

        try:
            name_key = normalize_species_key(name)
        except Exception:
            name_key = name.lower()
        # Connect this private listing to the nearest existing website species
        # (never let it create its own species page — Mike's rule).
        name_key = _snap_to_website_species(name_key, website_keys)

        size_str = entry.get("size")
        sz_min, sz_max, sz_mid = parse_size(size_str)

        sex = entry.get("sex") or "U"
        price = float(entry.get("price") or 0)
        qty = int(entry.get("qty") or 1)
        notes_raw = entry.get("notes") or ""
        cat = entry.get("category") or "T"
        common = entry.get("common_name")

        CAT_DISPLAY = {"T": "Tarantula", "S": "Spider", "SC": "Scorpion",
                       "C": "Centipede", "M": "Millipede", "O": "Other"}
        SEX_DISPLAY = {"F": "Female", "M": "Male", "PF": "Probable Female",
                       "PM": "Probable Male", "U": "Unsexed"}

        full_notes = f"[{CAT_DISPLAY.get(cat, cat)}]"
        if notes_raw:
            full_notes += f" {notes_raw}"

        rows.append((
            seller_key, name, name_key, common,
            sex, SEX_DISPLAY.get(sex, "Unsexed"),
            size_str, sz_min, sz_max, sz_mid,
            price, None, "in_stock", qty,
            None, None, full_notes,
            None, None, None, None, None,
            round(price / sz_mid, 2) if sz_mid and sz_mid > 0 else None,
            0, 0, 0, 0, 0, 0,
            None, "community",
            f"{name} {size_str or ''} {sex}".strip(), None, f"${price:.2f}",
            0, now,
        ))

    if dry_run:
        return len(rows)

    conn = get_connection(db_path)
    run_id = conn.execute("""
        INSERT INTO crawl_runs
          (vendor_key, status, pages_crawled, products_found, variants_found,
           started_at, finished_at, notes)
        VALUES (?, 'complete', 1, ?, ?, ?, ?, ?)
    """, (seller_key, len(rows), len(rows), now, now,
          f"Imported via import_seller.py — {now[:10]}")).lastrowid
    conn.commit()

    # Update crawl_run_id in rows
    rows = [r[:34] + (run_id,) + r[35:] for r in rows]

    conn.executemany("""
        INSERT INTO price_history
            (vendor_key, scientific_name, scientific_name_key, common_name,
             sex, sex_display, size_text, size_min, size_max, size_midpoint,
             price_usd, regular_price_usd, availability, quantity,
             product_url, variant_name, notes,
             deal_rating, deal_reason, current_lowest, market_average, historical_low,
             price_per_inch, is_new, is_price_drop, is_new_historical_low,
             is_returned_to_stock, is_sold_out, is_price_increase,
             previous_price, verification_level,
             raw_title, raw_variant, raw_price,
             crawl_run_id, observed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, rows)
    conn.commit()
    conn.close()
    return len(rows)


def list_sellers(db_path=DB_PATH):
    """Print all community sellers in the DB."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT v.vendor_key, v.vendor_name, COUNT(ph.id) as listings,
               MAX(ph.observed_at) as last_imported
        FROM vendors v
        LEFT JOIN price_history ph ON ph.vendor_key = v.vendor_key
        WHERE v.platform = 'private_seller'
        GROUP BY v.vendor_key
        ORDER BY last_imported DESC
    """)
    rows = cur.fetchall()
    conn.close()
    if not rows:
        print("No private sellers in DB yet.")
        return
    print(f"\n{'Seller':<35} {'Listings':>8}  {'Last Imported'}")
    print("-" * 65)
    for r in rows:
        print(f"{r['vendor_name']:<35} {r['listings']:>8}  {r['last_imported'][:10]}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import a private seller price list into the market tracker DB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          python tools/import_seller.py --file eric_list.txt --name "Eric Madrid"
          python tools/import_seller.py --paste --name "Facebook Seller July 11"
          python tools/import_seller.py --file list.txt --name "Aaron" --dry-run
          python tools/import_seller.py --list
        """),
    )
    parser.add_argument("--file",     help="Path to text file containing the price list")
    parser.add_argument("--name",     help="Seller name (used as label in DB)")
    parser.add_argument("--key",      help="Seller DB key (auto-generated from name if omitted)")
    parser.add_argument("--paste",    action="store_true",
                        help="Paste list interactively (end with Ctrl+D on Mac/Linux or Ctrl+Z on Windows)")
    parser.add_argument("--dry-run",  action="store_true",
                        help="Parse and preview without inserting into DB")
    parser.add_argument("--list",     action="store_true",
                        help="List all community sellers already in the DB")
    parser.add_argument("--no-ai",    action="store_true",
                        help="Skip Claude API and use regex parser only")
    args = parser.parse_args()

    if args.list:
        list_sellers(DB_PATH)
        sys.exit(0)

    if not args.name and not args.dry_run:
        print("Error: --name is required (e.g. --name 'Eric Madrid')")
        sys.exit(1)

    seller_name = args.name or "Unknown Seller"

    # Read input text
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    elif args.paste:
        print(f"Paste the price list for '{seller_name}' below.")
        print("End with Ctrl+D (Mac/Linux) or Ctrl+Z then Enter (Windows):")
        print("—" * 50)
        lines = []
        try:
            while True:
                lines.append(input())
        except EOFError:
            pass
        text = "\n".join(lines)
    else:
        print("Error: provide --file or --paste")
        sys.exit(1)

    if not text.strip():
        print("No input text provided.")
        sys.exit(1)

    # Parse
    print(f"\nParsing list for: {seller_name}")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    listings = []

    if not args.no_ai and api_key:
        print("  Using Claude AI parser...")
        listings = parse_with_claude(text, seller_name)
        if listings:
            print(f"  AI parser found {len(listings)} listings")
        else:
            print("  AI parse returned nothing — falling back to regex")

    if not listings:
        print("  Using regex parser...")
        listings = parse_with_regex(text)
        print(f"  Regex parser found {len(listings)} listings")

    if not listings:
        print("No listings parsed. Check input format.")
        sys.exit(1)

    # Preview
    print(f"\n{'#':<4} {'Species':<40} {'Size':>6} {'Sex':>4} {'Qty':>4} {'Price':>8}")
    print("-" * 75)
    for i, l in enumerate(listings[:30], 1):
        print(f"{i:<4} {l['scientific_name'][:40]:<40} "
              f"{l['size'] or '—':>6} {l['sex'] or 'U':>4} "
              f"{l['qty']:>4} ${l['price']:>7.2f}")
    if len(listings) > 30:
        print(f"  ... and {len(listings) - 30} more")

    if args.dry_run:
        print(f"\nDry run — {len(listings)} listings found, nothing inserted.")
        sys.exit(0)

    # Insert
    confirm = input(f"\nInsert {len(listings)} listings for '{seller_name}' into DB? [y/N] ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        sys.exit(0)

    count = insert_listings(listings, seller_name, seller_key=args.key, db_path=DB_PATH)
    print(f"\nInserted {count} listings for '{seller_name}'. Run --export-only to rebuild workbook.")
