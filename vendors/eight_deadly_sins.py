"""Eight Deadly Sins - Wix Stores (sitemap + per-product parse)."""
from vendors.wix_base import WixScraper


class EightDeadlySinsScraper(WixScraper):
    VENDOR_KEY = "eight_deadly_sins"
    VENDOR_NAME = "Eight Deadly Sins"
    BASE_URL = "https://www.eightdeadlysins.net"
