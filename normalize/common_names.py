"""
Common name lookup for ~300 species commonly traded in the exotic invert hobby.
Covers tarantulas, true spiders, scorpions, centipedes, millipedes, and isopods.
Keys are normalized scientific_name_key (lowercase, no punctuation).
"""

COMMON_NAMES: dict[str, str] = {
    # ── Tarantulas ────────────────────────────────────────────────────────────
    "acanthoscurria geniculata":          "Brazilian White Knee",
    "amazonius germani":                  "Orange Tree Spider",
    "aphonopelma chalcodes":              "Arizona Blonde",
    "aphonopelma hentzi":                 "Texas Brown",
    "aphonopelma seemanni":               "Costa Rican Stripe Knee",
    "aphonopelma johnnycashi":            "Johnny Cash Tarantula",
    "augacephalus ezendami":              "Mozambique Golden Baboon",
    "avicularia avicularia":              "Common Pink Toe",
    "avicularia juruensis":               "Juruá Pink Toe",
    "avicularia merianae":                "Peruvian Pink Toe",
    "brachypelma auratum":                "Mexican Flame Knee",
    "brachypelma boehmei":                "Mexican Fire Leg",
    "brachypelma emilia":                 "Mexican Red Leg",
    "brachypelma hamorii":                "Mexican Red Knee",
    "brachypelma albiceps":               "Mexican Golden Red Rump",
    "caribena versicolor":                "Antilles Pink Toe",
    "ceratogyrus brachycephalus":         "Straight-Horned Baboon",
    "ceratogyrus darlingi":               "Rear-Horned Baboon",
    "ceratogyrus marshalli":              "Marshall's Horned Baboon",
    "chilobrachys natanicharum":          "Electric Blue Tarantula",
    "chilobrachys huahini":               "Asian Fawn",
    "chromatopelma cyaneopubescens":      "Green Bottle Blue",
    "cyriocosmus elegans":                "Trinidad Dwarf Tiger",
    "cyriopagopus sp bach ma":            "Vietnam Blue Earth Tiger",
    "davus pentaloris":                   "Guatemala Tiger Rump",
    "dolichothele diamantinensis":        "Brazilian Blue Dwarf Beauty",
    "ephebopus murinus":                  "Skeleton Tarantula",
    "euathlus sp smarged tiger":          "Emerald Tiger",
    "euathlus truculentus":               "Chilean Bronze",
    "grammostola pulchra":                "Brazilian Black",
    "grammostola pulchripes":             "Chaco Golden Knee",
    "grammostola rosea":                  "Chilean Rose Hair",
    "grammostola quirogai":               "Uruguayan Black Beauty",
    "hapalopus formosus":                 "Colombian Dwarf Pumpkin",
    "haplocosmia himalayana":             "Himalayan Mountain Fawn",
    "harpactira pulchripes":              "Golden Blue-Leg Baboon",
    "heteroscodra maculata":              "Togo Starburst Baboon",
    "homoeomma chilense":                 "Chilean Copper",
    "hysterocrates gigas":                "Cameroon Red Baboon",
    "idiothele mira":                     "Blue-Foot Baboon",
    "iridopelma hirsutum":                "Bahia Scarlet",
    "lasiocyaneo sazimai":                "Brazilian Blue",
    "lasiodora klugi":                    "Bahia Scarlet Birdeater",
    "lasiodora parahybana":               "Salmon Pink Birdeater",
    "linothele sericata":                 "Funnel Web",
    "melapoeus lividus":                  "Cobalt Blue",
    "melapoeus minax":                    "Thai Black",
    "megaphobema robustum":               "Colombian Giant Red Leg",
    "monocentropus balfouri":             "Socotra Island Blue Baboon",
    "neoholothele incei":                 "Trinidad Olive",
    "nhandu chromatus":                   "Brazilian Red & White",
    "nhandu tripepii":                    "Brazilian Giant Blond",
    "omothymus schioedtei":               "Malaysian Earth Tiger",
    "omothymus violaceopes":              "Singapore Blue",
    "ornithoctoninae sp veronica":        "Veronica Earth Tiger",
    "pamphobeteus sp mascara":            "Mascara Birdeater",
    "pamphobeteus platyomma":             "Colombian Platyomma",
    "pelinobius muticus":                 "King Baboon",
    "phormictopus cancerides":            "Haitian Brown",
    "phormictopus sp dominican purple":   "Dominican Purple",
    "phormingochilus hati hati":          "Purple Earth Tiger",
    "poecilotheria fasciata":             "Sri Lanka Ornamental",
    "poecilotheria metallica":            "Gooty Sapphire Ornamental",
    "poecilotheria ornata":               "Fringed Ornamental",
    "poecilotheria regalis":              "Indian Ornamental",
    "poecilotheria striata":              "Mysore Ornamental",
    "poecilotheria tigrinawesseli":       "Tiger Ornamental",
    "psalmopoeus cambridgei":             "Trinidad Chevron",
    "psalmopoeus irminia":                "Venezuelan Suntiger",
    "psalmopoeus victori":                "Darth Maul",
    "psalmopoeus reduncus":               "Costa Rican Tiger Rump",
    "pterinochilus murinus":              "Orange Baboon Tarantula",
    "selenobrachys philippinus":          "Philippine Tangerine",
    "stromatopelma calceatum":            "Featherleg Baboon",
    "tapinauchenius sanctivincenti":      "Antilles Mustard",
    "theraphosa apophysis":               "Pink Foot Goliath",
    "theraphosa blondi":                  "Goliath Birdeater",
    "theraphosa stirmi":                  "Burgundy Goliath Birdeater",
    "thrixopelma pruriens":               "Peruvian Green Velvet",
    "tliltocatl albopilosus":             "Curly Hair",
    "tliltocatl kahlenbergi":             "Mexican Rose Gray",
    "tliltocatl schroederi":              "Mexican Black Velvet",
    "tliltocatl vagans":                  "Mexican Red Rump",
    "tliltocatl verdezi":                 "Tulum Dwarf Brown",
    "xenesthis intermedia":               "Amazon Blue Bloom Birdeater",
    "xenesthis sp blue":                  "Blue Bloomed Birdeater",
    "xenesthis sp white":                 "White Tailed Birdeater",
    "ybyrapora diversipes":               "Amazon Sapphire Pink Toe",
    "ybyrapora sooretama":                "Sooretama Pink Toe",
    "birupes simoroxigorum":              "Borneo Neon Blue Leg",
    "devicarina guidonae":                "Saffron Dwarf Pumpkin",
    "anqasha sp blue":                    "Ecuadorian Blue",
    "linothele fallax":                   "Colombian Funnel Web",
    # ── True Spiders ─────────────────────────────────────────────────────────
    "phidippus regius":                   "Regal Jumping Spider",
    "phidippus audax":                    "Bold Jumping Spider",
    "hyllus diardi":                      "Heavy Jumping Spider",
    "eresus sp ruficapillus":             "Sicilian Black Beauty Velvet Spider",
    "hogna miami":                        "Miami Wolf Spider",
    "dolomedes sp":                       "Fishing Spider",
    # ── Scorpions ────────────────────────────────────────────────────────────
    "pandinus imperator":                 "Emperor Scorpion",
    "pandinus cavimanus":                 "Togo Starburst Scorpion",
    "heterometrus spinifer":              "Giant Forest Scorpion",
    "heterometrus laoticus":              "Asian Forest Scorpion",
    "androctonus australis":              "Fat-Tailed Scorpion",
    "leiurus quinquestriatus":            "Death Stalker",
    "parabuthus transvaalicus":           "Spitting Thick-Tailed Scorpion",
    "hadrurus arizonensis":               "Giant Desert Hairy Scorpion",
    "centruroides vittatus":              "Striped Bark Scorpion",
    "opistophthalmus sp":                 "Rock Scorpion",
    # ── Centipedes ───────────────────────────────────────────────────────────
    "scolopendra subspinipes":            "Giant Centipede",
    "scolopendra dehaani":                "Vietnamese Centipede",
    "scolopendra gigantea":               "Amazonian Giant Centipede",
    "scolopendra hardwickei":             "Tiger Centipede",
    "scolopendra sp sumatran purple":     "Sumatran Purple Centipede",
    "ethmostigmus rubripes":              "Giant Australian Centipede",
    "cormocephalus sp":                   "Malaysian Centipede",
    # ── Millipedes ───────────────────────────────────────────────────────────
    "archispirostreptus gigas":           "Giant African Millipede",
    "narceus americanus":                 "American Giant Millipede",
    "telodeinopus aoutii":                "Giant Tanzanian Millipede",
    # ── Isopods ──────────────────────────────────────────────────────────────
    "armadillidium maculatum":            "Zebra Isopod",
    "armadillidium vulgare":              "Common Pill Bug",
    "cubaris sp rubber ducky":            "Rubber Ducky Isopod",
    "porcellio scaber":                   "Rough Sowbug",
    "porcellio laevis":                   "Dairy Cow Isopod",
    # ── Praying Mantis ───────────────────────────────────────────────────────
    "idolomantis diabolica":              "Devil's Flower Mantis",
    "creoboter sp":                       "Jeweled Flower Mantis",
    "hierodula sp":                       "Giant Asian Mantis",
}


def get_common_name(scientific_name_key: str) -> str | None:
    """Return common name for a species key, or None if unknown."""
    return COMMON_NAMES.get(scientific_name_key.lower().strip())


def enrich_listings_with_common_names(listings: list) -> None:
    """Add common_name to any listing where it's missing. Modifies in place."""
    for l in listings:
        is_dict = isinstance(l, dict)
        key = l.get("scientific_name_key") if is_dict else getattr(l, "scientific_name_key", None)
        existing = l.get("common_name") if is_dict else getattr(l, "common_name", None)
        if existing or not key:
            continue
        name = get_common_name(key)
        if name:
            if is_dict:
                l["common_name"] = name
            else:
                setattr(l, "common_name", name)
