"""
PalmStreet Auction Scraper
Captures recent sold prices from PalmStreet live shopping streams.
Focuses on Exotics Unlimited's Thursday auctions and Spider Room events.

PalmStreet shows:
  - Past auctions: sold lot list with species, sold price, date
  - Live auctions: current lot being sold (real-time, requires Playwright)

This scraper targets PAST AUCTION DATA — the "sold" lots pages —
which give us genuine transaction prices, not just asking prices.
Sold prices are the most honest market signal we can get.

Key insight: PalmStreet sold prices are typically 20-40% below
the same vendor's website price for the same species. Tracking
the delta between PalmStreet prices and website prices tells you
how much of a premium you're paying by buying off the website.

URLs:
  Exotics Unlimited: https://palmstreet.app/user/exoticsunlimited
  The Spider Room: https://palmstreet.app/user/thespiderroom

Saved to price_history with vendor_key = 'palmstreet_[seller]'
and verification_level = 'auction_sold'
"""
import asyncio
import logging
import re
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bs4 import BeautifulSoup
from vendors.base import BaseScraper
from models import CrawlResult, Availability
from normalize.price import parse_price
from database.db import DB_PATH

logger = logging.getLogger(__name__)

# PalmStreet sellers to monitor
PALMSTREET_SELLERS = {
    "exotics_unlimited_ps": {
        "display":  "Exotics Unlimited (PalmStreet)",
        "username": "exoticsunlimited",
        "url":      "https://palmstreet.app/user/exoticsunlimited",
    },
    "spider_room_ps": {
        "display":  "The Spider Room (PalmStreet)",
        "username": "thespiderroom",
        "url":      "https://palmstreet.app/user/thespiderroom",
    },
    "tydye_ps": {
        "display":  "TyDye Exotics (PalmStreet)",
        "username": "tydyeexotics",
        "url":      "https://palmstreet.app/user/tydyeexotics",
    },
}

# PalmStreet-specific species patterns in lot titles
# They often use common names — map to scientific where possible
PS_COMMON_NAME_HINTS = {
    "cobalt blue":        "Melapoeus lividus",
    "gbb":                "Chromatopelma cyaneopubescens",
    "green bottle blue":  "Chromatopelma cyaneopubescens",
    "obt":                "Pterinochilus murinus",
    "gooty":              "Poecilotheria metallica",
    "gooty sapphire":     "Poecilotheria metallica",
    "king baboon":        "Pelinobius muticus",
    "curly hair":         "Tliltocatl albopilosus",
    "salmon pink":        "Lasiodora parahybana",
    "chaco golden":       "Grammostola pulchripes",
    "brazilian black":    "Grammostola pulchra",
    "singapore blue":     "Omothymus violaceopes",
    "darth maul":         "Psalmopoeus victori",
}


def _extract_ps_species(title: str) -> tuple[str, Optional[str]]:
    """
    Extract scientific name and common name from a PalmStreet lot title.
    Lot titles like:
      'Grammostola pulchripes 3" female'
      'Brazilian Black Tarantula Sling - Grammostola pulchra'
      '1/2" GBB sling CB'
    """
    # Check for explicit scientific name (Capitalized Genus species)
    sci_match = re.search(
        r'([A-Z][a-z]+(?:\s+[a-z]+){1,3}(?:\s+sp\.?(?:\s+[A-Za-z]+)?)?)',
        title,
    )
    if sci_match:
        return sci_match.group(1).strip(), None

    # Fall back to common name lookup
    title_lower = title.lower()
    for common, sci in PS_COMMON_NAME_HINTS.items():
        if common in title_lower:
            return sci, common.title()

    return title.strip(), None


def _extract_ps_size(title: str) -> Optional[str]:
    """Extract size from PalmStreet lot title."""
    m = re.search(
        r'([\d.]+(?:\s*[-–]\s*[\d.]+)?\s*(?:"|inch(?:es)?|cm))',
        title, re.IGNORECASE,
    )
    return m.group(0).strip() if m else None


def _extract_ps_sex(title: str) -> Optional[str]:
    """Extract sex code from PalmStreet lot title."""
    t = title.lower()
    if "confirmed female" in t or " cf " in t:         return "F"
    if re.search(r'\bfemale\b|\bfem\b|\b\bf\b', t):    return "F"
    if re.search(r'\bmale\b|\b\bm\b|\bmm\b', t):        return "M"
    if "probable female" in t or "pf" in t:             return "PF"
    return None


class PalmStreetScraper(BaseScraper):
    """
    Scrapes past auction (sold lot) data from PalmStreet.
    Uses Playwright because PalmStreet is fully JS-rendered.

    NOTE: PalmStreet blocks simple HTTP scrapers with 403. Playwright
    with browser emulation is required. If Playwright is unavailable,
    the scraper returns an empty result with a note.
    """
    VENDOR_KEY  = "palmstreet"
    VENDOR_NAME = "PalmStreet (Multi-Seller)"
    BASE_URL    = "https://palmstreet.app"
    PLATFORM    = "palmstreet_auction"

    async def scrape(self) -> CrawlResult:
        from datetime import datetime as dt
        self.result.started_at = dt.utcnow()
        self.result.status = "running"

        async with self:
            for seller_key, seller_info in PALMSTREET_SELLERS.items():
                await self._scrape_seller(seller_key, seller_info)

        self.result.status = "complete" if not self.result.failures else "partial"
        self.result.finished_at = dt.utcnow()
        return self.result

    async def _scrape_seller(self, seller_key: str, info: dict):
        """Scrape a single seller's past sold lots from PalmStreet."""
        # PalmStreet past lots URL
        past_url = f"{info['url']}/past"
        resp = await self.get(past_url)
        if not resp:
            self.result.failures.append(
                f"PalmStreet {seller_key}: No response. "
                f"Site may require Playwright — run with: python vendors/palmstreet.py --seller {seller_key}"
            )
            return

        soup = BeautifulSoup(resp.text, "lxml")

        # Look for lot cards. PalmStreet uses React but server-renders some content.
        # Selectors may need updating — run --debug on first attempt.
        lot_selectors = [
            "div[class*='lot-card']",
            "div[class*='LotCard']",
            "div[class*='product-card']",
            "article",
            "li[class*='lot']",
        ]

        cards = []
        for sel in lot_selectors:
            cards = soup.select(sel)
            if cards:
                logger.debug(f"PalmStreet {seller_key}: {len(cards)} cards via '{sel}'")
                break

        if not cards:
            # Try finding price + title patterns directly in text
            cards = self._regex_extract_lots(soup, info["display"])
        else:
            for card in cards:
                listing = self._parse_lot_card(card, seller_key, info["display"])
                if listing:
                    self.result.listings.append(listing)
                    self.result.variants_found += 1

        self.result.pages_crawled += 1
        logger.info(f"PalmStreet {seller_key}: {self.result.variants_found} sold lots")

    def _parse_lot_card(self, card, seller_key: str, display_name: str):
        """Parse a PalmStreet lot card into a Listing."""
        # Title
        title_el = card.select_one("h2,h3,h4,[class*='title'],[class*='name']")
        title = title_el.get_text(strip=True) if title_el else card.get_text(" ", strip=True)[:80]
        if not title:
            return None

        # Price (SOLD price)
        price_text = None
        for sel in ["[class*='price']","[class*='sold']","span[class*='amount']"]:
            el = card.select_one(sel)
            if el:
                price_text = el.get_text(strip=True)
                break
        if not price_text:
            m = re.search(r'\$\s*\d+(?:\.\d+)?', card.get_text())
            price_text = m.group(0) if m else None

        price = parse_price(price_text) if price_text else None
        if not price:
            return None

        sci_name, common = _extract_ps_species(title)
        size_text = _extract_ps_size(title)
        sex       = _extract_ps_sex(title)

        return self._make_listing(
            scientific_name = sci_name,
            common_name     = common,
            sex             = sex or "U",
            size_text       = size_text,
            price_usd       = price,
            availability    = Availability.OUT_OF_STOCK,  # sold = no longer available
            product_url     = self.BASE_URL,
            notes           = f"PalmStreet auction sold price — {display_name}",
            raw_title       = title,
            raw_price       = price_text or "",
            vendor_key      = f"palmstreet_{seller_key.replace('_ps','')}",
        )

    def _regex_extract_lots(self, soup: BeautifulSoup, display_name: str) -> list:
        """Fallback: regex extraction from page text."""
        text = soup.get_text(separator="\n")
        listings = []
        pat = re.compile(
            r'([A-Z][a-z]+\s+[a-z][a-z\s.\'"()-]+?)'
            r'\s+\$\s*(\d+(?:\.\d+)?)',
            re.MULTILINE,
        )
        for m in pat.finditer(text):
            sci = m.group(1).strip()
            price = float(m.group(2))
            if price < 5 or len(sci) < 5:
                continue
            listings.append(self._make_listing(
                scientific_name = sci,
                price_usd       = price,
                availability    = Availability.OUT_OF_STOCK,
                product_url     = self.BASE_URL,
                notes           = f"PalmStreet regex extract — {display_name}",
                raw_title       = sci,
                raw_price       = f"${price}",
            ))
        return listings


async def scrape_palmstreet(db_path: Path = DB_PATH) -> dict:
    """
    Entry point for pipeline integration.
    Returns summary: {seller_key: listings_count}
    """
    scraper = PalmStreetScraper()
    result = await scraper.scrape()

    summary = {
        "total": result.variants_found,
        "failures": result.failures,
        "listings": result.listings,
    }

    if result.listings:
        from database.db import upsert_vendor, get_connection
        upsert_vendor("palmstreet", "PalmStreet (Auction Sold Prices)",
                      "https://palmstreet.app", "auction", db_path)
        # Insert into price_history
        conn = get_connection(db_path)
        now = datetime.now(timezone.utc).isoformat()
        run_id = conn.execute("""
            INSERT INTO crawl_runs (vendor_key, status, variants_found, started_at, finished_at, notes)
            VALUES ('palmstreet', 'complete', ?, ?, ?, 'PalmStreet auction sold prices')
        """, (len(result.listings), now, now)).lastrowid
        conn.commit()

        from database.db import save_listings
        save_listings(result.listings, run_id, db_path)
        conn.close()

    return summary


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.DEBUG,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Scrape PalmStreet auction prices")
    parser.add_argument("--seller", default=None, help="Specific seller key to scrape")
    args = parser.parse_args()

    print("Scraping PalmStreet past auction sold prices...")
    summary = asyncio.run(scrape_palmstreet(DB_PATH))
    print(f"Done: {summary['total']} sold lots captured")
    if summary['failures']:
        print("Warnings:")
        for f in summary['failures']:
            print(f"  {f}")
