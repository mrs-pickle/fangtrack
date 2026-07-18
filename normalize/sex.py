"""
Sex normalization for tarantula listings.
Normalized codes: F, PF, M, MM, U, Unknown
"""
import re
from typing import Optional

SEX_MAP = {
    # Female
    "female": "F", "f": "F", "fem": "F",
    "confirmed female": "F", "sexed female": "F",
    "adult female": "F", "af": "F",
    # "Probable / likely female" is an unverified seller guess, not a
    # confirmation — we treat it as Unsexed so it's never presented as a sexed
    # animal anywhere on the site.
    "probable female": "U", "prob female": "U", "pf": "U",
    "likely female": "U", "possible female": "U",
    "probable f": "U",
    # Male
    "male": "M", "m": "M",
    "juvenile male": "M", "young male": "M",
    # Mature male
    "mature male": "MM", "mm": "MM", "matured male": "MM",
    "adult male": "MM", "am": "MM",
    "ultimate male": "MM",
    # Unsexed
    "unsexed": "U", "u": "U", "unconfirmed": "U",
    "unknown sex": "U", "unknown gender": "U",
    "0.0.1": "U",  # notation
}

SEX_DISPLAY = {
    "F": "Female",
    "PF": "Unsexed",   # legacy code — any old rows display as Unsexed
    "M": "Male",
    "MM": "Mature Male",
    "U": "Unsexed",
    "Unknown": "Unknown",
}


def normalize_sex(raw: Optional[str]) -> tuple[str, str]:
    """
    Parse a sex string -> (sex_code, sex_display).
    Returns ("Unknown", "Unknown") when not recognizable.
    """
    if not raw:
        return "Unknown", "Unknown"

    text = raw.strip().lower()
    # Remove surrounding punctuation
    text = re.sub(r'[\'"\(\)]', "", text).strip()

    # Direct lookup
    if text in SEX_MAP:
        code = SEX_MAP[text]
        return code, SEX_DISPLAY.get(code, code)

    # Partial matches
    if "mature male" in text or "adult male" in text or "ultimate male" in text:
        return "MM", "Mature Male"
    if "probable female" in text or "prob female" in text or "likely female" in text:
        return "U", "Unsexed"
    if "female" in text:
        return "F", "Female"
    if "male" in text:
        return "M", "Male"
    if "unsexed" in text or "unconfirmed" in text:
        return "U", "Unsexed"

    return "Unknown", "Unknown"


def sex_from_variant_title(variant_title: Optional[str]) -> tuple[str, str]:
    """
    Extract sex from a Shopify/WooCommerce variant title like '1" Female' or 'MM 3"'.
    """
    if not variant_title:
        return "Unknown", "Unknown"
    # Try the whole thing first
    code, display = normalize_sex(variant_title)
    if code != "Unknown":
        return code, display
    # Try splitting and checking each token
    for token in re.split(r"[\s/,|]", variant_title):
        code, display = normalize_sex(token.strip())
        if code != "Unknown":
            return code, display
    return "Unknown", "Unknown"
