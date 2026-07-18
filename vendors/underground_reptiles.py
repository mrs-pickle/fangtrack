"""
Underground Reptiles scraper.
URL: https://undergroundreptiles.com
Platform: WooCommerce (Store API — bulk)

A large reptile/exotics retailer that also carries inverts. FangTrack is
inverts-only, so the shared is_livestock gate in WooStoreScraper keeps just the
tarantulas / scorpions / isopods / other inverts and drops all the
snakes/lizards/amphibians. (Those herps are saved for the future HerpTrack.)
"""
from vendors.woo_base import WooStoreScraper


class UndergroundReptilesScraper(WooStoreScraper):
    VENDOR_KEY = "underground_reptiles"
    VENDOR_NAME = "Underground Reptiles"
    BASE_URL = "https://undergroundreptiles.com"
    MAX_PAGES = 80   # large catalog; most pages are herps we filter out
