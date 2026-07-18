"""Wonderland Exotics - Wix Stores (sitemap + per-product parse)."""
from vendors.wix_base import WixScraper


class WonderlandExoticsScraper(WixScraper):
    VENDOR_KEY = "wonderland_exotics"
    VENDOR_NAME = "Wonderland Exotics"
    BASE_URL = "https://www.wonderlandexoticsllc.com"
