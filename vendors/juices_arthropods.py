"""
Juice's Arthropods (juicesarthropods.com) — Squarespace BULK JSON scraper.

Squarespace collections expose their full product list at `<collection>?format=json`
in ONE request — each item carries title, URL, per-variant price/sale-price,
stock quantity and option values. That replaced an earlier crawler that fetched
the sitemap and then hit one page per product (~120 requests) just to read the
price off each page's Open Graph tags.
"""
import logging
from datetime import datetime

import httpx

from models import CrawlResult, Availability
from vendors.base import BaseScraper
from normalize.sex import normalize_sex
from normalize.livestock import is_livestock

logger = logging.getLogger(__name__)

VENDOR_KEY = "juices_arthropods"
VENDOR_NAME = "Juice's Arthropods"
BASE_URL = "https://www.juicesarthropods.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}

# Squarespace collections that hold the live catalog. /shop is the master;
# add more here if the store splits inventory across collections.
COLLECTIONS = ["/shop"]


def _variant_price(v: dict):
    """Effective (sale-aware) price for a Squarespace variant, in dollars."""
    def cents(x):
        try:
            return float(x) / 100.0
        except (TypeError, ValueError):
            return None
    if v.get("onSale") and v.get("salePrice"):
        return cents(v.get("salePrice"))
    return cents(v.get("price"))


def _variant_size_sex(v: dict, title: str):
    """Pull size text + sex from a variant's option values, falling back to title."""
    size_text, sex_blob = None, ""
    for opt in (v.get("attributes") or {}).items():
        k, val = opt
        kl = str(k).lower()
        if "size" in kl:
            size_text = val
        sex_blob += f" {val}"
    # optionValues is the newer shape
    for ov in (v.get("optionValues") or []):
        val = ov.get("value", "")
        if "size" in str(ov.get("optionName", "")).lower():
            size_text = val
        sex_blob += f" {val}"
    sex_code, _ = normalize_sex(sex_blob or title)
    return size_text, sex_code


async def _scrape_dicts() -> list[dict]:
    results = []
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=45) as c:
        for coll in COLLECTIONS:
            # Squarespace ?format=json returns ONE page (~200 items) + a
            # pagination.nextPage flag — follow it so a growing catalog isn't
            # silently truncated at 200.
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
                variants = item.get("variants") or []
                if not variants:
                    continue
                for v in variants:
                    price = _variant_price(v)
                    if not price or price <= 0:
                        continue
                    in_stock = bool(v.get("unlimited")) or (v.get("qtyInStock") or 0) > 0
                    size_text, sex_code = _variant_size_sex(v, title)
                    results.append({
                        "vendor_key": VENDOR_KEY, "vendor_name": VENDOR_NAME,
                        "scientific_name": title, "sex": sex_code,
                        "size_text": size_text, "source_type": "CB",
                        "price_usd": round(price, 2), "quantity": v.get("qtyInStock"),
                        "product_url": url,
                        "availability": "in_stock" if in_stock else "out_of_stock",
                    })
    logger.info(f"[{VENDOR_KEY}] {len(results)} listings from Squarespace JSON")
    return results


class JuicesArthropodsScraper(BaseScraper):
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
                    sex=d["sex"] or "Unknown",
                    size_text=d["size_text"],
                    price_usd=float(d["price_usd"]),
                    quantity=d["quantity"],
                    availability=d["availability"],
                    product_url=d["product_url"],
                    raw_title=d["scientific_name"],
                ))
            self.result.products_found = len(self.result.listings)
            self.result.variants_found = len(self.result.listings)
            self.result.status = "complete"
        except Exception as e:
            self.result.failures.append(str(e))
            self.result.status = "failed"
        self.result.finished_at = datetime.utcnow()
        return self.result
