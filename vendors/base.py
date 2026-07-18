"""
Abstract base class for all vendor scrapers.
Every vendor module must subclass BaseScraper and implement scrape().
"""
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
import httpx
from models import Listing, CrawlResult, VerificationLevel

logger = logging.getLogger(__name__)

import re as _re
_TAG_RE = _re.compile(r"<[^>]+>")
_WS_RE = _re.compile(r"\s+")
_DESC_MAX = 800   # plenty for CB/WC + size keywords; keeps the DB lean


def _clean_description(raw: str) -> Optional[str]:
    """HTML → plain text, whitespace-collapsed, length-capped. None if empty."""
    if not raw:
        return None
    text = _TAG_RE.sub(" ", str(raw))
    # decode the handful of entities that actually show up in product copy
    for a, b in (("&amp;", "&"), ("&nbsp;", " "), ("&quot;", '"'),
                 ("&#39;", "'"), ("&rsquo;", "'"), ("&ldquo;", '"'), ("&rdquo;", '"')):
        text = text.replace(a, b)
    text = _WS_RE.sub(" ", text).strip()
    return text[:_DESC_MAX] or None


class BaseScraper(ABC):
    """
    Base class providing shared HTTP, retry, and delay functionality.
    Subclasses implement scrape() and return a CrawlResult.
    """

    VENDOR_KEY: str = ""
    VENDOR_NAME: str = ""
    BASE_URL: str = ""
    PLATFORM: str = "unknown"

    REQUEST_DELAY: float = 2.0   # seconds between requests
    MAX_RETRIES: int = 3         # fail fast on a stubborn 429; recovery pass mops up
    TIMEOUT: int = 30

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )

    def __init__(self, config: dict = None):
        self.config = config or {}
        self._last_request_time: float = 0.0
        self.result = CrawlResult(
            vendor_key=self.VENDOR_KEY,
            vendor_name=self.VENDOR_NAME,
        )
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        # Full browser-like header set so a CDN bot-heuristic (Cloudflare et al.)
        # is less likely to flag our paginated JSON requests as a scraper.
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": self.USER_AGENT,
                "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
            },
            timeout=self.TIMEOUT,
            follow_redirects=True,
            http2=False,
        )
        return self

    async def __aexit__(self, *args):
        if self.client:
            await self.client.aclose()

    async def _throttle(self):
        """Enforce minimum delay between requests."""
        elapsed = time.monotonic() - self._last_request_time
        delay = self.REQUEST_DELAY - elapsed
        if delay > 0:
            await asyncio.sleep(delay)
        self._last_request_time = time.monotonic()

    async def get(self, url: str, **kwargs) -> Optional[httpx.Response]:
        """GET with retry and throttle."""
        await self._throttle()
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                resp = await self.client.get(url, **kwargs)
                if resp.status_code == 200:
                    return resp
                if resp.status_code in (429, 503):
                    # Honor a server-provided Retry-After; otherwise escalate the
                    # wait. Longer, more patient backoff here is what keeps a big
                    # Shopify catalog from truncating mid-pagination.
                    try:
                        ra = float(resp.headers.get("Retry-After", ""))
                    except (TypeError, ValueError):
                        ra = 0
                    # Cap the fallback wait low: the main pass should give up
                    # quickly on a stubborn 429 (marking the run truncated) and let
                    # the sequential, cooled-down recovery pass recover it. Still
                    # honor a server Retry-After up to a sane ceiling.
                    wait = min(max(ra, 8 * attempt), 30)
                    logger.warning(f"Rate limited on {url}, waiting {wait:.0f}s (attempt {attempt})")
                    await asyncio.sleep(wait)
                else:
                    logger.warning(f"HTTP {resp.status_code} on {url}")
                    return None
            except httpx.TimeoutException:
                logger.warning(f"Timeout on {url} (attempt {attempt})")
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(5 * attempt)
            except Exception as e:
                logger.error(f"Request error on {url}: {e}")
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(3 * attempt)
        self.result.failures.append(f"Failed after {self.MAX_RETRIES} retries: {url}")
        return None

    async def get_json(self, url: str, **kwargs) -> Optional[dict | list]:
        """GET and parse JSON response."""
        resp = await self.get(url, **kwargs)
        if resp:
            try:
                return resp.json()
            except Exception as e:
                logger.error(f"JSON parse error on {url}: {e}")
                self.result.failures.append(f"JSON error: {url}")
        return None

    @abstractmethod
    async def scrape(self) -> CrawlResult:
        """
        Crawl the vendor and return a CrawlResult with all Listing objects.
        Must be implemented by each vendor subclass.
        """
        raise NotImplementedError

    def _make_listing(self, **kwargs) -> Listing:
        """Helper to create a Listing with vendor fields pre-filled."""
        from normalize.species import normalize_species_key
        from normalize.species_canonical import canonical_species
        from normalize.size import price_per_inch, derive_size, detect_pack
        from normalize.sex import normalize_sex

        listing = Listing(
            vendor=self.VENDOR_NAME,
            vendor_key=self.VENDOR_KEY,
            verification_level=VerificationLevel.DIRECT,
            date_checked=datetime.utcnow(),
            **kwargs,
        )

        # Store a cleaned, bounded product description (strip HTML, collapse whitespace,
        # cap length) so it feeds source/size detection without bloating the DB.
        if listing.description:
            listing.description = _clean_description(listing.description)

        # Canonical species identity: collapse messy titles to one "genus
        # species" key + fill the common name. Falls back to the looser
        # normalizer if we can't confidently canonicalize.
        if listing.scientific_name:
            ckey, _disp, ccommon = canonical_species(listing.scientific_name)
            listing.scientific_name_key = ckey or normalize_species_key(listing.scientific_name)
            if ccommon and not listing.common_name:
                listing.common_name = ccommon

        # Size: parse the size field, else mine a numeric size from the verbose
        # variant / title, else fall back to a stated life-stage. Shared with the
        # DB save path via derive_size() so the two never disagree.
        if listing.size_midpoint is None:
            st, lo, hi, mid = derive_size(
                listing.size_text, listing.raw_variant, listing.variant_name,
                listing.raw_title, listing.scientific_name)
            listing.size_text = st
            listing.size_min_inches = lo
            listing.size_max_inches = hi
            listing.size_midpoint = mid

        # Multi-specimen pack: tag it so the price (which is for the whole pack)
        # isn't read or compared as a single-animal price. We record the per-
        # animal figure in the note.
        pack = detect_pack(listing.raw_title, listing.scientific_name, listing.size_text)
        if pack:
            per = (listing.price_usd / pack) if listing.price_usd else None
            tag = f"Pack of {pack}" + (f" (~${per:.0f}/animal)" if per else "")
            listing.notes = f"{tag}. {listing.notes}".strip() if listing.notes else tag

        # Auto-set sex_display
        from models import SEX_DISPLAY
        listing.sex_display = SEX_DISPLAY.get(listing.sex, listing.sex)

        # Price per inch
        listing.price_per_inch = price_per_inch(listing.price_usd, listing.size_midpoint)

        return listing


# Aliases for stubs.py compatibility
BaseVendor = BaseScraper
VERIFICATION_DIRECT = "direct"

# Listing is in models.py -- re-export here for stubs convenience
from models import Listing  # noqa: F401
