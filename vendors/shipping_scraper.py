"""
Shipping Rate Module
Stores flat shipping rates and free-shipping thresholds for all vendors.
Calculates estimated landed cost per animal given a destination zip.

Usage:
  python vendors/shipping_scraper.py --seed          # load known rates
  python vendors/shipping_scraper.py --scan          # scrape vendor pages
  python vendors/shipping_scraper.py --zip 72712     # show rates to that zip

Landed cost formula:
  If order_total >= free_threshold: shipping = $0
  Else: shipping = flat_rate + heat_cold_pack (if seasonal)
  Per-animal shipping share = shipping / qty_in_order

Most live animal vendors use flat overnight rates regardless of destination.
Zip code affects: seasonal weather holds, and edge cases for zone-based
vendors (rare). Future: integrate FedEx/UPS API for true zone pricing.
"""
import asyncio
import sys
import os
import re
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from database.db import upsert_shipping, get_all_shipping, init_discount_tables, DB_PATH

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# ---------------------------------------------------------------------------
# Seeded shipping data (researched from vendor sites, forum posts, policies)
# Fields: vendor_key, vendor_name, origin_zip, carrier, service,
#         flat_rate, free_threshold, min_order, heat_cold_pack,
#         live_guarantee, notes, source_url
# ---------------------------------------------------------------------------
KNOWN_SHIPPING = [
    # vendor_key, name, origin_zip, carrier, service, flat, free_at, min_order, pack, lag, notes, source
    ("fear_not",           "Fear Not Tarantulas",     "23451", "FedEx",    "overnight", 29.00,  300.00, 50.00,  None, 1, "Ships Mon/Tue. $29 flat, free over $300. Pack included.",  "fearnottarantulas.com/pages/shipping-info"),
    ("jamies",             "Jamie's Tarantulas",      None,    "FedEx",    "overnight", 39.00,  None,   None,   None, 1, "Flat rate overnight. Contact for seasonal details.",         "jamiesontheweb.com"),
    ("spider_room",        "The Spider Room",         "91730", "FedEx",    "overnight", 40.00,  None,   None,   None, 1, "Rancho Cucamonga CA. Flat overnight.",                       "thespiderroom.com"),
    ("exotics_unlimited",  "Exotics Unlimited USA",   "27284", "FedEx",    "overnight", 45.00,  500.00, None,   None, 1, "Kernersville NC. Free ship over $500.",                      "exoticsunlimitedusa.com"),
    ("tydye",              "TyDye Exotics",           None,    "FedEx",    "overnight", 45.00,  500.00, None,   None, 1, "Free live animal ship on orders over $500 (retail).",        "tydyeexotic.com"),
    ("spidershoppe",       "Spider Shoppe",           None,    "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Flat overnight. Live arrival guarantee.",                    "spidershoppe.com"),
    ("plumbs_exotics",     "Plumb's Exotics",         None,    "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Flat overnight estimated.",                                  "plumbsexotics.com"),
    ("hardcore_arachnids", "Hardcore Arachnids",      None,    "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Flat overnight estimated.",                                  "hardcorearachnids.com"),
    ("marshall_arachnids", "Marshall Arachnids",      "37000", "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Tennessee. Flat overnight estimated.",                       "marshallarachnids.com"),
    ("buddha_bugs",        "Buddha Bugs Exotics",     None,    "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Flat overnight estimated.",                                  "buddhabugsexotics.com"),
    ("micro_wilderness",   "Micro Wilderness",        None,    "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Flat overnight estimated.",                                  "microwilderness.com"),
    ("fanghub",            "FangHub",                 None,    "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Flat overnight estimated.",                                  "fanghubtarantulas.com"),
    ("wonderland_exotics", "Wonderland Exotics",      None,    "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Flat overnight estimated.",                                  "wonderlandexoticsllc.com"),
    ("big_zs",             "Big Z's Exotic Pets",     None,    "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Flat overnight estimated.",                                  "bigzsexoticpets.com"),
    ("pnw_arachnids",      "Pacific Northwest Arachnids", "97000", "FedEx","overnight", 35.00,  None,   None,   None, 1, "Pacific NW. Flat overnight estimated.",                      "pnwarachnids.com"),
    ("ghostys",            "Ghosty's Tarantulas",     None,    "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Flat overnight estimated.",                                  "ghostystarantulas.com"),
    ("eight_deadly_sins",  "Eight Deadly Sins",       None,    "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Flat overnight estimated.",                                  "eightdeadlysins.net"),
    ("swifts_inverts",     "Swift's Inverts",         None,    "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Flat overnight estimated.",                                  "swiftsinverts.com"),
    ("fangztv",            "FangzTV",                 None,    "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Flat overnight estimated.",                                  "fangztv.com"),
    ("arachnoeden",        "ArachnoEden",             None,    "FedEx",    "overnight", 35.00,  None,   None,   None, 1, "Flat overnight estimated.",                                  "arachnoeden.org"),
    ("natures_exquisite_creatures", "Nature's Exquisite Creatures", None, "FedEx", "overnight", 35.00, None, None, None, 1, "Flat overnight estimated.", "naturesexquisitecreatures.com"),
    ("urban_tarantulas",   "Urban Tarantulas",        None,    "FedEx",    "overnight", 39.00,  None,   None,   None, 1, "Flat overnight estimated.",                                  "urbantarantulas.com"),
    ("juices_arthropods",  "Juice's Arthropods",      "94545", "FedEx",    "overnight", 39.00,  None,   None,   None, 1, "Hayward CA. Flat overnight estimated.",                      "juicesarthropods.com"),
    ("arachnid_rarities",  "Arachnid Rarities",       None,    "FedEx",    "overnight", 40.00,  None,   None,   None, 1, "Flat overnight estimated. Rare species specialist.",         "arachnidrarities.com"),
    ("tarantula_spiders",  "Tarantula Spiders",       None,    "FedEx",    "overnight", 60.00,  None,   None,   None, 1, "Higher shipping — typically bulk/specialty orders.",         "tarantulaspiders.com"),
    ("joshsfrogs",         "Josh's Frogs",            "49221", "FedEx",    "overnight", 39.99,  None,   None,   None, 1, "Michigan. Flat overnight. Scheduling required.",             "joshsfrogs.com"),
]

# ---------------------------------------------------------------------------
# Shipping page paths to scrape per vendor
# ---------------------------------------------------------------------------
SHIPPING_PAGES = {
    "fear_not":           "https://fearnottarantulas.com/pages/shipping-info",
    "exotics_unlimited":  "https://exoticsunlimitedusa.com/pages/shipping",
    "tydye":              "https://tydyeexotic.com/pages/shipping",
    "spider_room":        "https://thespiderroom.com/shipping",
    "spidershoppe":       "https://spidershoppe.com/pages/shipping",
    "joshsfrogs":         "https://www.joshsfrogs.com/pages/shipping.html",
    "jamies":             "https://jamiesontheweb.com/pages/shipping",
    "juices_arthropods":  "https://www.juicesarthropods.com/pages/shipping",
    "urban_tarantulas":   "https://www.urbantarantulas.com/pages/shipping-policy",
}

# Regex patterns for extracting shipping rates from text
FLAT_RATE_PAT = re.compile(
    r'(?:flat\s+(?:rate\s+)?)?shipping[:\s]+\$?\s*(\d+(?:\.\d+)?)',
    re.IGNORECASE,
)
FREE_THRESH_PAT = re.compile(
    r'free\s+(?:shipping|live\s+animal\s+shipping)\s+'
    r'(?:on\s+orders?\s+)?(?:over|above|exceeding)?\s*\$?\s*(\d+)',
    re.IGNORECASE,
)
DOLLAR_SHIP_PAT = re.compile(
    r'\$\s*(\d+(?:\.\d+)?)\s+(?:flat\s+)?(?:rate\s+)?shipping',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Zip code-to-zone estimation
# Very rough FedEx zone approximation for continental US overnight.
# Most vendors use flat rates so this is mainly for future expansion.
# ---------------------------------------------------------------------------
ORIGIN_SURCHARGES = {
    # Some vendors near coasts or major hubs have marginally different rates.
    # For now this is a stub — all vendors use flat rates.
}


def estimate_shipping(vendor_key: str, shipping_data: dict,
                      dest_zip: str, order_total: float = 0.0) -> dict:
    """
    Estimate shipping cost from vendor to dest_zip for a given order total.

    Returns dict with:
      shipping_cost:   estimated $ cost
      is_free:         True if order qualifies for free shipping
      method:          'flat_rate' | 'free' | 'estimated' | 'unknown'
      notes:           human-readable explanation
    """
    if not shipping_data:
        return {"shipping_cost": None, "is_free": False,
                "method": "unknown", "notes": "No shipping data on file"}

    flat  = shipping_data.get("flat_rate")
    free_at = shipping_data.get("free_threshold")
    min_ord = shipping_data.get("min_order", 0) or 0

    if order_total < min_ord:
        return {"shipping_cost": None, "is_free": False,
                "method": "unknown",
                "notes": f"Minimum order ${min_ord:.0f} not met"}

    if free_at and order_total >= free_at:
        return {"shipping_cost": 0.0, "is_free": True,
                "method": "free",
                "notes": f"Free shipping (order ≥ ${free_at:.0f})"}

    if flat:
        return {"shipping_cost": flat, "is_free": False,
                "method": "flat_rate",
                "notes": f"Flat overnight rate (FedEx/UPS)"}

    return {"shipping_cost": None, "is_free": False,
            "method": "unknown", "notes": "Rate structure unknown — check vendor site"}


def compute_landed_cost(price: float, vendor_key: str,
                        shipping_lookup: dict, dest_zip: str,
                        order_total: float = None) -> dict:
    """
    Compute total landed cost = price + share of shipping.

    order_total defaults to the single-animal price (worst case: ordering just 1).
    Returns dict with landed_cost, shipping_share, shipping_method.
    """
    if order_total is None:
        order_total = price

    shipping_data = shipping_lookup.get(vendor_key, {})
    ship_info = estimate_shipping(vendor_key, shipping_data, dest_zip, order_total)

    ship_cost = ship_info["shipping_cost"]
    if ship_cost is None:
        return {
            "landed_cost": None,
            "shipping_share": None,
            "shipping_method": ship_info["method"],
            "shipping_notes": ship_info["notes"],
        }

    return {
        "landed_cost": round(price + ship_cost, 2),
        "shipping_share": ship_cost,
        "shipping_method": ship_info["method"],
        "shipping_notes": ship_info["notes"],
    }


def seed_known_shipping(db_path=DB_PATH) -> None:
    """Insert all known shipping rates into the DB."""
    for row in KNOWN_SHIPPING:
        (vk, vname, ozip, carrier, service, flat, free_at,
         min_ord, pack, lag, notes, src) = row
        upsert_shipping(
            vendor_key=vk, vendor_name=vname, origin_zip=ozip,
            carrier=carrier, service=service,
            flat_rate=flat, free_threshold=free_at, min_order=min_ord,
            heat_cold_pack=pack, live_guarantee=lag,
            notes=notes, source_url=src, db_path=db_path,
        )
    print(f"Seeded shipping rates for {len(KNOWN_SHIPPING)} vendors.")


async def scrape_shipping_pages(db_path=DB_PATH) -> None:
    """Scan vendor shipping pages to find/update rates."""
    headers = {"User-Agent": UA}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        for vk, url in SHIPPING_PAGES.items():
            try:
                resp = await client.get(url, timeout=15)
                if resp.status_code != 200:
                    continue
                text = resp.text

                flat = None
                free_at = None

                for pat in [FLAT_RATE_PAT, DOLLAR_SHIP_PAT]:
                    m = pat.search(text)
                    if m:
                        flat = float(m.group(1))
                        break

                m = FREE_THRESH_PAT.search(text)
                if m:
                    free_at = float(m.group(1))

                if flat or free_at:
                    upsert_shipping(
                        vendor_key=vk, vendor_name=vk,
                        flat_rate=flat, free_threshold=free_at,
                        source_url=url, db_path=db_path,
                    )
                    print(f"  [{vk}] flat=${flat} free_at=${free_at}")
                else:
                    print(f"  [{vk}] No rates parsed from {url}")

                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"  [{vk}] Error: {e}")


def print_rate_table(dest_zip: str, db_path=DB_PATH) -> None:
    """Print a summary of shipping rates to a given zip code."""
    all_ship = get_all_shipping(db_path)
    print(f"\nShipping estimates to zip: {dest_zip}")
    print(f"{'Vendor':<30} {'Flat Rate':>10} {'Free At':>10} {'Min Order':>10}  {'Notes'}")
    print("-" * 90)
    for vk, s in sorted(all_ship.items(), key=lambda x: x[1].get("flat_rate") or 999):
        flat    = f"${s['flat_rate']:.0f}" if s.get("flat_rate") else "?"
        free_at = f"${s['free_threshold']:.0f}" if s.get("free_threshold") else "—"
        min_ord = f"${s['min_order']:.0f}" if s.get("min_order") else "—"
        name    = s.get("vendor_name") or vk
        notes   = (s.get("notes") or "")[:50]
        print(f"{name:<30} {flat:>10} {free_at:>10} {min_ord:>10}  {notes}")


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Shipping rate tool")
    parser.add_argument("--seed",   action="store_true", help="Seed known rates into DB")
    parser.add_argument("--scan",   action="store_true", help="Scrape shipping pages for updates")
    parser.add_argument("--zip",    default="72712",     help="Destination zip to show rates for")
    args = parser.parse_args()

    init_discount_tables(DB_PATH)

    if args.seed or not args.scan:
        seed_known_shipping(DB_PATH)

    if args.scan:
        print("\nScraping vendor shipping pages...")
        asyncio.run(scrape_shipping_pages(DB_PATH))

    print_rate_table(args.zip, DB_PATH)
