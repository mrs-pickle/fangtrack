"""Spider Shoppe - Shopify (products.json).

Vancouver-based store selling tarantulas + other exotics. The public
/products.json feed is live, so we reuse the standard ShopifyScraper and
rely on its tarantula filter to drop reptiles/supplies. The old
thespidershoppe.com host no longer resolves; spidershoppe.com is current.
"""
from vendors.shopify_base import ShopifyScraper


class SpiderShoppeScraper(ShopifyScraper):
    VENDOR_KEY = "spidershoppe"
    VENDOR_NAME = "Spider Shoppe"
    BASE_URL = "https://spidershoppe.com"
