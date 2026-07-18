"""FangHub - Wix Stores (sitemap + per-product parse)."""
from vendors.wix_base import WixScraper


class FangHubScraper(WixScraper):
    VENDOR_KEY = "fanghub"
    VENDOR_NAME = "FangHub"
    BASE_URL = "https://www.fanghubtarantulas.com"
