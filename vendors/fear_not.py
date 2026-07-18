"""Fear Not Tarantulas - Shopify (products.json).

The site is a standard Shopify store (confirmed via /products.json), so the
older guess-the-shop-path HTML crawler was replaced with the reliable
ShopifyScraper base. The default tarantula keyword filter applies.
"""
from vendors.shopify_base import ShopifyScraper


class FearNotTarantulasScraper(ShopifyScraper):
    VENDOR_KEY = "fear_not"
    VENDOR_NAME = "Fear Not Tarantulas"
    BASE_URL = "https://www.fearnottarantulas.com"
