"""Great Basin Serpentarium - Wix Stores (bulk catalog API)."""
from vendors.wix_base import WixScraper


class GreatBasinScraper(WixScraper):
    VENDOR_KEY = "great_basin"
    VENDOR_NAME = "Great Basin Serpentarium"
    BASE_URL = "https://www.greatbasinserpentarium.com"
