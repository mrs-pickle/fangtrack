"""
Canonical common-name map: species_key ("genus species") -> common name.

Curated from hobby-standard common names (Tarantula Collective / American
Tarantula Society usage) for the frequently-traded species, then augmented at
build time from names harvested out of vendor titles (see tools/build_common_names.py).
Keep this the single source of truth for the "(common name)" shown app-wide.
"""

COMMON_NAMES = {
    # Theraphosa & giants
    "theraphosa blondi": "Goliath Birdeater",
    "theraphosa apophysis": "Pinkfoot Goliath Birdeater",
    "theraphosa stirmi": "Burgundy Goliath Birdeater",
    "lasiodora parahybana": "Salmon Pink Birdeater",
    "lasiodora klugi": "Bahia Scarlet Birdeater",
    "pamphobeteus antinous": "Bolivian Steely Blue Birdeater",
    "xenesthis immanis": "Colombian Lesserblack",
    "xenesthis intermedia": "Colombian Purple Bloom",
    "acanthoscurria geniculata": "Brazilian Whiteknee",
    # Added 2026-07-17 (collection import surfaced these gaps)
    "phormictopus sp dominican purple": "Dominican Purple",
    "haplocosmia himalayana": "Himalayan Beauty",
    "augacephalus rufus": "Red Baboon",           # canonicalizer alias fixed 2026-07-16
    "lasiocyano sazimai": "Brazilian Blue",       # canonicalizer alias fixed 2026-07-16
    "phormingochilus hati hati": "Borneo Purple Earth Tiger",
    "chilobrachys sp kaeng krachan": "Dark Earth Tiger",
    "nhandu chromatus": "Brazilian Red & White",
    "nhandu tripepii": "Brazilian Giant Blonde",
    "nhandu coloratovillosus": "Brazilian Black & White",
    "megaphobema robustum": "Colombian Giant Redleg",
    "megaphobema mesomelas": "Costa Rican Redleg",
    "sericopelma sp": "Golden Legged Birdeater",
    # Grammostola
    "grammostola pulchra": "Brazilian Black",
    "grammostola pulchripes": "Chaco Golden Knee",
    "grammostola rosea": "Chilean Rose Hair",
    "grammostola porteri": "Chilean Rose Hair",
    "grammostola quirogai": "Uruguayan Black Beauty",
    "grammostola actaeon": "Brazilian Red Rump",
    "grammostola iheringi": "Entre Rios",
    "grammostola grossa": "Brazilian Silver",
    # Brachypelma / Tliltocatl
    "brachypelma hamorii": "Mexican Red Knee",
    "brachypelma smithi": "Mexican Red Knee",
    "brachypelma emilia": "Mexican Red Leg",
    "brachypelma boehmei": "Mexican Fireleg",
    "brachypelma auratum": "Mexican Flame Knee",
    "brachypelma albiceps": "Mexican Golden Red Rump",
    "brachypelma klaasi": "Mexican Pink",
    "brachypelma baumgarteni": "Mexican Orange Beauty",
    "tliltocatl albopilosus": "Curly Hair",
    "tliltocatl vagans": "Mexican Red Rump",
    "tliltocatl kahlenbergi": "Kahlenberg's Red Rump",
    "tliltocatl verdezi": "Verdez Red Rump",
    "tliltocatl epicureanus": "Yucatan Rust Rump",
    "tliltocatl sabulosus": "Yucatan Rust Rump",
    # Aphonopelma
    "aphonopelma chalcodes": "Arizona Blonde",
    "aphonopelma seemanni": "Costa Rican Zebra",
    "aphonopelma hentzi": "Texas Brown",
    "aphonopelma johnnycashi": "Johnny Cash",
    "aphonopelma bicoloratum": "Mexican Bloodleg",
    # Poecilotheria
    "poecilotheria metallica": "Gooty Sapphire Ornamental",
    "poecilotheria regalis": "Indian Ornamental",
    "poecilotheria formosa": "Salem Ornamental",
    "poecilotheria fasciata": "Sri Lankan Ornamental",
    "poecilotheria striata": "Mysore Ornamental",
    "poecilotheria ornata": "Fringed Ornamental",
    "poecilotheria rufilata": "Redslate Ornamental",
    "poecilotheria subfusca": "Ivory Ornamental",
    "poecilotheria tigrinawesseli": "Wessel's Tiger Ornamental",
    "poecilotheria vittata": "Ghost Ornamental",
    # Old-world arboreal / baboons
    "psalmopoeus irminia": "Venezuelan Suntiger",
    "psalmopoeus cambridgei": "Trinidad Chevron",
    "psalmopoeus victori": "Darth Maul",
    "psalmopoeus reduncus": "Costa Rican Orangemouth",
    "psalmopoeus pulcher": "Panama Blonde",
    "tapinauchenius violaceus": "Purple Tree Spider",
    "caribena versicolor": "Antilles Pinktoe",
    "caribena laeta": "Puerto Rican Pinktoe",
    "avicularia avicularia": "Pinktoe",
    "avicularia purpurea": "Ecuadorian Purple Pinktoe",
    "ybyrapora diversipes": "Amazon Sapphire Pinktoe",
    "chromatopelma cyaneopubescens": "Greenbottle Blue",
    "pterinochilus murinus": "Orange Baboon Tarantula",
    "pterinochilus chordatus": "Kilimanjaro Mustard Baboon",
    "monocentropus balfouri": "Socotra Island Blue Baboon",
    "harpactira pulchripes": "Golden Blue Leg Baboon",
    "heteroscodra maculata": "Togo Starburst Baboon",
    "stromatopelma calceatum": "Featherleg Baboon",
    "ceratogyrus darlingi": "Rear Horned Baboon",
    "ceratogyrus marshalli": "Great Horned Baboon",
    "ceratogyrus brachycephalus": "Lesser Horned Baboon",
    "pelinobius muticus": "King Baboon",
    "hysterocrates gigas": "Cameroon Red Baboon",
    "eucratoscelus pachypus": "Stout Leg Baboon",
    "augacephalus ezendami": "Mozambique Golden Baboon",
    "idiothele mira": "Blue Foot Baboon",
    # Asian
    "cyriopagopus lividus": "Cobalt Blue",
    "cyriopagopus sp": "Vietnam Blue",
    "cyriopagopus hainanus": "Chinese Fawn",
    "omothymus violaceopes": "Singapore Blue",
    "omothymus schioedtei": "Malaysian Earth Tiger",
    "chilobrachys fimbriatus": "Indian Violet",
    "chilobrachys natanicharum": "Electric Blue",
    "chilobrachys huahini": "Asian Fawn",
    "lampropelma nigerrimum": "Sangihe Black",
    "phormingochilus everetti": "Bornean Orange Fringed",
    "birupes simoroxigorum": "Borneo Neon Blue Leg",
    # dwarfs & others
    "cyriocosmus elegans": "Trinidad Dwarf Tiger",
    "hapalopus sp": "Pumpkin Patch",
    "dolichothele diamantinensis": "Brazilian Blue Dwarf Beauty",
    "kochiana brunnipes": "Dwarf Pink Leg",
    "neoholothele incei": "Trinidad Olive",
    "homoeomma chilensis": "Chilean Flame",
    "euathlus sp": "Chilean Flame Dwarf",
    "phormictopus sp": "Dominican Purple",
    "phormictopus auratus": "Cuban Bronze",
    "bumba cabocla": "Brazilian Red Head",
    "davus pentaloris": "Guatemalan Tiger Rump",
    "cyclosternum schmardae": "Costa Rican Tiger Rump",
    "thrixopelma ockerti": "Peruvian Flame",
    "pamphobeteus sp": "Purple Bloom Birdeater",
    "ephebopus cyanognathus": "Blue Fang",
    "ephebopus murinus": "Skeleton Tarantula",
    "vitalius paranaensis": "Brazilian Pointy Tail",
    # more common traders
    "acanthoscurria brocklehursti": "Brazilian Black & White",
    "aphonopelma moderatum": "Rio Grande Gold",
    "avicularia juruensis": "Yellow-banded Pinktoe",
    "brachypelma vagans": "Mexican Red Rump",
    "caribena versicolor": "Antilles Pinktoe",
    "ceratogyrus attonitifer": "Straighthorned Baboon",
    "chilobrachys dyscolus": "Vietnam Blue",
    "cyriopagopus schmidti": "Chinese Golden Earth Tiger",
    "davus fasciatus": "Costa Rican Tigerrump",
    "dolichothele exilis": "Colombian Dwarf",
    "encyocratella olivacea": "Tanzanian Black & Olive",
    "grammostola actaeon": "Brazilian Red Rump",
    "hapalotremus martinorum": "Andean Cloud Forest",
    "harpactira namaquensis": "Common Golden Baboon",
    "heterothele gabonensis": "Gabon Blue Dwarf",
    "kochiana brunnipes": "Dwarf Pink Leg",
    "lampropelma violaceopes": "Singapore Blue",
    "neoholothele incei": "Trinidad Olive",
    "nhandu carapoensis": "Brazilian Red",
    "orphnaecus sp": "Philippine Orange",
    "pamphobeteus sp": "Purple Bloom Birdeater",
    "phlogiellus sp": "Asian Dwarf",
    "phormictopus cancerides": "Haitian Brown",
    "poecilotheria tigrinawesseli": "Wessel's Tiger Ornamental",
    "psalmopoeus reduncus": "Costa Rican Orangemouth",
    "pterinopelma sazimai": "Brazilian Blue",
    "sericopelma angustum": "Panama Blonde",
    "tapinauchenius cupreus": "Ecuadorian Copper",
    "tapinauchenius rasti": "Caribbean Diamond Tree Spider",
    "thrixopelma pruriens": "Peruvian Green Velvet",
    "tliltocatl sabulosum": "Yucatan Rust Rump",
    "xenesthis sp": "Colombian Bloom",
    "ybyrapora sooretama": "Sooretama Pinktoe",
    # scorpions / other inverts
    "pandinus imperator": "Emperor Scorpion",
    "heterometrus spinifer": "Asian Forest Scorpion",
    "hadrurus arizonensis": "Desert Hairy Scorpion",
    "hottentotta hottentotta": "African Fattail",
    "androctonus australis": "Yellow Fattail",
    "damon diadema": "Tanzanian Giant Whip Spider",
    "mastigoproctus giganteus": "Giant Vinegaroon",
    "gromphadorhina portentosa": "Madagascar Hissing Roach",
    "scolopendra dehaani": "Vietnamese Centipede",
    "scolopendra subspinipes": "Vietnamese Centipede",
    "archispirostreptus gigas": "Giant African Millipede",
    "cubaris sp": "Rubber Ducky Isopod",
    "armadillidium maculatum": "Zebra Isopod",
    "porcellio laevis": "Dairy Cow Isopod",
    "porcellio scaber": "Common Rough Woodlouse",
    # --- Deep-research pass (verified vs dealer sites / Wikipedia / iNaturalist).
    # Keys include vendor misspellings on purpose, so the name attaches to the
    # exact species_key present in the DB. Only established names accepted.
    "hogna miami": "Miami Wolf Spider",
    "linothele megatheloides": "Colombian Funnel-web",
    "linothele megathelodies": "Colombian Funnel-web",
    "typhochlaena seladonia": "Brazilian Jewel",
    "brachypelma auruatum": "Mexican Flame Knee",
    "chilobrachys natanicharim": "Electric Blue",
    "pamphobeteus tigris": "Ecuadorian Black Birdeater",
    "brachypelma boehemi": "Mexican Fireleg",
    "brachypelma boemei": "Mexican Fireleg",
    "catumiri parvum": "Uruguayan Copper Dwarf",
    "chaetopelma karlamani": "Cyprus Tarantula",
    "chaetopelma oliviceum": "Middle East Black",
    "ephebopus cyangnathus": "Blue Fang",
    "ephebopus cyanognauthus": "Blue Fang",
    "hapalotremus hananqheswa": "High Valley Blue",
    "hapalotremus marcapata": "Peruvian Highland Blue",
    "haplocosmia himilayana": "Himalayan Earth Tiger",
    "harpactira namequensis": "Bronze Baboon",
    "harpactira overdijik": "Lesser Baboon",
    "phidippus ardens": "Desert Red Jumping Spider",
    "phormictopus cautus": "Cuban Purple",
    "scolopendra longipes": "Haitian Giant Centipede",
    "selenobrachys phillipinus": "Philippine Tangerine",
    "selenocosmia javanensis": "Javan Yellowknee",
    "androctonus amourexi": "Arabian Fat-Tailed Scorpion",
    "armadillidium klugi": "Clown Isopod",
    "asbolus verrucosus": "Blue Death Feigning Beetle",
    "barylestes saaristoi": "Ghost Huntsman",
    "blaberus fusca": "Dusky Cave Roach",
    "buthus elmoutaukili": "Moroccan Tricolor Scorpion",
    "centruroides vittatus": "Striped Bark Scorpion",
    "ceratogyrus meridianalis": "Zimbabwe Grey Baboon",
    "chilobrachys kaeng": "Dark Earth Tiger",
    "chilobrachys siam": "Siam Orange",
    "crassicrus tochtil": "Los Tuxtlas Cinnamon",
    "cyclocosmia ricketti": "Chinese Hourglass",
    "dolomedes albineus": "Whitebanded Fishing Spider",
    "dolomedes tenebrosus": "Dark Fishing Spider",
    "floridobolus floydi": "Floyd's Sandhill Millipede",
    "gymnetis thula": "Harlequin Flower Beetle",
    "hemiblabera tenebricosa": "Horseshoe Crab Roach",
    "heteroctonus junceus": "Cuban Red Scorpion",
    "heteropoda boiei": "Lichen Huntsman",
    "heteropoda javana": "Javan Huntsman",
    "heteropoda venatoria": "Huntsman Spider",
    "hogna osceola": "Pine Giant Wolf Spider",
    "hottentotta sousai": "Alligator Back Scorpion",
    "lasiodora benedeni": "Brazilian Red Birdeater",
    "lasiodrides striatus": "Peruvian Orange-Stripe",
    "leirurus quinquestriatus": "Deathstalker",
    "lucihormetica verrucosa": "Warty Glowspot Roach",
    "megaphasma dentricus": "Giant Walkingstick",
    "mezium affine": "Shiny Spider Beetle",
    "omothymus violacepes": "Singapore Blue",
    "pamphobeteus mascara": "Mascara Giant Birdeater",
    "pamphobeteus ultramarinus": "Ecuadorian Birdeater",
    "paruroctonus utahensis": "Eastern Sand Scorpion",
    "phiddipus morpheus": "Dream Jumping Spider",
    "phormigochilus arboricola": "Borneo Black",
    "phrynus whitei": "Tailless Whip Scorpion",
    "porcellio bolivari": "Skeleton Isopod",
    "psalmopoeus langenbucheri": "Venezuelan Chevron",
    "psalmopoeus rednucus": "Costa Rican Orange Mouth",
    "tapinauchenius casanare": "Casanare Tree Spider",
    "tenodera sinensis": "Chinese Mantis",
    "trichorhina tormentosa": "Dwarf White Isopod",
    "uroplectes chubbi": "Chubb's Thicktail Scorpion",
    "xenobolus carnifex": "Red Spined Millipede",
    # --- Web-scan pass 2 (verified vs dealer sites / Wikipedia / iNaturalist /
    # BugGuide). Keys include vendor genus-typos on purpose so they attach to the
    # exact key in the DB. Only established names accepted.
    "hogna carolinensis": "Carolina Wolf Spider",
    "hogna lenta": "Field Wolf Spider",
    "tlitocatl schroederi": "Mexican Black Velvet",
    "tlitocatl vagans": "Mexican Red Rump",
    "tlitocatl albopilosum": "Curly Hair",
    "devicarina guidonae": "Orange Blaze Dwarf",
    "grammostola rose": "Chilean Rose Hair",
    "phlogiellus johnreylazoi": "Palawan Blue",
    "teruelius grandidieri": "Madagascan Black Scorpion",
    "amazonius burgessi": "Ghost Tree Spider",
    "androctonus aeneas": "Aeneas Fat-tailed Scorpion",
    "anqasha picta": "Anqasha Tiger Rump",
    "edentistoma octosulcatum": "Millipede-Eating Centipede",
    "pamphobeteus ecclesiasticus": "Ecuadorian Olive Grey Tree Spider",
    "paruroctonus gracilior": "Chihuahuan Slendertailed Scorpion",
    "anasaitis canosa": "Twin-flagged Jumping Spider",
    "lyssomanes viridis": "Magnolia Green Jumper",
    "naphrys pulex": "Flea Jumper",
    "misumena vatia": "Goldenrod Crab Spider",
    # --- Web-scan pass 3 ---
    "latrodectus mactans": "Southern Black Widow",
    "haplopelma hainanum": "Chinese Black Earth Tiger",
    "scorpiops kautii": "Thai Flat Rock Scorpion",
    "scorpiops phatoensis": "Thailand Flat Rock Scorpion",
    "tapinauchenius seladonia": "Brazilian Jewel",
    "hapalopus sp colombia": "Pumpkin Patch",
    "davus fasciatus": "Costa Rican Tiger Rump",
    "phormingochilus everetti": "Sarawak Red Tiger",
    # --- Standardization pass (curated over messy vendor-harvested text) ---
    "amazonius germani": "Orange Tree Spider",
    "amazonius burgessi": "Ghost Tree Spider",
    "amazonius sp ecuador": "Napo Bronze Tree Spider",
    "blaberus craniifer": "Death Head Roach",
    "blaberus discoidalis": "Discoid Roach",
    "arilus cristatus": "Wheel Bug",
    "centruroides sculpturatus": "Arizona Bark Scorpion",
    "chicobolus spinigerus": "Florida Ivory Millipede",
    "trigoniulus coralinus": "Rusty Millipede",
    "chromatopelma cyanapubescense": "Greenbottle Blue",
    "dolomedes triton": "Six-spotted Fishing Spider",
    "dolomedes okefinokensis": "Okefenokee Fishing Spider",
    "kukulcania hibernalis": "Southern House Spider",
    "phyllocrania paradoxa": "Ghost Mantis",
    "therea olegrandjeani": "Question Mark Cockroach",
    "nauphoeta cinerea": "Lobster Roach",
    "platymeris rhadamanthus": "Red Spot Assassin Bug",
    "gandanameno enchinata": "Spiny Velvet Spider",
    "acanthophrynus coronatus": "Mexican Giant Whip Spider",
    "heteropoda venatoria": "Huntsman Spider",
    "heteropoda davidbowie": "David Bowie Huntsman",
    "lasiocyano sazimai": "Brazilian Blue",
    "melopoeus albostriatus": "Thai Zebra Leg",
    "melopeus lividus": "Cobalt Blue",
    "citharacanthus cyaneus": "Blue Masked Tarantula",
    "sicarius gracilis": "Ecuadorian Six-Eyed Sand Spider",
    "aphonopelma anax": "Texas Tan",
    "aphonopelma steindachneri": "Steindachner's Ebony",
    "eupalaestrus weijenberghi": "White Collared Tarantula",
    "eupelaestrus campestratus": "Pink Zebra Beauty",
    "euphrictus squamosus": "Hairy Baboon",
    "porcellionides pruinosus": "Powder Blue Isopod",
    "porcellio dilatatus": "Giant Canyon Isopod",
    "armadillidium vulgare": "Common Pill Woodlouse",
    "armadillidium klugii": "Clown Isopod",
    "trichorhina tomentosa": "Dwarf White Isopod",
    "cubaris murina": "Little Sea Isopod",
    "phidippus regius": "Regal Jumping Spider",
    "avicularia braunshauseni": "Goliath Pinktoe",
    # vendor spelling variants of already-curated species (attach to exact DB key)
    "tliltocatl albopilosum": "Curly Hair",
    "aphonopelma chalchodes": "Arizona Blonde",
    "chromatopelma cyaneopubescens": "Greenbottle Blue",
    "omothymus violaceops": "Singapore Blue",
    "grammostola quiroguay": "Uruguayan Black Beauty",
    "grammostola sp pulchra": "Brazilian Black",
    "lasiodora kluggi": "Bahia Scarlet Birdeater",
    "poecilotheria tigrinawesselli": "Wessel's Tiger Ornamental",
    "melopoeus lividis": "Cobalt Blue",
    "melopoeus lividus": "Cobalt Blue",
    "phiddipus regius": "Regal Jumping Spider",
    "theraposa apophysis": "Pinkfoot Goliath Birdeater",
    "tlitocatl khalenbergi": "Kahlenberg's Red Rump",
    "buthus elmoutaouakili": "Moroccan Tricolor Scorpion",
    "phrynus marginemaculatus": "Tailless Whip Scorpion",
}

# Vendor marketing / placeholder tokens that mean the "common name" harvested from
# a product title is junk, not a name. Matched as whole words (lowercased).
_JUNK_WORDS = {
    "rare", "beautiful", "gorgeous", "stunning", "beginner", "unsexed",
    "subadult", "subad", "juvenile", "aka", "ex", "formerly", "formally",
    "contrast", "pda", "female", "male", "unsexed-", "sale", "wysiwyg",
    "captive", "cb", "wc", "premium", "pair", "trio", "group", "sp",
}
# Hard junk: if any of these appears anywhere, the string is a scientific
# cross-reference or a sentence, never a common name — discard the whole thing.
_HARD_PHRASES = (
    "hard to find", "coming soon", "new to usa", "much like", "related to",
    "please read", "read description", "ex.", "ex:", "ex ", "aka ", "was ",
    "formerly", "formally", " sp ", "sp.",
)
# Edge junk: marketing / trade-condition tokens to peel off the ENDS of a name,
# leaving the real name in the middle ("SEXED PAIR Regal Jumping Spider").
_EDGE_JUNK = {
    "rare", "beautiful", "gorgeous", "stunning", "beginner", "unsexed", "sexed",
    "subadult", "subad", "juvenile", "adult", "contrast", "pda", "female",
    "male", "males", "females", "sale", "wysiwyg", "captive", "bred", "cb",
    "wc", "premium", "pair", "trio", "group", "sp", "spp", "species", "unsexed-",
    "and", "the", "a", "very", "new", "!", "-", "&",
}
# Bare geographic words: a name that is ONLY this is a locality tag, not a name.
_GEO_ONLY = {
    "colombia", "colombian", "ecuador", "peru", "brazil", "vietnam", "thailand",
    "mexico", "india", "china", "africa", "usa", "north", "south",
}


def _norm(s: str) -> str:
    return " ".join((s or "").lower().replace(".", "").replace(",", "").split())


def _smart_title(name: str) -> str:
    """Title-case only the all-lowercase words, so existing caps, apostrophes,
    and proper nouns (McConnell, David Bowie, St.) survive untouched."""
    out = []
    for w in name.split():
        out.append(w.capitalize() if w.islower() else w)
    return " ".join(out)


def _clean_candidate(name: str, key: str) -> str:
    """Turn one harvested vendor string into a clean common name, or '' if it
    isn't one. Peels marketing tokens off the edges, rejects sentences,
    scientific cross-references, duplicated binomials, and bare localities."""
    if not name:
        return ""
    n = name.strip()
    if any(ch.isdigit() for ch in n):
        return ""
    low = " " + n.lower().replace(".", " . ") + " "
    if any(p in low for p in _HARD_PHRASES):
        return ""
    toks = n.replace("/", " ").split()
    # peel edge-junk / punctuation off both ends
    while toks and toks[0].strip("!-&,").lower() in _EDGE_JUNK | {""}:
        toks.pop(0)
    while toks and toks[-1].strip("!-&,").lower() in _EDGE_JUNK | {""}:
        toks.pop()
    if not toks:
        return ""
    core = " ".join(toks).strip("!-&,. ")
    if not core or any(ch.isdigit() for ch in core):
        return ""
    if _norm(core) == _norm(key):        # duplicated binomial, e.g. "Blaberus craniifer"
        return ""
    if _norm(core) in _GEO_ONLY:         # a lone "Colombia" / "Ecuador"
        return ""
    return _smart_title(core)


def _descriptor(key: str) -> str:
    toks = (key or "").split()
    if len(toks) >= 3 and toks[1] == "sp":
        return " ".join(toks[2:]).title()
    return ""


def pick_common(key: str, candidates) -> str:
    """Best common name for a species key given ALL harvested candidate strings.
    Priority: curated map → best clean harvested name → sp. trade descriptor → ''.
    Among clean candidates, prefer a proper 2–4 word name over one-word tags."""
    curated = COMMON_NAMES.get(key)
    if curated:
        return curated
    if isinstance(candidates, str):
        candidates = [candidates]
    cleaned = [c for c in (_clean_candidate(x, key) for x in (candidates or [])) if c]
    if cleaned:
        def score(name):
            wc = len(name.split())
            return (1 if 2 <= wc <= 4 else 0, -abs(wc - 2), len(name))
        return sorted(cleaned, key=score, reverse=True)[0]
    return _descriptor(key)


def best_common(key: str, db_common: str = "") -> str:
    """Back-compatible single-value entry point; see pick_common."""
    return pick_common(key, db_common)
