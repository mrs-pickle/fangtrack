"""
Jamie's Tarantulas scraper.
URL: https://www.jamiesontheweb.com
Platform: Shopify

NOTE: Jamie periodically closes the shop (order backlog / health flare-ups)
by putting the Shopify storefront behind its password page. When that
happens every request redirects to /password; ShopifyScraper detects this
and returns a clean "skipped — temporarily closed" run instead of an error.
Crawls resume automatically once the store reopens.

Jamie's uses Shopify with variants organized as:
  Option 1: Size (e.g. "0.5 inch", "1 inch", "3-4 inch")
  Option 2: Sex (e.g. "Unsexed", "Female", "Male")
Products are categorized under "Tarantulas" product_type.
"""
from vendors.shopify_base import ShopifyScraper


class JamiesTarantulasScraper(ShopifyScraper):
    VENDOR_KEY = "jamies"
    VENDOR_NAME = "Jamie's Tarantulas"
    BASE_URL = "https://www.jamiesontheweb.com"

    def _filter_tarantulas(self, products: list) -> list:
        """Jamie's product_type is 'Tarantulas' for tarantulas."""
        results = []
        for p in products:
            product_type = (p.get("product_type") or "").lower()
            if "tarantula" in product_type:
                results.append(p)
            elif self._is_tarantula_product(p):
                results.append(p)
        return results

    def _is_tarantula_product(self, product: dict) -> bool:
        """
        Fallback: check tags for 'tarantula' or known scientific names in title.
        """
        tags = [t.lower() for t in (product.get("tags") or [])]
        title = (product.get("title") or "").lower()
        return "tarantula" in tags or any(
            kw in title for kw in ["brachypelma", "grammostola", "avicularia",
                                    "poecilotheria", "pamphobeteus", "nhandu",
                                    "lasiodora", "chromatopelma", "caribena"]
        )

    def parse_sex_from_options(self, opt1, opt2, opt3, variant_title):
        """
        Jamie's option layout:
          option1 = size
          option2 = sex (Female / Male / Unsexed / Mature Male)
        """
        from normalize.sex import normalize_sex
        # Try opt2 first (sex), then opt1
        for text in [opt2, opt1, opt3, variant_title]:
            if text:
                code, display = normalize_sex(text)
                if code != "Unknown":
                    return code, display
        return "Unknown", "Unknown"

    def parse_size_from_options(self, opt1, opt2, opt3, variant_title):
        """
        Jamie's option1 typically contains size.
        """
        import re
        # opt1 is usually size like "0.5 inch", "2-3 inch", "4 inch female"
        size_fields = [opt1, opt3, opt2, variant_title]
        inch_pat = re.compile(
            r'\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s*(?:["“”]|inch(?:es)?)',
            re.IGNORECASE
        )
        for text in size_fields:
            if text:
                m = inch_pat.search(text)
                if m:
                    return m.group(0).strip()
