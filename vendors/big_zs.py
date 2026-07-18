"""Big Z's - Shopify (products.json).

Moved to https://www.bigzs.shop/ (old bigzstarantulas.com / bigzsexoticpets.com
domains are dead). Carries wild-type US natives (wolf spiders, fishing
spiders, vinegaroons) alongside tarantulas, so the default tarantula keyword
filter applies.
"""
from vendors.shopify_base import ShopifyScraper


class BigZsScraper(ShopifyScraper):
    VENDOR_KEY = "big_zs"
    VENDOR_NAME = "Big Z's"
    BASE_URL = "https://www.bigzs.shop"
