"""
Shopify-specific base scraper.
Uses the /products.json API endpoint -- reliable, no JS needed.
Returns all products with all variants including price/availability.
"""
import logging
from typing import Optional
from normalize.sex import sex_from_variant_title, normalize_sex
from normalize.size import parse_size
from normalize.price import parse_price, is_from_price
from models import Listing, CrawlResult, Availability
from vendors.base import BaseScraper

logger = logging.getLogger(__name__)


class ShopifyScraper(BaseScraper):
    """
    Base class for all Shopify-based vendors.
    Subclass and set VENDOR_KEY, VENDOR_NAME, BASE_URL.
    May override parse_variant_options() for vendor-specific option naming.
    """
    PLATFORM = "shopify"
    PRODUCTS_PER_PAGE = 250  # Shopify max
    REQUEST_DELAY = 1.0      # Shopify products.json is a public read API; 1s is polite
    # /collections/all/products.json returns the SAME as /products.json for a
    # normal store, but the FULL catalog for stores whose global /products.json
    # is truncated (e.g. Exotics Unlimited: 248 vs 731). So we prefer it, and
    # fall back to /products.json if the "all" collection is empty/unavailable.
    PRODUCTS_PATH = "/collections/all/products.json"
    FALLBACK_PATH = "/products.json"

    async def scrape(self) -> CrawlResult:
        from datetime import datetime
        self.result.started_at = datetime.utcnow()
        self.result.status = "running"

        page = 1
        all_products = []
        path = self.PRODUCTS_PATH

        async with self:
            while True:
                url = f"{self.BASE_URL}{path}?limit={self.PRODUCTS_PER_PAGE}&page={page}"
                resp = await self.get(url)

                # Shopify stores that are temporarily closed put the whole
                # storefront behind a password page: the homepage redirects to
                # /password and products.json returns 401/redirects. Stop the
                # scan immediately and mark the run skipped — the vendor is
                # picked up again automatically once the store reopens.
                if resp is not None and "/password" in str(resp.url):
                    return self._password_wall_result()

                data = None
                if resp is not None:
                    try:
                        data = resp.json()
                    except Exception:
                        logger.error(f"{self.VENDOR_NAME}: non-JSON products.json response")
                        self.result.failures.append(f"Non-JSON response: {url}")

                # If the "all" collection endpoint returns nothing on page 1,
                # retry once from the plain /products.json endpoint.
                if page == 1 and path != self.FALLBACK_PATH and not (data or {}).get("products"):
                    path = self.FALLBACK_PATH
                    self.result.failures.clear()
                    continue

                if not data:
                    # products.json dead on the very first page (e.g. 401) —
                    # probe the homepage to distinguish "temporarily closed
                    # behind password wall" from a genuinely broken endpoint.
                    if page == 1:
                        probe = await self.get(self.BASE_URL)
                        if probe is not None and "/password" in str(probe.url):
                            return self._password_wall_result()
                        if not self.result.failures:
                            logger.warning(f"{self.VENDOR_NAME}: No data on page {page}")
                        break
                    # Mid-pagination fetch failure (page > 1): almost always a 429
                    # that outlasted our retries. We ALREADY got full pages before
                    # this, so breaking here would silently drop the rest of the
                    # catalog and report a truncated count as if complete. Flag it
                    # truncated so the snapshot keeps the vendor's last good run.
                    self.result.truncated = True
                    self.result.status = "partial"
                    self.result.failures.append(
                        f"Pagination truncated at page {page} (fetch failed) — "
                        f"kept {len(all_products)} products from {page-1} full pages")
                    logger.warning(f"{self.VENDOR_NAME}: truncated at page {page} "
                                   f"(fetch failed after retries); marking run partial")
                    break

                products = data.get("products", [])
                if not products:
                    break

                # Filter to tarantula products only
                t_products = self._filter_tarantulas(products)
                all_products.extend(t_products)

                self.result.pages_crawled += 1
                logger.info(f"{self.VENDOR_NAME}: Page {page} — {len(t_products)} tarantula products")

                if len(products) < self.PRODUCTS_PER_PAGE:
                    break  # Last page
                page += 1

        self.result.products_found = len(all_products)

        for product in all_products:
            listings = self._parse_product(product)
            self.result.listings.extend(listings)
            self.result.variants_found += len(listings)

        self.result.status = "complete" if not self.result.failures else "partial"
        self.result.finished_at = datetime.utcnow()
        logger.info(
            f"{self.VENDOR_NAME}: Done. "
            f"{self.result.products_found} products, "
            f"{self.result.variants_found} variants, "
            f"{len(self.result.failures)} failures."
        )
        return self.result

    def _password_wall_result(self) -> CrawlResult:
        """Finish the run as skipped because the storefront is password-locked."""
        from datetime import datetime
        note = ("Storefront password-protected — store temporarily closed. "
                "Skipped this run; will resume automatically when it reopens.")
        logger.info(f"{self.VENDOR_NAME}: {note}")
        self.result.status = "skipped"
        self.result.notes = note
        self.result.failures.clear()
        self.result.finished_at = datetime.utcnow()
        return self.result

    def _filter_tarantulas(self, products: list) -> list:
        """
        Filter product list to live invertebrates (tarantulas, other spiders,
        scorpions, centipedes, millipedes, isopods, …).

        Uses the shared normalize.livestock.is_livestock gate, which identifies
        inverts by taxon keyword OR binomial name rather than a hardcoded genus
        list — the old keyword set silently dropped whole genera (Liphistius,
        Linothele, Cyriocosmus, Euathlus, Scorpiops, Scolopendra, …), which is
        why some stores scanned far short of their live catalog.
        Override in a subclass only if a vendor needs special handling.
        """
        from normalize.livestock import is_livestock
        results = []
        for p in products:
            title = p.get("title") or ""
            tags = " ".join(p.get("tags") or [])
            if is_livestock(title) or is_livestock(tags) or self._is_tarantula_product(p):
                results.append(p)
        return results

    def _is_tarantula_product(self, product: dict) -> bool:
        """Override in subclass for vendor-specific detection."""
        return False

    def _parse_product(self, product: dict) -> list[Listing]:
        """
        Parse a single Shopify product dict into one or more Listings.
        One Listing per variant (sex/size combination).
        """
        listings = []
        title = product.get("title", "").strip()
        handle = product.get("handle", "")
        product_url = f"{self.BASE_URL}/products/{handle}"
        body_html = product.get("body_html", "")

        # Extract common name from description if possible
        common_name = self._extract_common_name(title, body_html)

        variants = product.get("variants", [])

        for variant in variants:
            listing = self._parse_variant(title, common_name, product_url, variant, product)
            if listing:
                listings.append(listing)

        # If no variants parsed, create one listing from "from" price
        if not listings and product.get("variants"):
            v = product["variants"][0]
            raw_price = v.get("price", "0")
            price = parse_price(raw_price)
            if price:
                listing = self._make_listing(
                    scientific_name=title,
                    common_name=common_name,
                    price_usd=price,
                    product_url=product_url,
                    availability=Availability.UNKNOWN,
                    notes=f"'From' price only — variant not confirmed",
                    raw_title=title,
                    raw_price=raw_price,
                    description=body_html,
                )
                from models import VerificationLevel
                listing.verification_level = VerificationLevel.ESTIMATED
                listings.append(listing)

        return listings

    def _parse_variant(self, product_title: str, common_name: Optional[str],
                       product_url: str, variant: dict, product: dict) -> Optional[Listing]:
        """Parse a single Shopify variant dict into a Listing."""
        raw_price = variant.get("price", "")
        compare_at = variant.get("compare_at_price")
        variant_title = variant.get("title", "")
        available = variant.get("available", False)
        inventory_qty = variant.get("inventory_quantity")

        # Options (option1, option2, option3)
        opt1 = variant.get("option1") or ""
        opt2 = variant.get("option2") or ""
        opt3 = variant.get("option3") or ""
        all_opts = f"{opt1} {opt2} {opt3} {variant_title}".strip()

        # Parse price
        price = parse_price(raw_price)
        if not price:
            return None

        regular_price = parse_price(compare_at) if compare_at else None

        # Parse sex and size from options
        sex_code, sex_display = self.parse_sex_from_options(opt1, opt2, opt3, variant_title)
        size_text = self.parse_size_from_options(opt1, opt2, opt3, variant_title)

        # Availability
        if not available:
            avail = Availability.OUT_OF_STOCK
        elif inventory_qty is not None and inventory_qty <= 3:
            avail = Availability.LIMITED
        else:
            avail = Availability.IN_STOCK

        return self._make_listing(
            scientific_name=product_title,
            common_name=common_name,
            sex=sex_code,
            size_text=size_text,
            price_usd=price,
            regular_price_usd=regular_price,
            availability=avail,
            quantity=inventory_qty if inventory_qty and inventory_qty > 0 else None,
            product_url=product_url,
            variant_name=variant_title if variant_title != "Default Title" else None,
            raw_title=product_title,
            raw_variant=variant_title,
            raw_price=raw_price,
            description=product.get("body_html", "") if isinstance(product, dict) else None,
        )

    def parse_sex_from_options(self, opt1: str, opt2: str, opt3: str, variant_title: str) -> tuple:
        """
        Attempt to detect sex from Shopify variant options.
        Shopify stores organize options differently -- override per vendor if needed.
        """
        from normalize.sex import sex_from_variant_title
        # Try each option in order
        for text in [opt1, opt2, opt3, variant_title]:
            if text:
                code, display = sex_from_variant_title(text)
                if code != "Unknown":
                    return code, display
        return "Unknown", "Unknown"

    def parse_size_from_options(self, opt1: str, opt2: str, opt3: str, variant_title: str) -> Optional[str]:
        """
        Attempt to extract size text from Shopify variant options.
        Returns raw size string (e.g. '2"') or None.
        """
        import re
        # Look for inch patterns in options
        inch_pat = re.compile(r'\d+(?:\.\d+)?(?:\s*[-\u2013]\s*\d+(?:\.\d+)?)?\s*["\u201c\u201d]?(?:\s*inch(?:es)?)?')
        for text in [opt1, opt2, opt3, variant_title]:
            if text:
                m = inch_pat.search(text)
                if m:
                    return m.group(0).strip()
        return None

    def _extract_common_name(self, title: str, body_html: str) -> Optional[str]:
        """
        Try to extract common name from product title or description.
        e.g. "Grammostola pulchripes (Chaco Golden Knee)" -> "Chaco Golden Knee"
        """
        import re
        # Pattern: title contains parenthetical common name
        m = re.search(r'\(([^)]+)\)', title)
        if m:
            candidate = m.group(1).strip()
            # Reject if it looks like a locality or size
            if not re.search(r'\d', candidate) and len(candidate) > 3:
                return candidate
        return None
