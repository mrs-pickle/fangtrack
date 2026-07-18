"""8 Paws Tarantulas - Wix Stores (bulk catalog API)."""
from vendors.wix_base import WixScraper


class EightPawsScraper(WixScraper):
    VENDOR_KEY = "eight_paws"
    VENDOR_NAME = "8 Paws Tarantulas"
    BASE_URL = "https://www.8pawstarantulas.com"
