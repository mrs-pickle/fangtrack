"""Fetchers. httpx for static pages/JSON; Playwright for JS-rendered pages.

Vendor modules call `await http.get(url)` and receive text. Choose the engine
in config.yaml (crawler.engine: httpx | playwright).
"""
from __future__ import annotations
import asyncio


class HttpxFetcher:
    def __init__(self, headers: dict | None = None, timeout: float = 30.0):
        import httpx
        self._client = httpx.AsyncClient(
            headers=headers or {"User-Agent": "TarantulaMarketTracker/1.0 (+contact)"},
            timeout=timeout, follow_redirects=True)

    async def get(self, url: str) -> str:
        r = await self._client.get(url)
        r.raise_for_status()
        return r.text

    async def aclose(self):
        await self._client.aclose()


class PlaywrightFetcher:
    """Renders JS, scrolls to trigger lazy-loading/infinite scroll, returns HTML."""
    def __init__(self, headless: bool = True, scroll_passes: int = 8):
        self._headless = headless
        self._scroll_passes = scroll_passes
        self._pw = None
        self._browser = None

    async def _ensure(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(headless=self._headless)

    async def get(self, url: str) -> str:
        await self._ensure()
        page = await self._browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=45000)
            for _ in range(self._scroll_passes):
                await page.mouse.wheel(0, 20000)
                await asyncio.sleep(0.6)
            return await page.content()
        finally:
            await page.close()

    async def aclose(self):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()


def make_fetcher(engine: str = "httpx", **kw):
    if engine == "playwright":
        return PlaywrightFetcher(**kw)
    return HttpxFetcher(**kw)
