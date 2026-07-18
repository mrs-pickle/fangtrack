"""
Sex Probability Estimator
Estimates the probability that an unsexed animal is female
based on species typical adult size, the animal's current size,
and general theraphosid growth patterns.

This is useful context for a buyer evaluating an "unsexed" listing
that's large enough to have been vented but wasn't.

Not used in deal scoring — shown as informational context only.
Scale: 0.0 (certain male) to 1.0 (certain female)
"""
from __future__ import annotations
from typing import Optional

# ---------------------------------------------------------------------------
# Adult size reference for common species (typical female DLS in inches)
# Used to position a given size on the growth curve
# ---------------------------------------------------------------------------
ADULT_SIZE_MAP: dict[str, float] = {
    # Large new world (7"+ females)
    "theraphosa blondi":              9.0,
    "theraphosa apophysis":           8.5,
    "theraphosa stirmi":              8.0,
    "lasiodora parahybana":           8.0,
    "lasiodora klugi":                7.5,
    "nhandu tripepii":                7.0,
    "acanthoscurria geniculata":      6.5,
    "xenesthis intermedia":           7.0,
    "xenesthis sp. blue":             7.0,
    "pamphobeteus mascara":           7.0,
    "pamphobeteus nigricolor":        7.0,
    "megaphobema robustum":           6.5,
    "nhandu carapoensis":             6.0,
    # Medium-large new world (5-7")
    "grammostola pulchripes":         7.0,
    "grammostola pulchra":            6.5,
    "grammostola rosea":              5.5,
    "grammostola quirogai":           5.0,
    "brachypelma hamorii":            5.5,
    "brachypelma emilia":             5.0,
    "brachypelma auratum":            5.0,
    "tliltocatl albopilosus":         5.5,
    "tliltocatl vagans":              5.0,
    "tliltocatl kahlenbergi":         5.0,
    "chromatopelma cyaneopubescens":  5.5,
    "caribena versicolor":            4.5,
    "lasiocyaneo sazimai":            5.5,
    "dolichothele diamantinensis":    2.5,
    "cyriocosmus elegans":            1.5,
    # Old world medium (4-6")
    "poecilotheria metallica":        6.0,
    "poecilotheria regalis":          6.0,
    "poecilotheria fasciata":         6.0,
    "poecilotheria tigrinawesseli":   6.0,
    "poecilotheria striata":          6.0,
    "psalmopoeus irminia":            5.0,
    "psalmopoeus cambridgei":         5.5,
    "psalmopoeus victori":            5.0,
    "psalmopoeus reduncus":           5.5,
    "melapoeus lividus":              5.0,
    "melapoeus minax":                5.5,
    "omothymus violaceopes":          7.5,
    "omothymus schioedtei":           6.0,
    "harpactira pulchripes":          4.5,
    "pterinochilus murinus":          4.5,
    "monocentropus balfouri":         4.0,
    "heteroscodra maculata":          5.0,
    "stromatopelma calceatum":        4.5,
    "ceratogyrus brachycephalus":     5.0,
    "ceratogyrus darlingi":           5.0,
    "pelinobius muticus":             7.5,
    "hysterocrates gigas":            6.0,
    "birupes simoroxigorum":          4.5,
    "phormingochilus hati hati":      4.5,
    "cyriopagopus sp. bach ma":       6.0,
    "chilobrachys natanicharum":      5.5,
    "chilobrachys huahini":           5.0,
}

# Default adult sizes by broad category (used when species not in map)
DEFAULT_ADULT_SIZES = {
    "large_nw":    7.0,   # Theraphosa, Lasiodora, Pamphobeteus
    "medium_nw":   5.5,   # Brachypelma, Grammostola
    "small_nw":    3.5,   # Cyriocosmus, Hapalopus
    "large_ow":    7.0,   # Omothymus, Pelinobius
    "medium_ow":   5.0,   # Poecilotheria, Psalmopoeus
    "small_ow":    4.0,   # Harpactira, Pterinochilus
    "default":     5.0,
}


def estimate_female_probability(species_key: str,
                                size_midpoint: Optional[float],
                                sex: str = "U") -> Optional[float]:
    """
    Estimate the probability (0.0 to 1.0) that an unsexed animal is female.

    Returns None for:
    - Animals already sexed (F/M/PF/PM)
    - Animals with no size info
    - Very small animals (< 0.75") where sexing is impossible
    - Animals where size > likely adult size (would have been sexed)

    For unsexed animals in the "sexable" size range:
    - Maps size as a fraction of adult DLS
    - Uses a sigmoidal function biased toward female
      (females are larger at any given age; at sexable sizes,
       more animals are female simply due to males maturing faster)
    """
    if sex in ("F", "M", "PF", "PM"):
        return None
    if size_midpoint is None or size_midpoint < 0.75:
        return None  # Too small to matter

    adult_size = ADULT_SIZE_MAP.get(species_key, DEFAULT_ADULT_SIZES["default"])
    size_fraction = size_midpoint / adult_size  # 0.0 = tiny sling, 1.0 = full adult

    if size_fraction < 0.15:
        return None   # still sling-sized — can't vent reliably

    if size_fraction >= 0.95:
        return 0.50   # at adult size still unsexed — unusual, genuinely 50/50

    # Between 20-75% of adult size: sexable but not sexed
    # Males molt to maturity at ~60-70% of female DLS (species-dependent)
    # If still listed unsexed at 60%+ of adult DLS, more likely female
    # (mature males would have been identified and often sold separately or priced lower)
    if size_fraction >= 0.65:
        # At this size, if male they would usually have matured
        # Higher probability female
        prob = 0.65 + (size_fraction - 0.65) * 0.30
    elif size_fraction >= 0.40:
        # Mid-range — roughly proportional
        prob = 0.50 + (size_fraction - 0.40) * 0.375
    else:
        # Small but sexable — slight female bias (males are smaller at this age)
        prob = 0.45 + (size_fraction - 0.15) * 0.20

    return round(min(0.90, max(0.35, prob)), 2)


def female_probability_label(prob: Optional[float]) -> str:
    """Human-readable label for sex probability."""
    if prob is None:
        return ""
    if prob >= 0.80:
        return f"~{int(prob*100)}% likely ♀"
    if prob >= 0.65:
        return f"~{int(prob*100)}% probable ♀"
    if prob >= 0.50:
        return f"~{int(prob*100)}% possible ♀"
    return f"~{int((1-prob)*100)}% possible ♂"


def annotate_sex_probability(listings: list) -> None:
    """
    Add female_probability and female_prob_label to each unsexed listing.
    """
    for l in listings:
        is_dict = isinstance(l, dict)
        key  = l.get("scientific_name_key") if is_dict else getattr(l, "scientific_name_key", None)
        mid  = l.get("size_midpoint")        if is_dict else getattr(l, "size_midpoint", None)
        sex  = (l.get("sex") or "U")         if is_dict else (getattr(l, "sex", None) or "U")

        prob  = estimate_female_probability(key or "", mid, sex)
        label = female_probability_label(prob)

        if is_dict:
            l["female_probability"] = prob
            l["female_prob_label"]  = label
        else:
            setattr(l, "female_probability", prob)
            setattr(l, "female_prob_label",  label)
