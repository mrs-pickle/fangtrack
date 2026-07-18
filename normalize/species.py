"""
Scientific name normalization for cross-vendor species comparison.

Rules:
- Preserve the seller's exact name in scientific_name
- Build a normalized comparison key in scientific_name_key
- Handle punctuation, capitalization, locale variants, and common synonyms
"""
import re
from typing import Optional


# ---------------------------------------------------------------------------
# Synonym mappings loaded from normalize/synonyms.py
# That module contains the full, maintained synonym table.
# ---------------------------------------------------------------------------
from normalize.synonyms import SYNONYMS as _SYN_TABLE, apply_synonyms as _apply_synonyms

# Legacy local overrides (kept for backward compat, will defer to synonyms.py)
_LOCAL_OVERRIDES: dict[str, str] = {
    'pamphobeteus sp "mascara"': "pamphobeteus sp mascara",
    "xenesthis sp. bright":       "xenesthis sp bright",
    "orphnaecus sp. cebu":        "orphnaecus sp cebu",
    "orphnaecus cebu":            "orphnaecus sp cebu",
    "pterinochilus murinus rcf":  "pterinochilus murinus rcf",
    "pterinochilus murinus dcf":  "pterinochilus murinus dcf",
}


def normalize_species_key(raw_name: str) -> str:
    """
    Convert a seller's scientific name to a normalized comparison key.
    Does NOT overwrite original -- only used for grouping/comparison.
    """
    if not raw_name:
        return "unknown"

    # Apply synonym mapping first (reclassifications, misspellings, trade names)
    raw_name = _apply_synonyms(raw_name)

    key = raw_name.lower().strip()

    # Remove HTML entities
    key = re.sub(r"&[a-z]+;", " ", key)
    # Remove parenthetical locality notes like (Peru)
    key = re.sub(r"\([^)]*\)", " ", key)
    # Strip quotes around sp. forms
    key = re.sub(r'[\'"""''"„«»]', "", key)
    # Normalize sp. / ssp. / cf. / aff.
    key = re.sub(r"\bsp\.\b", "sp", key)
    key = re.sub(r"\bssp\.\b", "ssp", key)
    key = re.sub(r"\bcf\.\b", "cf", key)
    key = re.sub(r"\baff\.\b", "aff", key)
    # Remove remaining punctuation except hyphens
    key = re.sub(r"[^\w\s\-]", " ", key)
    # Collapse whitespace
    key = re.sub(r"\s+", " ", key).strip()

    # Check local override table
    if key in _LOCAL_OVERRIDES:
        return _LOCAL_OVERRIDES[key]

    return key


def parse_locality_form(raw_name: str) -> tuple[str, Optional[str]]:
    """
    Split species name into (base, locality_or_form).
    e.g. "Pterinochilus murinus RCF" -> ("Pterinochilus murinus", "RCF")
    """
    known_forms = [
        "RCF", "DCF", "Usambara", "Highland", "Lowland",
        "Blue", "Green", "Orange", "Red", "Gold",
        "M1", "M2", "M3", "M4", "M5",
        "Borneo", "Sulawesi", "Java", "Sumatra",
        "Peru", "Colombia", "Brazil", "Ecuador", "Venezuela",
        "Mascara", "Bright", "Dark", "CB", "WC",
    ]
    for form in known_forms:
        pattern = re.compile(r"\s+" + re.escape(form) + r"(\s+.*)?$", re.IGNORECASE)
        match = pattern.search(raw_name)
        if match:
            base = raw_name[:match.start()].strip()
            return base, raw_name[match.start():].strip()
    return raw_name, None

# Alias for stubs compatibility
comparison_key = normalize_species_key

