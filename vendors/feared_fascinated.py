"""
Feared to Fascinated scraper.
URL: https://fearedtofascinated.com
Platform: Shopify (products.json — bulk)
"""
from vendors.shopify_base import ShopifyScraper


class FearedToFascinatedScraper(ShopifyScraper):
    VENDOR_KEY = "feared_fascinated"
    VENDOR_NAME = "Feared to Fascinated"
    BASE_URL = "https://fearedtofascinated.com"
