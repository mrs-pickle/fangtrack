"""
Price normalization for tarantula listings.
Handles standard prices, sale prices, from-prices, and bulk pricing.
"""
import re
from typing import Optional, Tuple


def parse_price(raw: Optional[str]) -> Optional[float]:
    """
    Parse a price string to float USD.
    Returns None if not parseable.
    """
    if not raw:
        return None
    # Remove currency symbols, commas
    cleaned = re.sub(r"[,$€£\s]", "", str(raw))
    try:
        val = float(cleaned)
        # Sanity: tarantula prices are between $1 and $10,000
        if 1.0 <= val <= 10000.0:
            return round(val, 2)
    except (ValueError, TypeError):
        pass
    return None


def is_from_price(raw: Optional[str]) -> bool:
    """
    Detect 'from $X' pricing which is NOT a confirmed variant price.
    """
    if not raw:
        return False
    return bool(re.search(r"\bfrom\b", raw, re.IGNORECASE))


def parse_bulk_price(raw: Optional[str]) -> Tuple[Optional[int], Optional[float], Optional[float]]:
    """
    Parse bulk/package pricing like '2 for $60' or '10/$150'.
    Returns (quantity, package_price, per_animal_price).
    """
    if not raw:
        return None, None, None

    # Pattern: "N for $X" or "N/$X"
    m = re.search(r"(\d+)\s*(?:for|/)\s*\$?\s*(\d+(?:\.\d+)?)", raw, re.IGNORECASE)
    if m:
        qty = int(m.group(1))
        pkg_price = float(m.group(2))
        per_animal = round(pkg_price / qty, 2)
        return qty, pkg_price, per_animal

    # Pattern: "$X for N" (reversed)
    m = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*for\s*(\d+)", raw, re.IGNORECASE)
    if m:
        pkg_price = float(m.group(1))
        qty = int(m.group(2))
        per_animal = round(pkg_price / qty, 2)
        return qty, pkg_price, per_animal

    return None, None, None


def parse_discount(regular: Optional[float], sale: Optional[float]) -> Optional[float]:
    """Calculate discount percentage."""
    if regular and sale and regular > 0:
        return round((regular - sale) / regular * 100, 1)
    return None
