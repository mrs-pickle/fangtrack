"""
Spider Room (thespiderroom.com) — custom text scraper
Inventory at: /daily-livestock-update
Format: "8x Acanthoscurria geniculata - Giant White Knee 3/4" - $40"
"""
import re
import logging
import httpx
from vendors.base import CrawlResult

logger = logging.getLogger(__name__)

VENDOR_KEY  = "spider_room"
VENDOR_NAME = "Spider Room"
BASE_URL    = "https://thespiderroom.com"
LIST_URL    = f"{BASE_URL}/daily-livestock-update"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SUPPLY_SKIP = {"enclosure","terrarium","substrate","soil","feeder","cricket","roach",
               "gift card","book","shirt","kit","supply","water dish","decor"}

def _is_animal(scientific_name: str) -> bool:
    skip_genera = {"gift","certificate","roach","cricket","mealworm","feeder"}
    return scientific_name.split()[0].lower() not in skip_genera

def _parse_line(line: str) -> dict | None:
    """Parse one livestock line. Returns dict or None if not parseable."""
    line = line.strip()
    if not re.match(r"^\d+x ", line):
        return None

    # Extract price (last " - $NNN" on the line)
    price_m = re.search(r"\s+-\s+\$(\d+(?:\.\d+)?)$", line)
    if not price_m:
        return None
    price = float(price_m.group(1))
    if price <= 0 or price > 4999:
        return None

    body = line[:price_m.start()].strip()
    body = body.replace("LOCAL PICKUP ONLY", "").replace("  ", " ").strip()

    qty_m = re.match(r"^(\d+)x\s+(.+)$", body)
    if not qty_m:
        return None
    qty = int(qty_m.group(1))
    rest = qty_m.group(2)

    dash = rest.find(" - ")
    if dash == -1:
        scientific = rest.strip()
        description = ""
    else:
        scientific = rest[:dash].strip()
        description = rest[dash + 3:].strip()

    if not _is_animal(scientific):
        return None

    # Size: numeric patterns like 3/4", 1", 2"-3", 4"+, 3i-5i
    size_m = re.search(
        r'(\d+(?:[./]\d+)?(?:-\d+(?:[./]\d+)?)?(?:i|"|\'|\+)?(?:-\d+(?:[./]\d+)?(?:i|"|\'))?)',
        description,
    )
    size_text = size_m.group(1) if size_m else None

    du = description.upper()
    if "ADULT FEMALE" in du or ("FEMALE" in du and "MALE" not in du.replace("FEMALE", "")):
        sex = "F"
    elif "ADULT MALE" in du or "MATURE MALE" in du or \
         ("MALE" in du and "FEMALE" not in du):
        sex = "M"
    elif "UNSEXED" in du:
        sex = "U"
    else:
        sex = None

    src_m = re.search(r"\(([A-Z]{2,3})\)", description)
    source = src_m.group(1) if src_m and src_m.group(1) in ("WC","CB","LTC","FH") else None

    common = description
    if size_m:
        common = description[:size_m.start()].strip().rstrip("-").strip()
    for token in ["ADULT FEMALE","SUB AD-ADULT FEMALE","SUB ADULT FEMALE","ADULT MALE",
                  "MATURE MALE","MATURE FEMALE","FEMALE","MALE","UNSEXED","JUVIE",
                  "JUVIE-ADULT","SUB AD-ADULT","(WC)","(CB)","(LTC)"]:
        common = common.replace(token, "").strip().rstrip("-").strip()
    common = common or None

    return {
        "vendor_key": VENDOR_KEY,
        "vendor_name": VENDOR_NAME,
        "scientific_name": scientific,
        "common_name": common,
        "size_text": size_text,
        "sex": sex,
        "source_type": source,
        "price_usd": price,
        "quantity": qty,
        "product_url": LIST_URL,
        "availability": "in_stock",
    }


async def scrape() -> list[dict]:
    results, failures = [], 0
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as c:
            r = await c.get(LIST_URL)
            r.raise_for_status()
            text = r.text

        # Pull text content: find the DAILY LIVESTOCK UPDATE section
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(text, "html.parser")
        content_text = soup.get_text(separator="\n")

        section_start = content_text.find("DAILY LIVESTOCK UPDATE")
        if section_start == -1:
            section_start = content_text.find("Tarantulas")
        content_section = content_text[section_start:] if section_start != -1 else content_text

        parsed = 0
        for line in content_section.split("\n"):
            r = _parse_line(line)
            if r:
                results.append(r)
                parsed += 1

        logger.info(f"[{VENDOR_KEY}] {parsed} listings parsed from text")
    except Exception as e:
        logger.error(f"[{VENDOR_KEY}] scrape error: {e}")
        failures += 1

    return results


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    results = asyncio.run(scrape())
    for r in results[:5]:
        print(r)
    print(f"Total: {len(results)}")




# ── Class adapter for REGISTRY compatibility ─────────────────────────────────
from models import CrawlResult as _CR, Listing as _L
from vendors.base import BaseScraper
from datetime import datetime as _dt
import asyncio as _asyncio

class SpiderRoomScraper(BaseScraper):
    """Thin class wrapper that calls the module-level scrape() function."""
    VENDOR_KEY  = VENDOR_KEY
    VENDOR_NAME = VENDOR_NAME
    BASE_URL    = BASE_URL
    PLATFORM    = "custom"

    async def scrape(self) -> _CR:
        from datetime import datetime
        self.result.started_at = datetime.utcnow()
        self.result.status = "running"
        try:
            raw_listings = await globals()["scrape"]()
            for d in raw_listings:
                l = _L(
                    vendor=d.get("vendor_name", VENDOR_NAME),
                    vendor_key=d.get("vendor_key", VENDOR_KEY),
                    scientific_name=d.get("scientific_name", "Unknown"),
                    common_name=d.get("common_name"),
                    sex=d.get("sex") or "Unknown",
                    size_text=d.get("size_text"),
                    price_usd=float(d.get("price_usd", 0)),
                    quantity=d.get("quantity"),
                    availability=d.get("availability", "unknown"),
                    product_url=d.get("product_url", ""),
                )
                self.result.listings.append(l)
            self.result.products_found = len(self.result.listings)
            self.result.status = "complete"
        except Exception as e:
            self.result.failures.append(str(e))
            self.result.status = "failed"
        self.result.finished_at = datetime.utcnow()
        return self.result


# main.py registry imports this name; keep both aliases in sync.
TheSpiderRoomScraper = SpiderRoomScraper
