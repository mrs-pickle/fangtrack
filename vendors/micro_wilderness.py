"""Micro Wilderness - Shopify (products.json)."""
from vendors.shopify_base import ShopifyScraper


class MicroWildernessScraper(ShopifyScraper):
    VENDOR_KEY = "micro_wilderness"
    VENDOR_NAME = "Micro Wilderness"
    BASE_URL = "https://www.microwilderness.com"
