"""
Species Synonym Table
Maps deprecated, misspelled, or alternate scientific names to their current
accepted canonical name. Covers:
  - Major genus reclassifications that happened 2015-2024
  - Brachypelma → Tliltocatl split (2017, Mendoza & Francke)
  - Avicularia → Caribena / Ybyrapora splits (2017, Sherwood)
  - Haplopelma / Cyriopagopus → Melopoeus (OW reclassification)
  - Common hobby misspellings and abbreviations

Canonical names follow current ATS / World Spider Catalog taxonomy.
When a seller uses an old name, normalize_species_key() remaps it before
inserting into price_history, so all historical records for a species
accumulate under one key regardless of what name each vendor uses.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# CANONICAL SYNONYM MAP
# Key   = any alternate name (lowercase, stripped)
# Value = current canonical scientific name (properly cased)
#
# Organized by reclassification event for maintainability.
# ---------------------------------------------------------------------------

SYNONYMS: dict[str, str] = {

    # ── Brachypelma → Tliltocatl split (2017) ──────────────────────────────
    # Seven species moved; the rest of Brachypelma stays.
    "brachypelma albopilosum":    "Tliltocatl albopilosus",
    "brachypelma albopilosus":    "Tliltocatl albopilosus",
    "brachypelma vagans":         "Tliltocatl vagans",
    "brachypelma verdezi":        "Tliltocatl verdezi",
    "brachypelma kahlenbergi":    "Tliltocatl kahlenbergi",
    "brachypelma epicureanum":    "Tliltocatl epicureanus",
    "brachypelma epicureanus":    "Tliltocatl epicureanus",
    "brachypelma sabulosum":      "Tliltocatl sabulosus",
    "brachypelma schroederi":     "Tliltocatl schroederi",
    "brachypelma angustum":       "Tliltocatl angustum",
    "brachypelma smithi":         "Brachypelma hamorii",   # B. smithi synonymized under hamorii 2012

    # Tliltocatl spelling variants (missing the second L — extremely common)
    "tlitocatl albopilosus":      "Tliltocatl albopilosus",
    "tlitocatl albopilosum":      "Tliltocatl albopilosus",
    "tliltocatl albopilosum":     "Tliltocatl albopilosus",  # -um vs -us
    "tlitocatl vagans":           "Tliltocatl vagans",
    "tlitocatl verdezi":          "Tliltocatl verdezi",
    "tlitocatl kahlenbergi":      "Tliltocatl kahlenbergi",
    "tlitocatl sabulosus":        "Tliltocatl sabulosus",
    "tlitocatl schroederi":       "Tliltocatl schroederi",
    "tlitocatl epicureanus":      "Tliltocatl epicureanus",

    # ── Avicularia splits (2017, Sherwood) ─────────────────────────────────
    # Caribena
    "avicularia versicolor":      "Caribena versicolor",
    "avicularia laeta":           "Caribena laeta",

    # Ybyrapora
    "avicularia diversipes":      "Ybyrapora diversipes",
    "avicularia sooretama":       "Ybyrapora sooretama",
    "avicularia gamba":           "Ybyrapora gamba",

    # Iridopelma
    "avicularia hirsuta":         "Iridopelma hirsutum",
    "avicularia hirsutum":        "Iridopelma hirsutum",
    "avicularia seladonium":      "Iridopelma seladonium",

    # ── Haplopelma / Cyriopagopus → Melopoeus ──────────────────────────────
    # Most former Haplopelma species moved to Melopoeus in 2022 revision
    "haplopelma lividum":         "Melopoeus lividus",
    "cyriopagopus lividus":       "Melopoeus lividus",
    "haplopelma lividus":         "Melopoeus lividus",
    "haplopelma minax":           "Melopoeus minax",
    "cyriopagopus minax":         "Melopoeus minax",
    "haplopelma vonwirthi":       "Melopoeus vonwirthi",
    "haplopelma albostriatum":    "Melopoeus albostriatus",
    "cyriopagopus albostriatus":  "Melopoeus albostriatus",
    "haplopelma schmidti":        "Melopoeus cf. schmidti",
    "cyriopagopus schmidti":      "Melopoeus cf. schmidti",
    "haplopelma sp. kanchanaburi":"Melopoeus sp. Kanchanaburi",

    # Cyriopagopus → Omothymus (Malaysian species)
    "cyriopagopus schioedtei":    "Omothymus schioedtei",
    "haplopelma schioedtei":      "Omothymus schioedtei",

    # ── Common hobby misspellings ───────────────────────────────────────────
    # Green Bottle Blue
    "chromatopelma cyanopubescens":  "Chromatopelma cyaneopubescens",  # missing E

    # Brazilian Blue — genus is Lasiocyano (Sherwood, Gabriel & Longhorn, 2021);
    # "Lasiocyaneo" is a misspelling, so it collapses ONTO the correct name.
    "lasiocyaneo sazimai":        "Lasiocyano sazimai",
    "lasiocyano sp.":             "Lasiocyano sazimai",
    "pterinopelma sazimai":       "Lasiocyano sazimai",     # former genus

    # Uruguayan Black
    "grammostola quirogui":       "Grammostola quirogai",  # common misspelling

    # Peruvian Green Velvet / Ewok
    "ewok pruriens":              "Thrixopelma pruriens",  # trade name as genus
    "thrixopelma pruriens":       "Thrixopelma pruriens",  # confirm current

    # Colombian Dwarf
    "hapalopus guerreroi":        "Hapalopus guerreroi",   # normalize vs formosus
    "hapalopus sp guerreroi":     "Hapalopus guerreroi",
    "hapalopus sp. guerreroi":    "Hapalopus guerreroi",

    # Brazilian Blue Dwarf Beauty
    "dolichothele diamantinensis":"Dolichothele diamantinensis",
    "oligoxystre diamantinensis": "Dolichothele diamantinensis",  # old genus

    # Cobalt Blue common variants
    "cobalt blue":                "Melopoeus lividus",

    # OBT
    "obt":                        "Pterinochilus murinus",
    "orange baboon tarantula":    "Pterinochilus murinus",

    # GBB
    "gbb":                        "Chromatopelma cyaneopubescens",
    "green bottle blue":          "Chromatopelma cyaneopubescens",

    # ── Phormingochilus hati hati → hati hati ──────────────────────────────
    "phormingochilus hatihati":   "Phormingochilus hati hati",
    "cyriopagopus hatihati":      "Phormingochilus hati hati",
    "cyriopagopus hati hati":     "Phormingochilus hati hati",

    # ── Selenobrachys → current name ───────────────────────────────────────
    "cyriopagopus philippinus":   "Selenobrachys philippinus",

    # ── Nhandu / Acanthoscurria corrections ────────────────────────────────
    "acanthoscurria geniculata":  "Acanthoscurria geniculata",  # confirm
    "nhandu chromatus":           "Nhandu chromatus",            # valid

    # ── Borneo/Malaysia species commonly listed under old names ────────────
    "haplopelma robustum":        "Cyriopagopus robustus",
    "cyriopagopus sp bach ma":    "Cyriopagopus sp. Bach Ma",
    "cyriopagopus sp. bach ma":   "Cyriopagopus sp. Bach Ma",

    # ── Augacephalus / Eupalaestrus / similar ──────────────────────────────
    # Augacephalus rufus (Gallon, 2002) is the valid name; "Aspinochilus" was a
    # mistaken mapping, so collapse it ONTO Augacephalus rather than away from it.
    "aspinochilus rufus":         "Augacephalus rufus",

    # ── Psalmopoeus / Tapinauchenius clarity ───────────────────────────────
    "psalmopoeus ecclesiasticus": "Pamphobeteus ecclesiasticus",  # common mix-up

    # ── Grammostola grossa vs G. pulchra ───────────────────────────────────
    # Some sellers confuse these; they are different species
    # Not mapping — they should remain separate

    # ── Chilean theraphosids ────────────────────────────────────────────────
    "euathlus truculentus":       "Euathlus truculentus",  # confirm (also listed as Euathlus blue)
    "thrixopelma ockerti":        "Thrixopelma ockerti",   # sometimes Euathlus ockerti

    # ── Pamphobeteus / Xenesthis ───────────────────────────────────────────
    "xenesthis intermedia":       "Xenesthis intermedia",  # sometimes listed as Amazon Blue Bloom
    "pamphobeteus platyomma":     "Pamphobeteus sp. Platyomma",
    "pamphobeteus sp platyomma":  "Pamphobeteus sp. Platyomma",
    "pamphobeteus sp. mascara":   "Pamphobeteus sp. Mascara",
    "pamphobeteus sp mascara":    "Pamphobeteus sp. Mascara",

    # ── Monocentropus balfouri spelling ────────────────────────────────────
    "monocentropus balfourei":    "Monocentropus balfouri",  # misspelling

    # ── Harpactira ─────────────────────────────────────────────────────────
    "pterinochilus pulchripes":   "Harpactira pulchripes",  # very old usage
}


def canonical_name(raw: str) -> str | None:
    """
    Return the canonical scientific name for a given input, or None if
    no synonym mapping exists.

    Input is case-insensitive. Returns properly-cased canonical name.
    """
    key = raw.strip().lower()
    # Direct match
    if key in SYNONYMS:
        return SYNONYMS[key]
    # Partial genus match for very common patterns
    # e.g. "Haplopelma lividum (WC)" → strip trailing notes first
    import re
    clean = re.sub(r'\s*[\(\[].+', '', key).strip()
    return SYNONYMS.get(clean)


def apply_synonyms(scientific_name: str) -> str:
    """
    Return the canonical form of a scientific name, applying synonym
    remapping if available. Falls through unchanged if no mapping exists.
    """
    canon = canonical_name(scientific_name)
    return canon if canon else scientific_name
