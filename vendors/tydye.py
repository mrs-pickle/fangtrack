"""TyDye Exotics - Shopify."""
from vendors.shopify_base import ShopifyScraper
class TyDyeExoticsScraper(ShopifyScraper):
    VENDOR_KEY = "tydye"
    VENDOR_NAME = "TyDye Exotics"
    BASE_URL = "https://tydyeexotic.com"
