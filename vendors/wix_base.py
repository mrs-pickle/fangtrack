"""
WixScraper — base scraper for Wix Stores vendors (BULK catalog API).

Wix storefronts are JS-rendered, but the Wix Stores backend exposes a
storefront GraphQL API that returns many products per request — each with
price, compare-at price and (crucially) an isInStock flag. That lets us pull
a whole catalog in a handful of requests instead of one page per product.

Flow:
  1. GET /_api/v1/access-tokens  → the Wix Stores app "instance" token
     (public, no auth needed — it's what the storefront itself uses).
  2. POST /_api/wix-ecommerce-storefront-web/api  with getFilteredProducts
     over the built-in "all products" collection, paginated 100 at a time.

This replaced an earlier sitemap + per-product-page crawler that needed one
request per product (≈600 for a big store); the bulk API cuts that to ~7.

Etiquette: still ≥2s between requests (BaseScraper throttle) — we just make
far fewer of them.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

from models import CrawlResult, Availability
from vendors.base import BaseScraper
from normalize.livestock import is_livestock
from normalize.sex import normalize_sex
from normalize.price import parse_price

logger = logging.getLogger(__name__)

STORES_APP_ID = "1380b703-ce81-ff05-f115-39571d94dfcd"
ALL_PRODUCTS_COLLECTION = "00000000-000000-000000-000000000001"

_PRODUCTS_QUERY = (
    "query getFilteredProducts($mainCollectionId: String!, $offset: Int, $limit: Int) {"
    "  catalog { category(categoryId: $mainCollectionId) {"
    "    productsWithMetaData(limit: $limit, offset: $offset, onlyVisible: false) {"
    "      totalCount"
    "      list { id name price comparePrice isInStock urlPart formattedPrice formattedComparePrice sku description }"
    "    } } } }"
)


class WixScraper(BaseScraper):
    REQUEST_DELAY = 1.0   # Wix storefront GraphQL is a read API; 1s is polite
    PLATFORM = "wix"
    PAGE = 100
    MAX_PAGES = 40  # safety (40*100 = 4000 products)

    async def _get_token(self) -> Optional[str]:
        resp = await self.get(self.BASE_URL + "/_api/v1/access-tokens")
        if not resp:
            return None
        try:
            return resp.json()["apps"][STORES_APP_ID]["instance"]
        except Exception as e:
            logger.warning(f"{self.VENDOR_NAME}: no Wix Stores token ({e})")
            return None

    async def _query(self, token: str, offset: int) -> Optional[dict]:
        await self._throttle()
        url = self.BASE_URL + "/_api/wix-ecommerce-storefront-web/api"
        headers = {"Authorization": token, "Content-Type": "application/json",
                   "User-Agent": self.USER_AGENT}
        body = {"query": _PRODUCTS_QUERY,
                "variables": {"mainCollectionId": ALL_PRODUCTS_COLLECTION,
                              "offset": offset, "limit": self.PAGE}}
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                r = await self.client.post(url, json=body, headers=headers)
                if r.status_code == 200:
                    return r.json()
                logger.warning(f"{self.VENDOR_NAME}: products API HTTP {r.status_code}")
            except Exception as e:
                logger.warning(f"{self.VENDOR_NAME}: products API error ({attempt}): {e}")
            import asyncio
            await asyncio.sleep(3 * attempt)
        return None

    async def scrape(self) -> CrawlResult:
        self.result.started_at = datetime.utcnow()
        self.result.status = "running"

        async with self:
            token = await self._get_token()
            if not token:
                self.result.failures.append("Could not obtain Wix Stores token")
                self.result.status = "failed"
                self.result.finished_at = datetime.utcnow()
                return self.result

            offset, total = 0, None
            while total is None or offset < total:
                if offset >= self.PAGE * self.MAX_PAGES:
                    break
                data = await self._query(token, offset)
                if not data:
                    break
                try:
                    meta = data["data"]["catalog"]["category"]["productsWithMetaData"]
                except Exception:
                    self.result.failures.append("Unexpected products API shape")
                    break
                total = meta.get("totalCount", 0)
                lst = meta.get("list", [])
                if not lst:
                    break
                self.result.pages_crawled += 1
                for p in lst:
                    listing = self._parse_product(p)
                    if listing:
                        self.result.listings.append(listing)
                logger.info(f"{self.VENDOR_NAME}: {offset + len(lst)}/{total} products")
                offset += len(lst)

        self.result.products_found = len(self.result.listings)
        self.result.variants_found = len(self.result.listings)
        self.result.status = "complete" if self.result.listings else "partial"
        self.result.finished_at = datetime.utcnow()
        logger.info(f"{self.VENDOR_NAME}: {len(self.result.listings)} listings "
                    f"in {self.result.pages_crawled} API pages")
        return self.result

    def _parse_product(self, p: dict) -> Optional[object]:
        name = (p.get("name") or "").strip()
        if not name or not is_livestock(name):
            return None

        price = parse_price(p.get("formattedPrice") or "") or p.get("price")
        if not price or price <= 0:
            return None
        regular = parse_price(p.get("formattedComparePrice") or "") or (p.get("comparePrice") or None)
        if regular and regular <= price:
            regular = None

        avail = Availability.IN_STOCK if p.get("isInStock") else Availability.OUT_OF_STOCK
        slug = p.get("urlPart") or ""
        url = f"{self.BASE_URL}/product-page/{slug}" if slug else self.BASE_URL

        sex_code, _ = normalize_sex(name)
        # Wix stores keep the size in the description body ("Current Size:
        # Approximately 3/4\"") — mine the CURRENT size (not the full-grown one).
        from normalize.size import extract_size_from_description
        size_text = extract_size_from_description(p.get("description"))
        # sex sometimes only stated in the body too
        if sex_code in ("Unknown", None) and p.get("description"):
            import re as _re
            body = _re.sub(r"<[^>]+>", " ", p.get("description") or "")
            sex_code, _ = normalize_sex(body[:200] + " " + name)
        return self._make_listing(
            scientific_name=name,
            sex=sex_code,
            size_text=size_text,
            price_usd=float(price),
            regular_price_usd=float(regular) if regular else None,
            availability=avail,
            product_url=url,
            raw_title=name,
            raw_price=p.get("formattedPrice") or str(price),
            description=p.get("description"),
        )
