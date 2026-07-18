"""
V Exotic Me scraper.
URL: https://www.vexoticme.com
Platform: Shopify (products.json — bulk)
"""
from vendors.shopify_base import ShopifyScraper


class VExoticScraper(ShopifyScraper):
    VENDOR_KEY = "vexotic"
    VENDOR_NAME = "V Exotic"
    BASE_URL = "https://www.vexoticme.com"
