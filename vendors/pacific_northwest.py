"""Pacific Northwest Arachnids - Wix Stores (sitemap + per-product parse).

Old pacificnorthwestarachnids.com no longer resolves; current site is
pnwarachnids.com. Large store that keeps sold-out product pages live, so
the in-stock saved count is well below the sitemap URL count.
"""
from vendors.wix_base import WixScraper


class PacificNorthwestScraper(WixScraper):
    VENDOR_KEY = "pacific_northwest"
    VENDOR_NAME = "Pacific Northwest Arachnids"
    BASE_URL = "https://www.pnwarachnids.com"
