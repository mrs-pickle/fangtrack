"""
WooStoreScraper — base for WooCommerce vendors via the Store API (bulk).

WooCommerce exposes a public, unauthenticated Store API that returns full
product data — name, price, stock, permalink — 100 per request:

    GET /wp-json/wc/store/v1/products?per_page=100&page=N

That replaces crawling one HTML page per product (hundreds of requests) with a
couple of JSON calls. Prices come in the currency's minor units (cents), so a
$90.00 item is "9000" with currency_minor_unit=2.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from models import CrawlResult, Availability
from vendors.base import BaseScraper
from normalize.livestock import is_livestock
from normalize.sex import normalize_sex

logger = logging.getLogger(__name__)


class WooStoreScraper(BaseScraper):
    # WooCommerce Store API is a public read JSON API; a 1s cadence is polite and cuts the
    # big multi-page vendors (e.g. underground_reptiles' 65 pages) roughly in half.
    REQUEST_DELAY = 1.0
    PLATFORM = "woocommerce"
    PER_PAGE = 100
    MAX_PAGES = 40
    STORE_API = "/wp-json/wc/store/v1/products"

    async def scrape(self) -> CrawlResult:
        self.result.started_at = datetime.utcnow()
        self.result.status = "running"

        async with self:
            page = 1
            total_pages = None
            while page <= self.MAX_PAGES:
                url = f"{self.BASE_URL}{self.STORE_API}?per_page={self.PER_PAGE}&page={page}"
                resp = await self.get(url)
                if not resp:
                    break
                if total_pages is None:
                    try:
                        total_pages = int(resp.headers.get("x-wp-totalpages") or 1)
                    except (TypeError, ValueError):
                        total_pages = 1
                try:
                    products = resp.json()
                except Exception:
                    self.result.failures.append(f"Non-JSON Store API response p{page}")
                    break
                if not products:
                    break
                self.result.pages_crawled += 1
                for p in products:
                    listing = self._parse_product(p)
                    if listing:
                        self.result.listings.append(listing)
                logger.info(f"{self.VENDOR_NAME}: page {page}/{total_pages} — "
                            f"{len(products)} products")
                if page >= total_pages:
                    break
                page += 1

        self.result.products_found = len(self.result.listings)
        self.result.variants_found = len(self.result.listings)
        self.result.status = "complete" if self.result.listings else "partial"
        self.result.finished_at = datetime.utcnow()
        logger.info(f"{self.VENDOR_NAME}: {len(self.result.listings)} listings "
                    f"in {self.result.pages_crawled} API pages")
        return self.result

    def _parse_product(self, p: dict) -> Optional[object]:
        name = (p.get("name") or "").strip()
        # WooCommerce titles carry HTML: italic tags plus entity-encoded punctuation
        # (&#8211; en-dash, &#8221; curly quote, &#8243; inch mark). Decode them so
        # the name displays cleanly AND the size in the title (e.g. "1 – 3\"")
        # is parseable.
        import re, html
        name = re.sub(r"</?i>", "", name)
        name = html.unescape(name).strip()
        if not name or not is_livestock(name):
            return None

        prices = p.get("prices") or {}
        minor = prices.get("currency_minor_unit", 2)
        div = 10 ** minor if minor else 1

        def to_usd(v):
            try:
                return round(int(v) / div, 2)
            except (TypeError, ValueError):
                return None

        price = to_usd(prices.get("price"))
        if not price or price <= 0:
            return None
        regular = to_usd(prices.get("regular_price")) if p.get("on_sale") else None
        if regular and regular <= price:
            regular = None

        avail = Availability.IN_STOCK if p.get("is_in_stock") else Availability.OUT_OF_STOCK
        url = p.get("permalink") or self.BASE_URL
        sex_code, _ = normalize_sex(name)

        # Size may be in the title (handled by _make_listing) or the description
        # body ("Approximately 3 – 4 Inches"). Pass a body-derived size so the
        # scraper picks it up when the title has none.
        from normalize.size import extract_size_from_description
        size_text = extract_size_from_description(
            (p.get("description") or "") + " " + (p.get("short_description") or ""))

        return self._make_listing(
            scientific_name=name,
            sex=sex_code,
            size_text=size_text,
            price_usd=price,
            regular_price_usd=regular,
            availability=avail,
            product_url=url,
            raw_title=name,
            raw_price=prices.get("price_html") or str(price),
            description=(p.get("description") or "") + " " + (p.get("short_description") or ""),
        )
