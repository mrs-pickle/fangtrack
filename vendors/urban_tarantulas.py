"""
Urban Tarantulas scraper.
URL: https://www.urbantarantulas.com
Platform: Shopify

Specializes in tarantulas + scorpions. Known for M. balfouri communals
and claims to be the largest M. balfouri breeder in the US.

Option layout observed from product URLs:
  Products typically have single price per species (or male/female variant)
  Some products have quantity/size selectors as variants.
"""
import re
from vendors.shopify_base import ShopifyScraper


INVERT_KEYWORDS = {
    "tarantula", "scorpion", "centipede", "spider", "millipede",
    "avicularia", "brachypelma", "grammostola", "poecilotheria",
    "pamphobeteus", "xenesthis", "theraphosa", "psalmopoeus",
    "pterinochilus", "cyriopagopus", "haplopelma", "monocentropus",
    "harpactira", "caribena", "tliltocatl", "phormictopus",
    "dolichothele", "tapinauchenius", "hysterocrates", "nhandu",
    "lasiodora", "chromatopelma", "acanthoscurria", "birupes",
    "tityus", "pandinus", "heterometrus",  # scorpions
    "bumba", "ephebopus", "orphnaecus", "omothymus",
    "phormingochilus", "selenobrachys", "ybyrapora",
}

SKIP_TYPES = {
    "enclosure", "substrate", "supply", "supplies", "equipment",
    "book", "shirt", "accessory", "accessories", "feeder", "feeders",
    "care", "kit", "habitat", "merchandise", "merch",
}


class UrbanTarantulasScraper(ShopifyScraper):
    VENDOR_KEY  = "urban_tarantulas"
    VENDOR_NAME = "Urban Tarantulas"
    BASE_URL    = "https://www.urbantarantulas.com"

    def _filter_tarantulas(self, products: list) -> list:
        """Keep live inverts (tarantulas, scorpions, centipedes, …).

        Delegates to the shared is_livestock gate via the base class so no
        genus is silently missed.
        """
        return super()._filter_tarantulas(products)

    def parse_sex_from_options(self, opt1, opt2, opt3, variant_title):
        """
        Urban Tarantulas often encodes sex in the variant title
        e.g. "Female", "Male", "Unsexed", "Mature Male",
        or uses a separate "Quantity" option for communal packs (M. balfouri).
        """
        from normalize.sex import normalize_sex
        for text in [opt1, opt2, opt3, variant_title]:
            if text:
                code, display = normalize_sex(text)
                if code != "Unknown":
                    return code, display
        return "Unknown", "Unknown"

    def parse_size_from_options(self, opt1, opt2, opt3, variant_title):
        """
        Urban Tarantulas may encode size in variants like '1 inch', '2-3\"', etc.
        For communal listings (M. balfouri) the variant may be a pack quantity.
        """
        inch_pat = re.compile(
            r'\d+(?:\.\d+)?(?:\s*[-\u2013]\s*\d+(?:\.\d+)?)?\s*'
            r'(?:["\u201c\u201d]|inch(?:es)?)',
            re.IGNORECASE,
        )
        for text in [opt1, opt2, opt3, variant_title]:
            if text:
                m = inch_pat.search(text)
                if m:
                    return m.group(0).strip()
        # Fall through: if a variant looks like a communal quantity, note it
        for text in [opt1, opt2, opt3]:
            if text and re.search(r'\d+\s*(pack|communal|ind)', text, re.I):
                return None  # communal pack — no individual size
        return opt1 if opt1 and opt1.lower() not in ("default title",) else None
