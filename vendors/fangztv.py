"""FangzTV - Shopify (products.json)."""
from vendors.shopify_base import ShopifyScraper


class FangzTVScraper(ShopifyScraper):
    VENDOR_KEY = "fangztv"
    VENDOR_NAME = "FangzTV"
    BASE_URL = "https://www.fangztv.com"
