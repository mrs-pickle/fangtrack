"""
TarantulaList scraper.
URL: https://tarantulalist.com
Platform: Aggregator

TarantulaList aggregates listings from multiple vendors.
We use it to discover vendor URLs and supplement our direct crawls.
Listings here are marked verification_level=aggregator.
"""
import logging
import re
from bs4 import BeautifulSoup
from models import CrawlResult, Availability, VerificationLevel
from vendors.base import BaseScraper
from normalize.sex import normalize_sex
from normalize.price import parse_price

logger = logging.getLogger(__name__)


class TarantulaListScraper(BaseScraper):
    VENDOR_KEY = "tarantulalist"
    VENDOR_NAME = "TarantulaList"
    BASE_URL = "https://tarantulalist.com"
    PLATFORM = "aggregator"

    async def scrape(self) -> CrawlResult:
        from datetime import datetime
        self.result.started_at = datetime.utcnow()
        self.result.status = "running"
        self.result.notes = "Aggregator -- listings link to external vendors"

        async with self:
            # TarantulaList main listing page
            resp = await self.get(self.BASE_URL)
            if not resp:
                self.result.status = "failed"
                self.result.finished_at = datetime.utcnow()
                return self.result

            soup = BeautifulSoup(resp.text, "lxml")
            self.result.pages_crawled += 1

            # Parse main listing table/grid
            listings = self._parse_listings(soup)
            self.result.listings.extend(listings)
            self.result.variants_found += len(listings)

            # Follow pagination. Dedup against everything already collected:
            # the site serves the same grid for any unknown ?page=N, so an
            # "empty page" stop condition never fires — we stop as soon as a
            # page adds nothing new (plus a hard cap as a backstop).
            seen = {(l.scientific_name, l.price_usd, l.product_url)
                    for l in self.result.listings}
            page = 2
            MAX_PAGES = 50
            while page <= MAX_PAGES:
                page_url = f"{self.BASE_URL}/?page={page}"
                resp = await self.get(page_url)
                if not resp:
                    break
                soup = BeautifulSoup(resp.text, "lxml")
                fresh = []
                for l in self._parse_listings(soup):
                    key = (l.scientific_name, l.price_usd, l.product_url)
                    if key not in seen:
                        seen.add(key)
                        fresh.append(l)
                if not fresh:
                    break
                self.result.listings.extend(fresh)
                self.result.variants_found += len(fresh)
                self.result.pages_crawled += 1
                page += 1

        self.result.products_found = len(self.result.listings)
        self.result.status = "complete" if not self.result.failures else "partial"
        self.result.finished_at = datetime.utcnow()
        return self.result

    def _parse_listings(self, soup: BeautifulSoup) -> list:
        """
        Parse listing rows from TarantulaList's aggregator table.

        Each row's cells are, in order:
          [0] "Scientific name \u00b7 size"   e.g. "Aphonopelma bicoloratum \u00b7 1/2"
          [1] "$price"                    e.g. "$75.00"
          [2] vendor display name         e.g. "ArachnoEden"
          [3] sex / marker (often blank)
          [4] "Open" link (external vendor link)
        The species is in cell[0], NOT the "Open" button \u2014 the previous
        selector-based parse grabbed the button and recorded every row as
        "Open".
        """
        from models import VerificationLevel
        listings = []
        rows = soup.select("table tbody tr") or soup.select("table tr")

        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue

            name_cell = cells[0].get_text(" ", strip=True)
            if not name_cell:
                continue

            # Split "Genus species \u00b7 size" on a bullet/middot/pipe separator.
            parts = re.split(r"\s*[\u00b7\u2022|\u00b7\u2022\ufffd]\s*", name_cell, maxsplit=1)
            scientific = parts[0].strip()
            size_text = parts[1].strip() if len(parts) > 1 else None

            # Must look like a real species (Genus species), not a UI label.
            if not re.match(r"^[A-Z][a-z]+ ", scientific):
                continue

            price = parse_price(cells[1].get_text(strip=True))
            if not price:
                continue

            vendor_name = cells[2].get_text(" ", strip=True) or None

            # Sex sometimes appears in a later cell or in the size text.
            sex_blob = " ".join(c.get_text(" ", strip=True) for c in cells[3:])
            sex_code, _ = normalize_sex(sex_blob)
            if sex_code == "Unknown" and size_text:
                sex_code, _ = normalize_sex(size_text)

            listing = self._make_listing(
                scientific_name=scientific,
                sex=sex_code,
                size_text=size_text,
                price_usd=price,
                product_url=self.BASE_URL,
                availability=Availability.UNKNOWN,
                notes=f"via TarantulaList \u2192 {vendor_name}" if vendor_name else "via TarantulaList",
                raw_title=name_cell,
                raw_price=cells[1].get_text(strip=True),
            )
            listing.verification_level = VerificationLevel.AGGREGATOR
            listings.append(listing)

        return listings
