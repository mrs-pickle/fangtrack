"""
ArachnoEden scraper.
URL: https://arachnoeden.org
Platform: WooCommerce (Store API — bulk)

Uses the public WooCommerce Store API (/wp-json/wc/store/v1/products), which
returns the whole catalog with price + stock in a couple of JSON requests —
far faster than the old crawler that walked every product-category page and
then fetched each product page individually.
"""
from vendors.woo_base import WooStoreScraper


class ArachnoEdenScraper(WooStoreScraper):
    VENDOR_KEY = "arachnoeden"
    VENDOR_NAME = "ArachnoEden"
    BASE_URL = "https://arachnoeden.org"
