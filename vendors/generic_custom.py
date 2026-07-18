"""
GenericCustomScraper — a configurable HTML catalog scraper on top of BaseScraper.

Built for storefronts that are NOT Shopify (no /products.json), where the
catalog is rendered as server-side HTML product cards inside category pages:
BigCommerce, WooCommerce, PinnacleCart, etc.

A concrete vendor subclasses this and sets, at minimum:
    BASE_URL
    CATEGORY_PATHS   -> list of catalog/category paths to walk, e.g. ["/terrestrial/"]

and, if the theme differs from the defaults, overrides the CSS selectors:
    PRODUCT_SELECTOR -> selector matching one product card
    TITLE_SELECTOR   -> selector (within a card) for the title/link text
    LINK_SELECTOR    -> selector (within a card) for the <a href> product link
    PRICE_SELECTOR   -> selector (within a card) for the price text

Pagination is handled by appending PAGE_QUERY (?page=N by default) and stopping
once a page yields no *new* product URLs (dedup is global per vendor), so a
theme that repeats the last page at the end of the range terminates cleanly.

Etiquette: all requests go through BaseScraper.get(), which enforces the
2s minimum delay and rotating retry/backoff — do not bypass it.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from models import CrawlResult, Availability
from vendors.base import BaseScraper
from normalize.sex import normalize_sex
from normalize.price import parse_price

logger = logging.getLogger(__name__)


# Titles that are supplies / feeders / merch, not live tarantulas.
SUPPLY_KEYWORDS = [
    "enclosure", "terrarium", "vivarium", "cage", "tank", " kit",
    "substrate", "soil", "coco", "peat", "sphagnum", "moss", "vermiculite",
    "feeder", "cricket", "roach", "dubia", "mealworm", "waxworm", "superworm",
    "book", "shirt", "hoodie", "apparel", "merch", "hat", "sticker",
    "water dish", "hide", "cork bark", "decoration", "humidity",
    "thermometer", "hygrometer", "heat mat", "heat lamp",
    "shipping", "deli cup", "container", "springtail", "isopod",
    "gift card", "gift certificate", "mystery box",
]


def _is_supply(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in SUPPLY_KEYWORDS)


class GenericCustomScraper(BaseScraper):
    PLATFORM = "custom"

    # --- Required per-vendor config ---
    CATEGORY_PATHS: list[str] = []

    # --- Selectors (BigCommerce ClassicNext defaults) ---
    PRODUCT_SELECTOR = "ul.ProductList > li"
    LINK_SELECTOR = "a.pname"
    TITLE_SELECTOR = "a.pname"
    PRICE_SELECTOR = "em.p-price, .ProductPriceRating, [class*='price']"

    # --- Pagination ---
    PAGE_QUERY = "?page={n}"
    MAX_PAGES = 50

    SOLD_OUT_TEXT = ("sold out", "out of stock", "sold-out", "unavailable")

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._seen_urls: set[str] = set()

    async def scrape(self) -> CrawlResult:
        self.result.started_at = datetime.utcnow()
        self.result.status = "running"

        if not self.CATEGORY_PATHS:
            self.result.failures.append("No CATEGORY_PATHS configured")
            self.result.status = "failed"
            self.result.finished_at = datetime.utcnow()
            return self.result

        async with self:
            for path in self.CATEGORY_PATHS:
                await self._crawl_category(path)
            # Some stores only show name+price on the category cards and keep the
            # size in the product page body ("Size: 1\""). When FETCH_BODY_SIZE
            # is set, fetch each still-sizeless product page and mine it.
            if getattr(self, "FETCH_BODY_SIZE", False):
                await self._enrich_body_size()

        self.result.products_found = len(self.result.listings)
        self.result.variants_found = len(self.result.listings)
        self.result.status = "complete" if self.result.listings else "partial"
        if not self.result.listings and not self.result.failures:
            self.result.failures.append("No products discovered on any category page")
            self.result.status = "partial"
        self.result.finished_at = datetime.utcnow()
        logger.info(
            f"{self.VENDOR_NAME}: {len(self.result.listings)} listings from "
            f"{self.result.pages_crawled} pages"
        )
        return self.result

    async def _enrich_body_size(self):
        """For listings still missing a numeric size, fetch the product page and
        mine the size out of its body copy ('Size: 1\"', 'Current Size: …')."""
        from normalize.size import extract_size_from_description, parse_size
        targets = [l for l in self.result.listings
                   if getattr(l, "size_midpoint", None) is None and getattr(l, "product_url", None)]
        for l in targets:
            resp = await self.get(l.product_url)
            if not resp:
                continue
            tok = extract_size_from_description(resp.text)
            if tok:
                lo, hi, mid = parse_size(tok)
                if mid is not None:
                    l.size_text = l.size_text or tok
                    l.size_min_inches, l.size_max_inches, l.size_midpoint = lo, hi, mid
        logger.info(f"{self.VENDOR_NAME}: body-size enriched {len(targets)} product pages")

    def _page_url(self, path: str, page: int) -> str:
        base = self.BASE_URL + path
        if page == 1:
            return base
        sep = "&" if "?" in path else ""
        q = self.PAGE_QUERY.format(n=page)
        if "?" in path:
            q = q.replace("?", "&", 1)
        return base + q

    async def _crawl_category(self, path: str):
        page = 1
        while page <= self.MAX_PAGES:
            url = self._page_url(path, page)
            resp = await self.get(url)
            if not resp:
                break
            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select(self.PRODUCT_SELECTOR)
            if not cards:
                break
            self.result.pages_crawled += 1

            new_on_page = 0
            for card in cards:
                listing = self._parse_card(card)
                if listing is None:
                    continue
                if listing.product_url in self._seen_urls:
                    continue
                self._seen_urls.add(listing.product_url)
                self.result.listings.append(listing)
                new_on_page += 1

            # Stop when a page adds nothing new (end-of-range repeat or dupes).
            if new_on_page == 0:
                break
            page += 1

    def _parse_card(self, card) -> Optional[object]:
        link_el = card.select_one(self.LINK_SELECTOR)
        title_el = card.select_one(self.TITLE_SELECTOR) or link_el
        price_el = card.select_one(self.PRICE_SELECTOR)

        if not (link_el and title_el):
            return None
        href = link_el.get("href")
        if not href:
            return None
        product_url = href if href.startswith("http") else self.BASE_URL + href

        title = title_el.get_text(" ", strip=True)
        if not title or _is_supply(title):
            return None

        price_text = price_el.get_text(" ", strip=True) if price_el else None
        price = parse_price(price_text)
        if not price:
            return None

        card_text = card.get_text(" ", strip=True).lower()
        sold_out = any(t in card_text for t in self.SOLD_OUT_TEXT)

        sex_code, _ = normalize_sex(title)

        return self._make_listing(
            scientific_name=title,
            sex=sex_code,
            price_usd=price,
            product_url=product_url,
            availability=Availability.OUT_OF_STOCK if sold_out else Availability.IN_STOCK,
            raw_title=title,
            raw_price=price_text,
        )
