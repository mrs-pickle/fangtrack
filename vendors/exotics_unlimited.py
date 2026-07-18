"""Exotics Unlimited USA - Shopify (products.json)."""
from vendors.shopify_base import ShopifyScraper


class ExoticsUnlimitedScraper(ShopifyScraper):
    VENDOR_KEY = "exotics_unlimited"
    VENDOR_NAME = "Exotics Unlimited USA"
    BASE_URL = "https://exoticsunlimitedusa.com"
