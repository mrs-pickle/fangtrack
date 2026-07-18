"""
RetiredScraper — base for vendors that are intentionally not crawled.

Used when a vendor's site is dead/gone, has no machine-readable catalog, or
carries no relevant inventory. Returns a clean CrawlResult with status
"skipped" and a documented reason instead of crashing or silently returning
nothing, so `python main.py --vendor all` stays green and the reason is
recorded on the crawl run.
"""
import logging
from datetime import datetime

from models import CrawlResult
from vendors.base import BaseScraper

logger = logging.getLogger(__name__)


class RetiredScraper(BaseScraper):
    PLATFORM = "retired"
    REASON = "Retired — not crawled."

    async def scrape(self) -> CrawlResult:
        self.result.started_at = datetime.utcnow()
        self.result.status = "skipped"
        self.result.notes = self.REASON
        self.result.finished_at = datetime.utcnow()
        logger.info(f"{self.VENDOR_NAME}: SKIPPED — {self.REASON}")
        return self.result
