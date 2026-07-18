"""
Josh's Frogs scraper.
URL: https://www.joshsfrogs.com
Platform: Custom CMS (proprietary, not Shopify/WooCommerce)

Josh's Frogs is a large, long-established operation (founded 2004) that
carries tarantulas, scorpions, mantids, millipedes, and isopods alongside
their primary dart frog business.

Invertebrate landing page:
  https://www.joshsfrogs.com/animals-for-sale/pet-insects-invertebrates.html
  (also: /live-insects-feeders/spiders/tarantulas.html)

Observed product title format (from search snippets):
  "[Common Name] - [Scientific Name] | [Size] (Captive Bred)"
  e.g. "Chilean Rose Hair Tarantula 'Red Color Form' - Grammostola rosea 'RCF' | 1/2 inch (Captive Bred)"
       "Mascara Giant Birdeater Tarantula - Pamphobeteus sp. \"Mascara\" | 1 inch (Captive Bred)"
       "Goliath Pink Toe Tarantula - Avicularia sp. 'Braunshauseni' | 1 inch (Captive Bred)"

Product URL pattern:
  /kp/[product-name]-[sku] or /sp/[product-name]-[sku]
  e.g. /kp/tarantula-8x8x8-nano-kit-for-sale-kit0081

Strategy:
  1. Crawl the invertebrates listing page
  2. Find product cards with title + price
  3. Parse species from the " - [Scientific Name]" portion of the title
  4. Parse size from the "| N inch" portion

NOTE: Josh's is a large JS-rendered site. First run may return empty if their
listing page requires JS. Run with --debug to check; if empty, Playwright needed.
The scraper will try both their listing pages and fall back to regex parsing.
"""
import logging
import re
from typing import Optional
from bs4 import BeautifulSoup
from models import CrawlResult, Availability
from vendors.base import BaseScraper
from normalize.sex import normalize_sex
from normalize.price import parse_price

logger = logging.getLogger(__name__)

# Josh's Frogs rebuilt their site (2025+). The catalog now lives under /c/...
# category pages that are server-rendered (each product card carries title,
# sale + regular price, and an Add to Cart / Out of Stock marker). Products
# link out to /sp/<slug>. Pagination is ?page=N.
CATEGORY_PATHS = [
    "/c/live_animals/arachnids/tarantulas",
    "/c/live_animals/arachnids/true-spiders",
    "/c/live_animals/arachnids/scorpions",
    "/c/live_animals/isopods",
    "/c/live_animals/millipedes",
    "/c/live_animals/roaches",
]
MAX_PAGES = 40

# Product card selectors (try these in order)
CARD_SELECTORS = [
    "div.product-grid-item",
    "div[class*='product-card']",
    "div[class*='ProductCard']",
    "li[class*='product']",
    "div.jf-product",
    "article[class*='product']",
    "div[class*='item-product']",
    "div.product",
]

TITLE_SELECTORS = [
    "h2.product-name", "h3.product-name",
    "p.product-name", "span.product-name",
    ".product-title", "[class*='ProductName']",
    "h2", "h3", "a[class*='title']",
]

PRICE_SELECTORS = [
    "span[class*='price']:not([class*='old']):not([class*='was'])",
    "div[class*='price']", ".product-price",
    "[data-price]", "span.price",
]


class JoshsFrogsScraper(BaseScraper):
    VENDOR_KEY  = "joshsfrogs"
    VENDOR_NAME = "Josh's Frogs"
    BASE_URL    = "https://www.joshsfrogs.com"
    PLATFORM    = "custom"

    async def scrape(self) -> CrawlResult:
        from datetime import datetime
        self.result.started_at = datetime.utcnow()
        self.result.status = "running"

        seen: set[str] = set()
        async with self:
            for path in CATEGORY_PATHS:
                page = 1
                while page <= MAX_PAGES:
                    sep = "&" if "?" in path else "?"
                    url = f"{self.BASE_URL}{path}{sep}page={page}"
                    resp = await self.get(url)
                    if not resp or resp.status_code == 404:
                        break
                    soup = BeautifulSoup(resp.text, "lxml")
                    self.result.pages_crawled += 1

                    cards = self._find_cards(soup)
                    new_on_page = 0
                    for href, node in cards:
                        if href in seen:
                            continue
                        seen.add(href)
                        listing = self._parse_new_card(href, node)
                        if listing:
                            self.result.listings.append(listing)
                            self.result.variants_found += 1
                            self.result.products_found += 1
                            new_on_page += 1
                    logger.info(
                        f"{self.VENDOR_NAME}: page {page} of {path} — "
                        f"{new_on_page} new listings"
                    )
                    if new_on_page == 0:
                        break
                    page += 1

        if not self.result.listings:
            self.result.failures.append(
                "No listings found on Josh's Frogs category pages — site structure "
                "may have changed again."
            )

        self.result.status = "complete" if self.result.listings else "partial"
        self.result.finished_at = datetime.utcnow()
        logger.info(
            f"{self.VENDOR_NAME}: Done. "
            f"{self.result.variants_found} listings, {len(self.result.failures)} failures."
        )
        return self.result

    def _find_cards(self, soup: BeautifulSoup) -> list:
        """Return [(product_href, card_node)] — one entry per unique product.

        For each /sp/ product link, climb to the smallest ancestor that holds a
        price and exactly one product link, so sibling products don't merge.
        """
        out, seen = [], set()
        for a in soup.select("a[href*='/sp/']"):
            href = a.get("href")
            if not href or href in seen:
                continue
            node = a
            for _ in range(6):
                if node.parent is None:
                    break
                node = node.parent
                if "$" in node.get_text() and len(node.select("a[href*='/sp/']")) == 1:
                    break
            seen.add(href)
            full = href if href.startswith("http") else self.BASE_URL + href
            out.append((full, node))
        return out

    def _parse_new_card(self, href: str, node) -> Optional[object]:
        text = node.get_text(" ", strip=True)

        prices = re.findall(r"\$\s*(\d+(?:\.\d+)?)", text)
        if not prices:
            return None
        price = parse_price(prices[0])
        if not price:
            return None
        regular = parse_price(prices[1]) if len(prices) > 1 else None
        if regular and regular <= price:
            regular = None

        low = text.lower()
        if "out of stock" in low or "sold out" in low:
            avail = Availability.OUT_OF_STOCK
        elif "add to cart" in low or "pre-order" in low or "preorder" in low:
            avail = Availability.IN_STOCK
        else:
            avail = Availability.UNKNOWN

        # Title = everything before the price / review-count / captive marker.
        title = re.split(r"\s*\$", text, 1)[0]
        title = re.sub(r"\s*\(\d+\)\s*$", "", title).strip()   # trailing (12) review count
        title = re.sub(r"\s*Save\s+\d+%.*$", "", title, flags=re.I).strip()
        if not title:
            return None

        sci, size, common = self._parse_jf_title(title, "")
        if not sci:
            return None

        return self._make_listing(
            scientific_name=sci,
            common_name=common,
            size_text=size,
            price_usd=price,
            regular_price_usd=regular,
            availability=avail,
            product_url=href,
            raw_title=title,
            raw_price=f"${prices[0]}",
        )

    async def _try_shopify_json(self) -> Optional[dict]:
        data = await self.get_json(f"{self.BASE_URL}/products.json?limit=5")
        if data and data.get("products"):
            all_prods = list(data["products"])
            page = 2
            while True:
                more = await self.get_json(
                    f"{self.BASE_URL}/products.json?limit=250&page={page}"
                )
                if not more or not more.get("products"):
                    break
                all_prods.extend(more["products"])
                if len(more["products"]) < 250:
                    break
                page += 1
            return {"products": all_prods}
        return None

    def _parse_shopify(self, data: dict):
        for p in data.get("products", []):
            title = p.get("title", "")
            handle = p.get("handle", "")
            url = f"{self.BASE_URL}/products/{handle}"
            sci, size, common = self._parse_jf_title(title, "")
            if not sci:
                continue
            for v in p.get("variants", []):
                price = parse_price(v.get("price", ""))
                if not price:
                    continue
                avail = Availability.IN_STOCK if v.get("available") else Availability.OUT_OF_STOCK
                listing = self._make_listing(
                    scientific_name=sci, common_name=common,
                    size_text=size, price_usd=price,
                    availability=avail, product_url=url,
                    raw_title=title, raw_price=v.get("price", ""),
                )
                self.result.listings.append(listing)
                self.result.variants_found += 1
            self.result.products_found += 1

    def _parse_listing_page(self, soup: BeautifulSoup, page_url: str) -> list:
        """Try card selectors, then regex fallback."""
        for sel in CARD_SELECTORS:
            cards = soup.select(sel)
            if len(cards) >= 2:
                parsed = [self._parse_card(c, page_url) for c in cards]
                parsed = [l for l in parsed if l]
                if parsed:
                    logger.debug(f"{self.VENDOR_NAME}: {len(parsed)} cards via '{sel}'")
                    return parsed

        return self._regex_fallback(soup, page_url)

    def _parse_card(self, card, page_url: str):
        # -- Title --
        name = None
        for sel in TITLE_SELECTORS:
            el = card.select_one(sel)
            if el:
                name = el.get_text(strip=True)
                if name and len(name) > 5:
                    break
        if not name:
            return None

        # -- Price --
        price_text = None
        for sel in PRICE_SELECTORS:
            el = card.select_one(sel)
            if el:
                price_text = el.get_text(strip=True)
                if price_text:
                    break
        if not price_text:
            m = re.search(r'\$\s*\d+(?:\.\d+)?', card.get_text())
            price_text = m.group(0) if m else None

        price = parse_price(price_text) if price_text else None
        if not price:
            return None

        # -- Link --
        link_el = card.select_one("a[href]")
        prod_url = page_url
        if link_el:
            href = link_el["href"]
            prod_url = href if href.startswith("http") else self.BASE_URL + href

        # -- Availability --
        card_text = card.get_text().lower()
        if "out of stock" in card_text or "sold out" in card_text:
            avail = Availability.OUT_OF_STOCK
        elif "add to cart" in card_text:
            avail = Availability.IN_STOCK
        else:
            avail = Availability.UNKNOWN

        # -- Parse title into scientific name + size --
        vt = card.select_one("[class*='variant'], [class*='size']")
        variant_text = vt.get_text(strip=True) if vt else ""
        sci, size, common = self._parse_jf_title(name, variant_text)
        if not sci:
            return None

        return self._make_listing(
            scientific_name=sci,
            common_name=common,
            size_text=size,
            price_usd=price,
            availability=avail,
            product_url=prod_url,
            raw_title=name,
            raw_price=price_text or "",
        )

    def _parse_jf_title(self, title: str, variant: str) -> tuple:
        """
        Josh's Frogs title format:
          "Common Name - Scientific Name | N inch (Captive Bred)"
          "Scientific Name | N inch (Captive Bred)"

        Returns (scientific_name, size_text, common_name)
        """
        # Strip captive bred / wild caught flags
        clean = re.sub(r'\s*\((?:Captive Bred|CB|WC|Wild Caught)[^)]*\)\s*', '', title, flags=re.I)

        # Extract size from | delimiter
        size = None
        if "|" in clean:
            parts = clean.split("|", 1)
            size_part = parts[1].strip()
            m = re.search(r'[\d./]+\s*(?:inch(?:es)?|")', size_part, re.I)
            if m:
                size = m.group(0).strip()
            clean = parts[0].strip()

        # Check for "Common Name - Scientific Name" pattern
        common = None
        sci = clean.strip()
        if " - " in clean:
            dash_parts = clean.split(" - ", 1)
            # The scientific name is usually after the dash (contains genus)
            # Genus is capitalized, species is lowercase
            candidate_sci = dash_parts[1].strip()
            candidate_common = dash_parts[0].strip()
            # Validate: scientific name should start with uppercase genus
            if re.match(r'^[A-Z][a-z]+', candidate_sci):
                sci = candidate_sci
                common = candidate_common
            else:
                # Other direction
                candidate_sci = dash_parts[0].strip()
                if re.match(r'^[A-Z][a-z]+', candidate_sci):
                    sci = candidate_sci
                    common = dash_parts[1].strip()

        # Clean up quotes/apostrophes from locale info in sci name
        # e.g. "Grammostola rosea 'RCF'" -> keep as-is (locale is useful)

        # Extract size from variant text if not found yet
        if not size and variant:
            m = re.search(r'[\d./]+\s*(?:inch(?:es)?|")', variant, re.I)
            if m:
                size = m.group(0).strip()

        # New-site titles embed the size inline (no '|'): "Genus species 1.5\"".
        # Pull a trailing inch measurement off the sci name and strip it.
        if not size:
            m = re.search(r'(\d+(?:[./]\d+)?(?:\s*-\s*\d+(?:[./]\d+)?)?)\s*(?:inch(?:es)?|")', sci, re.I)
            if m:
                size = m.group(0).strip()
                sci = (sci[:m.start()] + sci[m.end():]).strip()
        # Drop a bare trailing inch mark left on the name.
        sci = re.sub(r'\s*["”]\s*$', '', sci).strip()

        if not sci or len(sci) < 4:
            return None, None, None

        return sci, size, common

    def _regex_fallback(self, soup: BeautifulSoup, page_url: str) -> list:
        """Scan page text for JF-format product entries."""
        text = soup.get_text(separator="\n")
        listings = []
        # Match "Common Name - Genus species | size" style
        pattern = re.compile(
            r'([A-Za-z\s\'"-]+\s*[-–]\s*[A-Z][a-z]+\s+[a-z][a-z\s.\'\"()-]*)'
            r'(?:\s*\|\s*([\d./]+\s*(?:inch(?:es)?|")))?'
            r'[^$\n]*\$\s*(\d+(?:\.\d+)?)',
            re.MULTILINE | re.IGNORECASE,
        )
        for m in pattern.finditer(text):
            raw_name = m.group(1).strip()
            size = m.group(2)
            price = float(m.group(3))
            if price < 5:
                continue
            sci, sz, common = self._parse_jf_title(raw_name, "")
            if sz and not size:
                size = sz
            if not sci:
                continue
            listings.append(self._make_listing(
                scientific_name=sci,
                common_name=common,
                size_text=size,
                price_usd=price,
                availability=Availability.UNKNOWN,
                product_url=page_url,
                raw_title=raw_name,
                raw_price=f"${price}",
                notes="regex-fallback parse",
            ))
        return listings

    async def _paginate(self, base_url: str):
        """Follow pagination."""
        for page in range(2, 20):
            # Try common pagination patterns
            for sep in ["?pg=", "?page=", "?p="]:
                url = f"{base_url}{sep}{page}"
                resp = await self.get(url)
                if resp and resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "lxml")
                    listings = self._parse_listing_page(soup, url)
                    if not listings:
                        return
                    self.result.listings.extend(listings)
                    self.result.variants_found += len(listings)
                    self.result.pages_crawled += 1
                    break
            else:
                return
