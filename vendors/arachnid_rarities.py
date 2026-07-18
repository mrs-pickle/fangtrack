"""
Arachnid Rarities (arachnidrarities.com) — Squarespace BULK JSON scraper.

The store is a Squarespace collection at /inventory. `?format=json` returns all
products in one request, each with its real product URL (/inventory/p/<slug>)
and its full list of size VARIANTS — the "Size" dropdown on the product page —
including per-size stock (qtyInStock) and price (in cents). This replaces the
old scraper that read the rendered /inventory text (which had no per-product
URLs and no size at all).
"""
import logging
from datetime import datetime

import httpx

from models import CrawlResult
from vendors.base import BaseScraper
from normalize.sex import normalize_sex
from normalize.livestock import is_livestock

logger = logging.getLogger(__name__)

VENDOR_KEY = "arachnid_rarities"
VENDOR_NAME = "Arachnid Rarities"
BASE_URL = "https://www.arachnidrarities.com"
COLLECTIONS = ["/inventory"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}


def _variant_price(v: dict):
    """Sale-aware variant price in dollars (Squarespace stores cents)."""
    def cents(x):
        try:
            return float(x) / 100.0
        except (TypeError, ValueError):
            return None
    if v.get("onSale") and v.get("salePrice"):
        return cents(v.get("salePrice"))
    return cents(v.get("price"))


def _variant_size_sex(v: dict, title: str):
    """Size text (from the Size option) + sex, from a variant's attributes."""
    size_text, sex_blob = None, ""
    for k, val in (v.get("attributes") or {}).items():
        if "size" in str(k).lower():
            size_text = val
        sex_blob += f" {val}"
    for ov in (v.get("optionValues") or []):
        val = ov.get("value", "")
        if "size" in str(ov.get("optionName", "")).lower():
            size_text = val
        sex_blob += f" {val}"
    sex_code, _ = normalize_sex(f"{sex_blob} {title}")
    return size_text, sex_code


async def _scrape_dicts() -> list[dict]:
    results = []
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=45) as c:
        for coll in COLLECTIONS:
            # Squarespace ?format=json returns ONE page (default 200 items) and
            # signals more via pagination.nextPage — paginate through all of it.
            items, offset, pages = [], 0, 0
            while pages < 20:
                try:
                    r = await c.get(f"{BASE_URL}{coll}?format=json&offset={offset}")
                    r.raise_for_status()
                    data = r.json()
                except Exception as e:
                    logger.warning(f"[{VENDOR_KEY}] {coll} fetch error: {e}")
                    break
                page_items = data.get("items", [])
                items.extend(page_items)
                pages += 1
                pg = data.get("pagination") or {}
                if not pg.get("nextPage") or not page_items:
                    break
                offset = pg.get("nextPageOffset", offset + len(page_items))
            for item in items:
                title = (item.get("title") or "").strip()
                if not title or not is_livestock(title):
                    continue
                slug = item.get("fullUrl") or ""
                url = f"{BASE_URL}{slug}" if slug.startswith("/") else (slug or BASE_URL)
                for v in (item.get("variants") or []):
                    price = _variant_price(v)
                    if not price or price <= 0:
                        continue
                    in_stock = bool(v.get("unlimited")) or (v.get("qtyInStock") or 0) > 0
                    size_text, sex_code = _variant_size_sex(v, title)
                    results.append({
                        "scientific_name": title, "sex": sex_code or "Unknown",
                        "size_text": size_text,
                        "price_usd": round(price, 2), "quantity": v.get("qtyInStock"),
                        "product_url": url,
                        "availability": "in_stock" if in_stock else "out_of_stock",
                        "variant_name": size_text,
                    })
    logger.info(f"[{VENDOR_KEY}] {len(results)} variant listings from Squarespace JSON")
    return results


class ArachnidRaritiesScraper(BaseScraper):
    VENDOR_KEY = VENDOR_KEY
    VENDOR_NAME = VENDOR_NAME
    BASE_URL = BASE_URL
    PLATFORM = "squarespace"

    async def scrape(self) -> CrawlResult:
        self.result.started_at = datetime.utcnow()
        self.result.status = "running"
        try:
            for d in await _scrape_dicts():
                self.result.listings.append(self._make_listing(
                    scientific_name=d["scientific_name"],
                    sex=d["sex"],
                    size_text=d["size_text"],
                    price_usd=float(d["price_usd"]),
                    quantity=d["quantity"],
                    availability=d["availability"],
                    product_url=d["product_url"],
                    variant_name=d["variant_name"],
                    raw_title=d["scientific_name"],
                ))
            self.result.products_found = len(self.result.listings)
            self.result.variants_found = len(self.result.listings)
            self.result.status = "complete" if self.result.listings else "partial"
        except Exception as e:
            self.result.failures.append(str(e))
            self.result.status = "failed"
        self.result.finished_at = datetime.utcnow()
        return self.result
