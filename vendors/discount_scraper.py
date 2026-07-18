"""
Discount Code Scraper
Scans vendor homepages, promo pages, and banner areas for active discount codes.

Patterns detected:
  - "use code WORD for X% off"
  - "X% off with code WORD"
  - "promo code: WORD"
  - Affiliate codes from known community sources
  - Seasonal/holiday banners

Run standalone:   python vendors/discount_scraper.py
Or via main.py:   python main.py --scan-promos
"""
import asyncio
import logging
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from database.db import upsert_discount_code, init_discount_tables, DB_PATH

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# ---------------------------------------------------------------------------
# Known / seeded codes (from research, affiliate pages, community posts)
# Mark is_verified=1 only if manually confirmed working.
# ---------------------------------------------------------------------------
KNOWN_CODES = [
    # vendor_key, code, type, value, min_order, source_note, is_verified
    # The Tarantula Collective affiliate codes (found on their dealer page)
    ("spidershoppe",       "COLLECTIVE10",  "pct", 10.0,  None, "TarantulaCollective affiliate", 0),
    ("marshall_arachnids", "TTC10",         "pct", 10.0,  None, "TarantulaCollective affiliate", 0),
    ("juices_arthropods",  "TTC10",         "pct", 10.0,  None, "TarantulaCollective affiliate", 0),
    ("arachnid_rarities",  "COLLECTIVE10",  "pct", 10.0,  None, "TarantulaCollective affiliate", 0),
    # Fear Not has a Tarantula Talk discount
    ("fear_not",           "TARANTULAT ALK","pct", 10.0,  None, "TarantulaTalk community", 0),
    # Exotics Unlimited VIP program (stacking 10-15%)
    ("exotics_unlimited",  "VIP10",         "pct", 10.0,  None, "EU VIP member discount", 0),
    ("exotics_unlimited",  "VIP15",         "pct", 15.0,  None, "EU VIP member discount (higher tier)", 0),
]

# ---------------------------------------------------------------------------
# Pages to scan per vendor (paths appended to BASE_URL)
# ---------------------------------------------------------------------------
VENDOR_PROMO_PAGES = {
    "jamies":             ["https://jamiesontheweb.com", "https://jamiesontheweb.com/pages/about"],
    "fear_not":           ["https://fearnottarantulas.com", "https://fearnottarantulas.com/pages/shipping-info"],
    "arachnoeden":        ["https://arachnoeden.org"],
    "spidershoppe":       ["https://spidershoppe.com"],
    "exotics_unlimited":  ["https://exoticsunlimitedusa.com", "https://exoticsunlimitedusa.com/pages/vip"],
    "plumbs_exotics":     ["https://plumbsexotics.com"],
    "hardcore_arachnids": ["https://hardcorearachnids.com"],
    "buddha_bugs":        ["https://buddhabugsexotics.com"],
    "tydye":              ["https://tydyeexotic.com"],
    "marshall_arachnids": ["https://marshallarachnids.com"],
    "micro_wilderness":   ["https://microwilderness.com"],
    "fanghub":            ["https://fanghubtarantulas.com"],
    "wonderland_exotics": ["https://wonderlandexoticsllc.com"],
    "big_zs":             ["https://bigzsexoticpets.com"],
    "ghostys":            ["https://ghostystarantulas.com"],
    "eight_deadly_sins":  ["https://eightdeadlysins.net"],
    "swifts_inverts":     ["https://swiftsinverts.com"],
    "spider_room":        ["https://thespiderroom.com", "https://thespiderroom.com/shipping"],
    "urban_tarantulas":   ["https://www.urbantarantulas.com"],
    "juices_arthropods":  ["https://www.juicesarthropods.com"],
    "arachnid_rarities":  ["https://www.arachnidrarities.com"],
    "tarantula_spiders":  ["https://tarantulaspiders.com"],
    "joshsfrogs":         ["https://www.joshsfrogs.com"],
}

# ---------------------------------------------------------------------------
# Regex patterns to detect discount codes and their values
# ---------------------------------------------------------------------------
CODE_PATTERNS = [
    # "use code WORD for X% off"  (non-greedy gap so it doesn't eat the number)
    re.compile(
        r'use\s+(?:code|coupon|promo(?:tion)?|discount)\s+["\']?([A-Z0-9_-]{3,20})["\']?'
        r'[^\n%]*?([\d]{1,3})%\s*off',
        re.IGNORECASE,
    ),
    # "save X% with code WORD" / "X% off with code WORD"
    re.compile(
        r'(?:save\s+)?([\d]{1,3})%\s*off\s+(?:with\s+)?(?:code|coupon|promo)?\s*["\']?([A-Z0-9_-]{3,20})["\']?',
        re.IGNORECASE,
    ),
    # "code: WORD" or "coupon: WORD" near a % number
    re.compile(
        r'(?:code|coupon|promo(?:tion)?)[\s:]+["\']?([A-Z][A-Z0-9_-]{2,19})["\']?',
        re.IGNORECASE,
    ),
    # "WORD = X% off" (some sites list it this way)
    re.compile(
        r'["\']([A-Z][A-Z0-9_-]{2,19})["\']?\s*[=-]\s*([\d]{1,3})%\s*off',
        re.IGNORECASE,
    ),
    # Flat discount: "use code WORD for $X off"
    re.compile(
        r'use\s+(?:code|coupon)\s+["\']?([A-Z0-9_-]{3,20})["\']?'
        r'[^\n$]*?\$([\d]+(?:\.\d+)?)\s*off',
        re.IGNORECASE,
    ),
]

# Words that look like promo codes but never are — common English + the product
# categories that sale copy mentions ("60% off TARANTULAS" must not become a
# code named TARANTULAS).
IGNORE_CODES = {
    "OFF","AND","FOR","USE","GET","THE","FREE","CODE","WITH","SAVE",
    "YOUR","ORDER","ALSO","FROM","INTO","OVER","THAT","THIS","SHOP",
    "TAKE","JUST","ONLY","NEED","HAVE","WILL","MORE","THAN","SAME",
    "HTML","CSS","PHP","HTTP","HTTPS","JSON","FORM","CLICK","HERE",
    "NEXT","BACK","ITEM","LIST","SALE","SIZE","INFO","EACH","PLUS",
    "SOME","MANY","MOST","BEEN","WERE","THEY","THEIR","THERE","WHEN",
    # product categories / sale-copy nouns
    "TARANTULAS","TARANTULA","INVERTEBRATES","INVERTS","SCORPIONS","SCORPION",
    "SPIDERS","SPIDER","SLINGS","SLING","ISOPODS","ISOPOD","CENTIPEDES",
    "MILLIPEDES","ROACHES","EVERYTHING","SITEWIDE","STOREWIDE","PRODUCTS",
    "ORDERS","PURCHASE","CHECKOUT","ANYTHING","SELECT","ENTIRE","LIVESTOCK",
    # scraped-noise words seen in the wild
    "SHOULD","EMAIL","CODES","WINDOW","TOWARDS","LINKING","PLEASE","INFORMATION",
    "COUNTRY","OPTIONAL","INVALID","DIGITS","ENABLED","DISABLED","REQUIRED",
}


# Sitewide / storewide sale banners (auto-discount, often no code needed).
SITEWIDE_PATTERNS = [
    re.compile(r'(\d{1,2})%\s*off\s*(?:everything|sitewide|site-?wide|store-?wide|'
               r'entire\s+(?:order|store)|all\s+(?:products|orders|tarantulas|inverts))', re.I),
    re.compile(r'(?:sitewide|site-?wide|store-?wide|black\s*friday|cyber\s*monday|'
               r'holiday|labor\s*day|memorial\s*day|anniversary|flash)\s*sale[^\n%]{0,30}?(\d{1,2})%', re.I),
    re.compile(r'save\s*(\d{1,2})%\s*(?:on\s*)?(?:everything|sitewide|all)', re.I),
]


def detect_sitewide_sale(text: str):
    """Return (pct, context) for a sitewide sale banner, or None."""
    for pat in SITEWIDE_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                pct = float(m.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= pct <= 80:
                i = m.start()
                ctx = text[max(0, i - 40):m.end() + 40].replace("\n", " ").strip()
                return pct, ctx
    return None


# BOGO / multi-buy offers. The effective per-item discount depends on the cart,
# so we capture these as an informational flag (not a computed price) — honest.
BOGO_PATTERNS = [
    re.compile(r'\bbogo\b', re.I),
    re.compile(r'buy\s*(?:one|1)\s*get\s*(?:one|1)\s*(?:free|half|50%)?', re.I),
    re.compile(r'buy\s*(\d)\s*get\s*(\d)\s*(?:free|off|half)?', re.I),
    re.compile(r'\b2\s*for\s*1\b', re.I),
    re.compile(r'\b(?:second|2nd)\s+(?:one\s+)?(?:free|half\s*off|50%\s*off)', re.I),
]

# Holiday / seasonal events — used to recognise a promo even when the % lives in
# a nearby word or an image. Feeds both the % sitewide detector and, failing a
# number, an informational "holiday sale" flag.
HOLIDAY_EVENTS = [
    "black friday", "cyber monday", "boxing day", "christmas", "holiday",
    "new year", "new year's", "valentine", "st patrick", "easter", "spring",
    "memorial day", "july 4th", "4th of july", "independence day", "labor day",
    "halloween", "thanksgiving", "anniversary", "birthday sale", "flash sale",
    "summer sale", "winter sale", "end of year", "clearance",
]


def detect_bogo(text: str):
    """Return a short BOGO/multi-buy context string, or None."""
    for pat in BOGO_PATTERNS:
        m = pat.search(text)
        if m:
            i = m.start()
            return text[max(0, i - 30):m.end() + 30].replace("\n", " ").strip()
    return None


def detect_holiday_promo(text: str):
    """Return (pct_or_None, event, context) when a named holiday sale is present.
    If a percentage sits near the event word we capture it; otherwise pct is None
    and it's stored as an informational flag (buyer should check the banner)."""
    low = text.lower()
    for ev in HOLIDAY_EVENTS:
        idx = low.find(ev)
        if idx == -1:
            continue
        window = low[max(0, idx - 60): idx + 80]
        if "sale" not in window and "off" not in window and "%" not in window:
            continue  # the word alone (e.g. "christmas island") isn't a promo
        pm = re.search(r'(\d{1,2})\s*%', window)
        pct = None
        if pm:
            try:
                v = float(pm.group(1))
                if 1 <= v <= 80:
                    pct = v
            except ValueError:
                pass
        ctx = text[max(0, idx - 30): idx + 60].replace("\n", " ").strip()
        return pct, ev, ctx
    return None


def _is_plausible_code(s: str) -> bool:
    """Return True if s looks like a discount code rather than a common word."""
    if not re.fullmatch(r'[A-Z][A-Z0-9_-]{3,14}', s):
        return False
    if s in IGNORE_CODES:
        return False
    # All-letter codes must be ≥5 chars (3-4 letter words are usually English)
    if re.fullmatch(r'[A-Z]{4,}', s) and len(s) < 5:
        return False
    return True


def extract_codes_from_text(text: str) -> list[dict]:
    """
    Scan raw page text for discount codes.
    Returns list of {code, discount_type, discount_value, context} dicts.
    """
    found = []
    seen_codes = set()

    for pat in CODE_PATTERNS:
        for m in pat.finditer(text):
            groups = m.groups()
            # Determine which group is the code vs the value
            code = None
            value = None
            discount_type = "pct"

            for g in groups:
                if g is None:
                    continue
                g = g.strip().upper()
                # Is it numeric? → probably the value
                if re.fullmatch(r'\d+(?:\.\d+)?', g):
                    value = float(g)
                elif _is_plausible_code(g):
                    code = g

            if not code or code in seen_codes:
                continue
            # Sanity checks: code shouldn't look like a common English word
            if code.lower() in {"code", "coupon", "promo", "sale", "save"}:
                continue
            # A code with no real discount value is noise ("code: EMAIL" with no
            # percent nearby). Only store codes that carry an actual saving.
            if value is None or value <= 0:
                continue
            # Value sanity: 0 < pct <= 90, or $0 < flat <= 200
            if discount_type == "pct" and not (1 <= value <= 90):
                continue
            if discount_type == "flat" and not (1 <= value <= 200):
                continue

            # Extract surrounding context (50 chars either side)
            start = max(0, m.start() - 50)
            end = min(len(text), m.end() + 50)
            context = text[start:end].replace("\n", " ").strip()

            seen_codes.add(code)
            found.append({
                "code":          code,
                "discount_type": discount_type,
                "discount_value": value,
                "context":       context,
            })

    return found


async def scan_vendor(vendor_key: str, urls: list[str],
                      client: httpx.AsyncClient, db_path=DB_PATH) -> int:
    """Scan one vendor's pages for discount codes. Returns count found."""
    total = 0
    for url in urls:
        try:
            resp = await client.get(url, timeout=15)
            if resp.status_code != 200:
                continue
            text = resp.text
            # Sitewide sale banner → store as an auto-applied vendor discount so
            # every listing shows the effective price (Black-Friday capture).
            sale = detect_sitewide_sale(text)
            if sale:
                pct, ctx = sale
                upsert_discount_code(
                    vendor_key=vendor_key, code="SITEWIDE SALE",
                    discount_type="pct", discount_value=pct, source_url=url,
                    source_context=f"Auto sitewide sale: {ctx}", is_verified=0,
                    db_path=db_path,
                )
                total += 1
                logger.info(f"  [{vendor_key}] 🔥 SITEWIDE SALE {pct}% off")
            # Holiday / seasonal event (Black Friday, July 4th…). If it names a
            # percent we store it as a real sitewide discount; if not, an
            # informational flag so the admin/badge knows a sale is running.
            holiday = detect_holiday_promo(text)
            if holiday:
                hpct, ev, hctx = holiday
                upsert_discount_code(
                    vendor_key=vendor_key,
                    code="HOLIDAY SALE" if hpct is None else "SITEWIDE SALE",
                    discount_type="pct" if hpct else "info",
                    discount_value=hpct or 0, source_url=url,
                    source_context=f"{ev.title()} sale: {hctx}", is_verified=0,
                    db_path=db_path,
                )
                total += 1
                logger.info(f"  [{vendor_key}] 🎉 {ev.title()} sale "
                            f"({str(hpct)+'%' if hpct else 'see banner'})")
            # BOGO / multi-buy — informational (effective price depends on cart).
            bogo = detect_bogo(text)
            if bogo:
                upsert_discount_code(
                    vendor_key=vendor_key, code="BOGO",
                    discount_type="info", discount_value=0, source_url=url,
                    source_context=f"Buy-one-get-one / multi-buy: {bogo}",
                    is_verified=0, db_path=db_path,
                )
                total += 1
                logger.info(f"  [{vendor_key}] 🛒 BOGO / multi-buy offer")
            codes = extract_codes_from_text(text)
            for c in codes:
                upsert_discount_code(
                    vendor_key=vendor_key,
                    code=c["code"],
                    discount_type=c["discount_type"],
                    discount_value=c["discount_value"] or 0,
                    source_url=url,
                    source_context=c["context"],
                    is_verified=0,
                    db_path=db_path,
                )
                total += 1
                logger.info(f"  [{vendor_key}] Found code: {c['code']} "
                            f"({c['discount_type']} {c['discount_value']})")
        except Exception as e:
            logger.debug(f"  [{vendor_key}] Error scanning {url}: {e}")
    return total


def seed_known_codes(db_path=DB_PATH):
    """Insert the hardcoded known codes into the DB."""
    for vendor_key, code, dtype, value, min_order, source, verified in KNOWN_CODES:
        upsert_discount_code(
            vendor_key=vendor_key,
            code=code,
            discount_type=dtype,
            discount_value=value,
            min_order=min_order,
            source_context=source,
            is_verified=verified,
            db_path=db_path,
        )
    print(f"Seeded {len(KNOWN_CODES)} known discount codes.")


async def scan_all(db_path=DB_PATH) -> dict:
    """Scan all vendors for promo/sale codes concurrently (different domains, so
    parallel is polite). Returns summary {vendor_key: count}."""
    summary = {}
    headers = {"User-Agent": UA}
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        async def one(vk, urls):
            async with sem:
                try:
                    summary[vk] = await scan_vendor(vk, urls, client, db_path)
                except Exception as e:
                    logger.debug(f"[{vk}] discount scan error: {e}")
                    summary[vk] = 0
        await asyncio.gather(*(one(vk, urls) for vk, urls in VENDOR_PROMO_PAGES.items()))
    return summary


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Scan vendor sites for discount codes")
    parser.add_argument("--seed-only", action="store_true",
                        help="Only seed known codes, skip live scan")
    args = parser.parse_args()

    init_discount_tables(DB_PATH)
    print("Seeding known codes...")
    seed_known_codes(DB_PATH)

    if not args.seed_only:
        print("\nScanning vendor sites for promo codes...")
        summary = asyncio.run(scan_all(DB_PATH))
        print("\n=== Scan complete ===")
        total = sum(summary.values())
        print(f"Total codes found/updated: {total}")
        for vk, cnt in sorted(summary.items()):
            if cnt:
                print(f"  {vk}: {cnt}")
