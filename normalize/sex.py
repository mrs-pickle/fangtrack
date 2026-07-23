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


# Some sellers put the sex in the LISTING TITLE and leave the variant as a bare
# size ("Aphonopelma chalchodes - Male", variant '3"'). We were reading only the
# variant, so those animals showed as Unknown even though the seller told us.
#
# A title is prose, so only WHOLE WORDS count here — never the single-letter
# codes normalize_sex accepts ("f", "m", "u"), which collide with size notation
# and locality codes in real titles. Ambiguous titles stay Unknown: reporting a
# sex the seller did not state is worse than admitting we do not know.
_PAIR_RE = re.compile(r"\bpairs?\b|\bm\s*\+\s*f\b|\bf\s*\+\s*m\b", re.IGNORECASE)
_TITLE_UNSEXED_RE = re.compile(
    r"\bunsexed\b|\bunconfirmed\b|\b(?:probable|likely|possible)\s+(?:female|male)\b",
    re.IGNORECASE)
_TITLE_MM_RE = re.compile(r"\b(?:mature|adult|ultimate)\s+males?\b", re.IGNORECASE)
_TITLE_F_RE  = re.compile(r"\bfemales?\b", re.IGNORECASE)
_TITLE_M_RE  = re.compile(r"\bmales?\b", re.IGNORECASE)


def sex_from_title(title: Optional[str]) -> tuple[str, str]:
    """Extract a seller-stated sex from a listing TITLE.

    Returns ("Unknown", "Unknown") unless the title states one sex plainly.
    A pair listing ("PAIR M+F") is deliberately Unknown — it is not a single
    sexed animal, so labelling it either way would misdescribe what is sold.
    """
    if not title:
        return "Unknown", "Unknown"
    if _PAIR_RE.search(title):
        return "Unknown", "Unknown"
    if _TITLE_UNSEXED_RE.search(title):
        return "U", SEX_DISPLAY["U"]
    if _TITLE_MM_RE.search(title):
        return "MM", SEX_DISPLAY["MM"]
    has_f = bool(_TITLE_F_RE.search(title))
    has_m = bool(_TITLE_M_RE.search(title))
    if has_f and has_m:            # e.g. "males and females available"
        return "Unknown", "Unknown"
    if has_f:
        return "F", SEX_DISPLAY["F"]
    if has_m:
        return "M", SEX_DISPLAY["M"]
    return "Unknown", "Unknown"


def annotate_missing_sex(listings: list) -> int:
    """Fill in a seller-stated sex that the scraper missed. Returns how many.

    Sex is extracted per-vendor (each scraper reads its own variant field), so a
    seller who states it in the TITLE instead slipped through everywhere at once.
    This runs over the finished snapshot — one place, all vendors, historical rows
    included. FILL ONLY: a sex already extracted is never overwritten, so a
    variant-level fact always beats this title-level fallback.
    """
    filled = 0
    for l in listings:
        is_dict = isinstance(l, dict)
        cur = (l.get("sex") if is_dict else getattr(l, "sex", None)) or "Unknown"
        if cur != "Unknown":
            continue
        title = (l.get("raw_title") if is_dict else getattr(l, "raw_title", None)) \
            or (l.get("scientific_name") if is_dict else getattr(l, "scientific_name", None)) or ""
        code, display = sex_from_title(title)
        if code == "Unknown":
            continue
        if is_dict:
            l["sex"], l["sex_display"] = code, display
        else:
            l.sex, l.sex_display = code, display
        filled += 1
    return filled


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
