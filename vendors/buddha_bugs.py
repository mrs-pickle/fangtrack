"""Buddha Bugs - Shopify (products.json).

Correct domain is buddha-bugs.com (hyphenated); the older buddhabugs.com
no longer resolves. Sells tarantulas, huntsman spiders, isopods and other
inverts, so the standard tarantula filter keeps the live-animal listings.
"""
from vendors.shopify_base import ShopifyScraper


class BuddhaBugsScraper(ShopifyScraper):
    VENDOR_KEY = "buddha_bugs"
    VENDOR_NAME = "Buddha Bugs"
    BASE_URL = "https://buddha-bugs.com"
