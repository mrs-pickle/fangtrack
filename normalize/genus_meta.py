"""
Genus-level metadata for faceted browse: biogeographic origin (New World vs
Old World) and a rough hobby care level (Beginner / Intermediate / Advanced).

These are genus-level generalisations for FILTERING/browse only — never care
advice. Unknown genera resolve to '' (origin) / 'Intermediate' (care) so they
simply don't over-claim. Non-tarantula genera (scorpions, isopods, etc.) get
origin '' and are excluded from the NW/OW facet rather than mislabeled.
"""
from __future__ import annotations

# ── Old World theraphosid genera (Asia / Africa / Australia) ────────────────
OLD_WORLD = {
    # Asia
    "poecilotheria", "chilobrachys", "cyriopagopus", "omothymus", "ornithoctonus",
    "haplopelma", "lampropelma", "phormingochilus", "phormigochilus", "selenocosmia",
    "selenobrachys", "orphnaecus", "coremiocnemis", "haplocosmia", "psednocnemis",
    "phlogiellus", "yamia", "birupes", "thrigmopoeus", "haploclastus", "poecilotheria",
    "chilocosmia", "chilobrachys", "chilobrachys", "cyriocosmus",  # cyriocosmus is NW; corrected below
    # Africa
    "pterinochilus", "ceratogyrus", "heteroscodra", "stromatopelma", "hysterocrates",
    "harpactira", "harpactirella", "augacephalus", "idiothele", "monocentropus",
    "pelinobius", "encyocratella", "eucratoscelus", "bacillochilus", "ceratogyrus",
}
# corrections: these are New World, remove if accidentally added
OLD_WORLD.discard("cyriocosmus")

# ── New World theraphosid genera (Americas) ─────────────────────────────────
NEW_WORLD = {
    "grammostola", "brachypelma", "tliltocatl", "aphonopelma", "avicularia",
    "caribena", "ybyrapora", "theraphosa", "lasiodora", "lasiodorides", "nhandu",
    "acanthoscurria", "pamphobeteus", "xenesthis", "megaphobema", "sericopelma",
    "psalmopoeus", "tapinauchenius", "ephebopus", "cyriocosmus", "hapalopus",
    "chromatopelma", "euathlus", "homoeomma", "thrixopelma", "bumba", "phormictopus",
    "cyclosternum", "davus", "crassicrus", "aphonopelma", "citharacanthus",
    "hapalotremus", "neoholothele", "holothele", "linothele", "typhochlaena",
    "iridopelma", "pseudhapalopus", "cotztetlana", "bonnetina", "schizopelma",
    "kochiana", "vitalius", "nhandu", "eupalaestrus", "plesiopelma", "catumiri",
    "magnacarina", "aphonopelma",
}

# ── Care level sets (hobby generalisation) ──────────────────────────────────
_BEGINNER = {
    "grammostola", "brachypelma", "tliltocatl", "aphonopelma", "caribena",
    "avicularia", "chromatopelma", "euathlus", "acanthoscurria", "bumba",
    "thrixopelma", "hapalopus", "homoeomma", "eupalaestrus", "ybyrapora",
}
_ADVANCED_NW = {
    "psalmopoeus", "tapinauchenius", "ephebopus", "pamphobeteus", "phormictopus",
    "xenesthis",
}


def origin(genus: str) -> str:
    g = (genus or "").lower()
    if g in OLD_WORLD:
        return "Old World"
    if g in NEW_WORLD:
        return "New World"
    return ""


def care_level(genus: str) -> str:
    g = (genus or "").lower()
    if g in _BEGINNER:
        return "Beginner"
    if g in OLD_WORLD or g in _ADVANCED_NW:
        return "Advanced"
    return "Intermediate"


def price_band(min_price) -> str:
    try:
        p = float(min_price)
    except (TypeError, ValueError):
        return ""
    if p < 25:   return "Under $25"
    if p < 50:   return "$25–50"
    if p < 100:  return "$50–100"
    if p < 250:  return "$100–250"
    return "$250+"


PRICE_BAND_ORDER = ["Under $25", "$25–50", "$50–100", "$100–250", "$250+"]
