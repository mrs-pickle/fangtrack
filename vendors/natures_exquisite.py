"""Nature's Exquisite Creatures - BigCommerce (ClassicNext theme).

No /products.json feed; the catalog is server-rendered HTML product cards
inside habit-based category pages. We walk the three habit categories
(which partition the whole tarantula catalog) and dedup by product URL.
"""
from vendors.generic_custom import GenericCustomScraper


class NaturesExquisiteScraper(GenericCustomScraper):
    VENDOR_KEY = "natures_exquisite"
    VENDOR_NAME = "Nature's Exquisite Creatures"
    BASE_URL = "https://naturesexquisitecreatures.com"

    CATEGORY_PATHS = ["/terrestrial/", "/arboreal/", "/semi-arboreal/"]
    FETCH_BODY_SIZE = True   # size lives in the product-page body ("Size: 1\"")
    # Custom HTML site; per-product body fetches dominate its crawl time. 1.2s stays
    # polite for a small dedicated store while roughly halving its ~150s crawl.
    REQUEST_DELAY = 1.2
    # BigCommerce ClassicNext defaults in generic_custom already match:
    #   PRODUCT_SELECTOR = "ul.ProductList > li"
    #   LINK/TITLE       = "a.pname"
    #   PRICE_SELECTOR   = "em.p-price"
    PAGE_QUERY = "?page={n}"
