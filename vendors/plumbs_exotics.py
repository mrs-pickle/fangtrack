"""Plumb's Exotics - Ecwid storefront API scraper.

The Ecwid storefront is JS-rendered, but its backing API is publicly
reachable without a token:

    POST https://us-vir3-storefront-api.ecwid.com/storefront/api/v1/{STORE_ID}/catalog
    body: {"parentCategoryId": <id>, "pagination": {"offset": N, "limit": 60}, "lang": "en"}

(Request schema captured from the live storefront via Playwright — the SPA
issues these calls from a web worker.) The response carries, per product:
name, base price, sold-out flag, size option choices and the URL slug.

We list categories from the root call, walk each invert category with
pagination, and skip the VENOMOUS REPTILES category (not tracked here).
"""
import logging
import re
from datetime import datetime

from models import CrawlResult, Availability
from vendors.base import BaseScraper
from normalize.sex import normalize_sex

logger = logging.getLogger(__name__)


class PlumbsExoticsScraper(BaseScraper):
    VENDOR_KEY = "plumbs_exotics"
    VENDOR_NAME = "Plumb's Exotics"
    BASE_URL = "https://plumbsexotics.com"
    PLATFORM = "ecwid"

    STORE_ID = "109347075"
    API = f"https://us-vir3-storefront-api.ecwid.com/storefront/api/v1/{STORE_ID}/catalog"
    PAGE_LIMIT = 60
    # Categories that are not invertebrates.
    SKIP_CATEGORIES = {"venomous reptiles"}

    async def _post_catalog(self, body: dict):
        """POST to the storefront catalog API with the standard throttle/retry."""
        await self._throttle()
        headers = {"Content-Type": "application/json", "Origin": self.BASE_URL,
                   "Referer": self.BASE_URL + "/"}
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                resp = await self.client.post(self.API, json=body, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"{self.VENDOR_NAME}: HTTP {resp.status_code} on catalog POST")
            except Exception as e:
                logger.warning(f"{self.VENDOR_NAME}: catalog POST error ({attempt}): {e}")
            import asyncio
            await asyncio.sleep(3 * attempt)
        self.result.failures.append(f"catalog POST failed: {body}")
        return None

    async def scrape(self) -> CrawlResult:
        self.result.started_at = datetime.utcnow()
        self.result.status = "running"

        async with self:
            root = await self._post_catalog({"lang": "en"})
            if not root:
                self.result.status = "failed"
                self.result.finished_at = datetime.utcnow()
                return self.result

            cats = []
            for c in root.get("expandedCategories", []):
                for sub in c.get("subcategories", []):
                    name = (sub.get("name") or "").strip()
                    if name.lower().replace("​", "") in self.SKIP_CATEGORIES:
                        continue
                    cats.append((sub["id"], name))
            logger.info(f"{self.VENDOR_NAME}: categories: {[n for _, n in cats]}")

            for cat_id, cat_name in cats:
                await self._crawl_category(cat_id, cat_name)

        self.result.products_found = len(self.result.listings)
        self.result.variants_found = len(self.result.listings)
        self.result.status = "complete" if self.result.listings else "partial"
        self.result.finished_at = datetime.utcnow()
        logger.info(f"{self.VENDOR_NAME}: {len(self.result.listings)} listings")
        return self.result

    async def _crawl_category(self, cat_id: int, cat_name: str):
        offset = 0
        total = None
        while total is None or offset < total:
            data = await self._post_catalog({
                "categoryViewMode": "COLLAPSED", "lang": "en",
                "parentCategoryId": cat_id,
                "pagination": {"offset": offset, "limit": self.PAGE_LIMIT},
            })
            if not data:
                break
            ecs = data.get("expandedCategories", [])
            block = next((c for c in ecs
                          if c.get("categoryInfo", {}).get("id") == cat_id), None)
            if block is None:
                break
            total = block.get("totalProductsCount", 0)
            prods = block.get("products", [])
            if not prods:
                break
            self.result.pages_crawled += 1
            for p in prods:
                listing = self._parse_product(p, cat_name)
                if listing:
                    self.result.listings.append(listing)
            logger.info(f"{self.VENDOR_NAME}: {cat_name} offset {offset} — "
                        f"{len(prods)} products (total {total})")
            offset += len(prods)

    def _parse_product(self, p: dict, cat_name: str):
        name = (p.get("name") or "").strip()
        if not name:
            return None

        overrides = p.get("defaultOptionsOverrides") or {}
        prices = overrides.get("pricesOverrides") or {}
        variation = overrides.get("variationOverrides") or {}

        price = prices.get("basePriceWithModifiersDiscount") or prices.get("basePrice")
        if not price or price <= 0:
            return None

        sold_out = bool(variation.get("isSoldOut"))

        slug = (p.get("slugs") or {}).get("forRouteWithoutId") or ""
        url = f"{self.BASE_URL}/products/{slug}" if slug else self.BASE_URL

        # Size: the default preselected "Size" choice, when the product has one.
        size_text = None
        for opt in prices.get("optionsChoicesWithModifiersAndTaxes") or []:
            if str(opt.get("optionId", "")).lower() == "size":
                choices = opt.get("choices") or []
                if choices:
                    size_text = choices[0].get("choiceName")
                break
        # Sex is often encoded in the size choice ("4-5\" Confirmed Female")
        # rather than the product name — check both.
        sex_code, _ = normalize_sex(name)
        if sex_code == "Unknown" and size_text:
            sex_code, _ = normalize_sex(size_text)

        if size_text and not re.search(r"\d", size_text):
            size_text = None  # non-numeric labels like "Adult" — leave unparsed

        return self._make_listing(
            scientific_name=name,
            sex=sex_code,
            size_text=size_text,
            price_usd=float(price),
            availability=Availability.OUT_OF_STOCK if sold_out else Availability.IN_STOCK,
            product_url=url,
            notes=f"Category: {cat_name}",
            raw_title=name,
            raw_price=str(price),
        )
