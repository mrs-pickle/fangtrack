"""
Livestock gate: decide whether a product title is a LIVE INVERTEBRATE listing.

Only living inverts (tarantulas, other arachnids, myriapods, isopods, insects)
belong in the tracker. Everything else — supplies, enclosures, decor, botanicals
(leaf litter / pods / wood), minerals, plants, apparel, feeder cultures, and
vertebrates — must be dropped so it can never pollute deals/rarity scoring.

The hard part: supply names are Title-Case two-word phrases ("Frozen Rodents",
"Plant Pots", "Fine Fir Bark") that look just like a Genus-species binomial, and
some deny words collide with real common names ("Green **Bottle** Blue" = GBB,
"**Rock** Scorpion", "**Powder** Blue" isopod). So we use a TWO-TIER deny:

  STRONG_DENY  — apparel / merch / feeders / vertebrates / consumables.
                 These never appear in a live-animal listing, so they win even
                 when a genus is also present ("aphonopelma classic tee").
  WEAK_DENY    — containers / substrate / decor / botanicals. These can appear
                 inside a real listing's blurb, so they only reject when there
                 is NO genus and NO taxon keyword ("Habitat 24oz" → drop, but
                 "Eresus … 🛖Habitat" → keep).

Accept order:
  1. STRONG_DENY hit → reject.
  2. deny genus (plant / shell / vertebrate) → reject.
  3. known invert GENUS token, or specific taxon keyword → accept.
  4. WEAK_DENY hit → reject.
  5. clean lowercase binomial "Genus species" / "Genus sp." → accept.
  6. else reject.
"""
from __future__ import annotations

import re

# ── STRONG deny — always wins, even over a genus match ───────────────────────
STRONG_DENY = [
    # apparel
    "shirt", "t-shirt", "tshirt", "tee", "hoodie", "sweatshirt", "crewneck",
    "jersey", "sleeve", "tank top", "swim trunks", "clog", "clogs", "sock",
    "socks", "hat", "hats", "beanie", "unisex", "men's", "women's", "kid's",
    "youth", "apparel", "foam clogs", "eva foam", "swimsuit",
    # merch
    "sticker", "pin", "pins", "magnet", "poster", "art print", "prints",
    "photography", "keychain", "key chain", "lanyard", "luggage tag",
    "necklace", "oval necklace", "mug", "tumbler", "water bottle", "tote",
    "backpack", "journal", "blanket", "fleece", "pillow", "wine glass",
    "postcard", "postcards", "vinyl", "spooky sweet", "merch", "obsession tee",
    "keychain", "3d print", "jacket", "wrapping paper", "gift wrap", "sign",
    "tattoo", "coffin", "crib", "cribs",
    # home goods / novelty merch (win over the taxon keyword in the blurb).
    # NB: "curtain"/"mask" are NOT denied bare — they collide with real names
    # (Linothele "curtain-web spider", Pamphobeteus "Crimson Mask"); deny the
    # merch phrase instead.
    "towel", "towels", "shower curtain", "slipper", "slippers", "face mask",
    "cube", "cubes", "lunch bag", "tool bag", "tote bag", "gift bag", "brick",
    "bricks", "building block", "block set", "banquet", "puzzle", "plush",
    "ornament", "coaster", "coasters", "mousepad", "mouse pad", "phone case",
    "trading card", "mon card", "canvas print", "wall art", "coloring book",
    "apron", "cutting board", "notebook", "playing card",
    # husbandry substrate/bedding — beats the isopod/roach taxon keyword
    "substrate", "bedding", "faunaboost",
    # feeders / feeder cultures (a feeders module is planned separately)
    "feeder", "feeders", "feeding", "cricket", "crickets", "mealworm",
    "superworm", "waxworm", "hornworm", "dubia", "red runner", "fruit fly",
    "drosophila", "springtail", "bloodworm", "herring", "fish food",
    "gutload", "tadpole", "roach crunch", "isopod crunch", "crunchies",
    # feeder roaches sold by the count (Josh's Frogs &c.) — NOT the pet roach
    # genera (Gromphadorhina/Blaberus keep passing on their genus token).
    "orange head roach", "discoid roach", "banana roach", "lobster roach",
    "turkistan roach", "ivory head roach", "green banana roach",
    # consumables / supplements / media / services
    "fertilizer", "nutrient", "additive", "supplement", "supplementation",
    "calcium", "vitamin", "mineral booster", "mineral bath", "gutload",
    "cleaner", "gift card", "gift certificate", "mystery box", "mystery",
    "grab bag", "subscription",
    "grubsub", "donation", "supporter", "add-on", "buddy add", "delivery",
    "shipping box", "shipping", "personal insult", "custom order", "dewayne",
    "shell", "seashell", "abalone",
    "diet", "invertebrate diet", "pod power",
    # container / decor words that only ever appear on supplies (never the
    # animal itself), even when the blurb mentions "tarantula"/"isopod".
    # (These win over the taxon keyword, and include plural forms.)
    "habitat", "studio", "flats", "skull", "skull hide",
    "water dish", "dish", "dishes", "bowl", "bowls", "disposable",
    "kit", "kits", "cage", "cages", "hide", "hides",
    "vial", "vials", "deli cup", "enclosure", "enclosures", "terrarium",
    "vivarium", "water bowl",
    # vertebrates
    "gecko", "snake", "python", "boa constrictor", "sand boa", "rosy boa",
    "red-tail boa", "red tail boa", "lizard", "skink", "monitor",
    "chameleon", "iguana", "bearded dragon", "frog", "froglet", "toad",
    "salamander", "newt", "axolotl", "turtle", "tortoise", "mouse", "mice",
    "rat", "rodent", "hamster", "hedgehog", "viper", "cobra", "rattlesnake",
    "reptile", "amphibian", "whiptail", "anole", "cherry head", "mata mata",
    "milk frog", "dart frog", "tree frog", "trachycephalus", "dendrobates",
    # plants / minerals / decor / mounts — plant-selling vendors (e.g. Pacific
    # Northwest) list these alongside inverts; they are not livestock.
    "cactus", "cacti", "succulent", "air plant", "airplant", "tillandsia",
    "echinopsis", "notocactus", "parodia", "ferocactus", "gymnocalycium",
    "mammillaria", "opuntia", "lithops", "amethyst", "geode", "quartz",
    "mineral cluster", "amethyst cluster", "mineral", "decal", "cling",
    "ceramic", "saliva",
    # brand names that only appear on gear / supplies
    "exo terra", "zoo med", "zoomed", "the bio dude", "bio dude", "lugarti",
    "josh's frogs", "joshs frogs", "canned",
]

# ── WEAK deny — only when there is no genus / taxon signal ────────────────────
WEAK_DENY = [
    # containers & husbandry gear
    "vial", "vials", "deli cup", "deli round", "container", "keeper", "keepers",
    "enclosure", "terrarium", "vivarium", "cage",
    "acryl", "acrylic", "hasp", "lid", "mesh", "vent", "screen", "kit", "crib",
    "cribs", "setup", "tongs", "tweezers", "syringe", "dropper", "mister",
    "sprayer", "shovel", "scoop", "squeeze bottle", "critter", "case",
    "foam insert", "insert", "barrier", "grow-out", "snap cup", "cup", "tank",
    # substrate / botanicals / decor
    "substrate", "soil", "coco", "peat", "vermiculite", "sphagnum", "moss",
    "perlite", "pumice", "leca", "clay", "hydroton", "hydroball", "drainage",
    "cork", "bark", "wood", "excelsior", "manzanita", "ironwood", "driftwood",
    "hardscape", "background", "panel", "putty", "leaf litter", "litter",
    "pod", "pods", "cone", "cones", "seed pod", "botanical", "husk",
    "hide", "cave", "replica", "water dish", "rock dish", "dish",
    "bowl", "decor", "faux", "vine", "plant pot", "pots", "gravel",
    "fern", "fernwood", "powder", "bath kit",
    "thermometer", "hygrometer", "heat mat", "heat lamp", "heat pack",
    "cool pack", "cryopak", "uvb", "bulb", "lamp", "waffle", "fabric",
    "monkey ladder", "stemless",
]

# ── Genera that would otherwise pass but are NOT live inverts ────────────────
DENY_GENERA = {
    # plants
    "tillandsia", "tilandsia", "ionantha", "xerographica", "velickiana",
    "albertiana", "aechmea", "guzmania", "vriesea", "neoregelia", "billbergia",
    "dyckia", "cryptanthus", "nidularium", "pothos", "philodendron", "begonia",
    "wallisia", "goudaea", "mammillaria", "quercus", "acer", "coccoloba",
    "monstera", "syngonium", "anubias",
    # seashell genera sold as decor
    "bursa", "strombus", "cypraea", "conus", "murex", "turbo", "nassarius",
    "trochus", "cerithium", "oliva", "terebra", "lambis", "cassis", "melo",
    "charonia", "haliotis", "nautilus", "architectonica", "tonna", "harpa",
    "cymbiola", "voluta", "mitra", "natica", "polinices", "busycon",
    # vertebrate genera
    "hemitheconyx", "eublepharis", "correlophus", "rhacodactylus", "python",
    "morelia", "pantherophis", "lampropeltis", "crotalus", "bitis", "naja",
    "atheris", "trimeresurus", "agkistrodon", "heloderma", "pogona", "anolis",
    "cnemidophorus", "chelonoidis", "chelus", "acanthosaura", "calluella",
    "dendrobates", "eurydactylodes", "drymarchon", "unicolor",
}

# ── Known invert genera (curated from the live catalog) ──────────────────────
GENUS_SET = {
    # Added 2026-07-17 — valid genera/subfamilies that were leaking as "unknown genus"
    # junk keys (mostly from underground_reptiles selling undescribed sp. at subfamily rank).
    "acanthopelma", "phlogius", "brachionopus", "haploclastus", "pandinopsis",
    "anuroctonus", "aegaeobuthus", "janalychas", "opisthacanthus", "platythomisus",
    "theraphosinae", "selenocosmiinae", "theraphosidae", "thrigmopoeinae",
    "ornithoctoninae", "selenocosmia", "orphnaecus", "phlogiellus",
    # Theraphosidae (tarantulas)
    "acanthoscurria", "aphonopelma", "avicularia", "birupes", "bistriopelma",
    "bonnetina", "brachypelma", "bumba", "caribena", "catumiri", "ceratogyrus",
    "chaetopelma", "chilobrachys", "chromatopelma", "citharacanthus",
    "clavopelma", "coremiocnemis", "crassicrus", "cotzetlana", "cyclosternum",
    "cyriocosmus", "cyriopagopus", "davus", "dolichothele", "encyocratella",
    "ephebopus", "euathlus", "eucratoscelus", "eupalaestrus", "euthycaelus",
    "ewok", "fufius", "grammostola", "guyruita", "hapalopus", "hapalotremus",
    "haplocosmia", "haplopelma", "harmonicon", "harpactira", "harpactirella",
    "heteroscodra", "heterothele", "holothele", "homoeomma", "hysterocrates",
    "idiothele", "iridopelma", "ischnocolus", "kochiana", "lampropelma",
    "lasiocyano", "lasiodora", "lasiodorides", "linothele", "lyrognathus",
    "megaphobema", "melopoeus", "monocentropus", "neischnocolus",
    "neoholothele", "nhandu", "omothymus", "ornithoctoninae", "ornithoctonus",
    "orphnaecus", "pamphobeteus", "pelinobius", "phormictopus",
    "phormingochilus", "phrixotrichus", "piloctenus", "plesiopelma",
    "poecilotheria", "psalmopoeus", "psednocnemis", "pseudhapalopus",
    "pseudoclamoris", "pterinochilus", "pterinopelma", "sahydroaraneus",
    "selenobrachys", "selenocosmia", "sericopelma", "spinosatibiapalpus",
    "stromatopelma", "taksinus", "tapinauchenius", "theraphosa", "thrigmopoeus",
    "thrixopelma", "tliltocatl", "typhochlaena", "vitalius", "xenesthis",
    "ybyrapora", "augacephalus", "aspinochilus", "chilocosmia", "dugesiella",
    "hemirrhagus", "holconia", "magnacrus", "orientothele", "pseudohapalopus",
    "sahastata", "thalerommata", "trichopelma", "acanthogonatus", "cardiopelma",
    "cyclocosmia", "bothriocyrtum", "ummidia", "isaboroa", "psophocleis",
    # other spiders
    "cupiennius", "cyclosa", "deinopis", "dolomedes", "gandanameno",
    "gnathopalystes", "heteropoda", "hogna", "kukulcania", "leucorchestris",
    "loxosceles", "latrodectus", "macrothele", "peucetia", "phoneutria",
    "phidippus", "rhitymna", "scytodes", "selenops", "sicarius",
    "sphodros", "stegodyphus", "thelcticopis", "tigrosa", "ischnothele",
    "euagrus", "diplura", "cerbalus", "barylestes", "calommata", "liphistius",
    "qiongthela", "vinathela", "macroctenus", "hyllus", "vonones", "psechrus",
    "eresus", "kukulcania", "sphodros", "cheiracanthium", "argiope", "nephila",
    # scorpions
    "androctonus", "babycurus", "buthacus", "butheolus", "buthus", "centruroides",
    "chaerilus", "chersonesometrus", "compsobuthus", "diplocentrus", "euscorpius",
    "gigantometrus", "hadogenes", "hadrurus", "heterometrus", "heteroctonus",
    "heteroctenus", "hoffmannius", "hottentotta", "javanimetrus", "leiurus",
    "leirurus", "liocheles", "lychas", "nebo", "oliverius", "orthochirus",
    "pandinurus", "pandinus", "parabuthus", "paravaejovis", "paruroctonus",
    "pseudolychas", "pseudouroctonus", "scorpio", "scorpiops", "smeringurus",
    "teruelius", "tityopsis", "tityus", "uroplectes", "vaejovis", "butheoloides",
    "isometrus", "grosphus", "opistophthalmus", "butheolus", "gint",
    # amblypygi / uropygi / solifugae
    "damon", "phrynus", "paraphrynus", "charinus", "heterophrynus",
    "mastigoproctus", "typopeltis", "thelyphonus", "paragaleodes", "galeodes",
    # myriapods
    "scolopendra", "ethmostigmus", "rhysida", "otostigmus", "cormocephalus",
    "scutigera", "thereuopoda", "alipes", "anadenobolus", "archispirostreptus",
    "chicobolus", "narceus", "orthoporus", "orthroporus", "trigoniulus",
    "coromus", "floridobolus", "spirobolus", "acladocricus", "centrobolus",
    "leptogoniulus", "narceous", "treptogonostreptus", "pelmatojulus",
    "aphistogoniulus", "tonkinbolus", "spirobolellus", "desmoxytes",
    "xenobolus", "epibolus", "chicobulus", "spirostreptus",
    # isopods
    "armadillidium", "cubaris", "porcellio", "porcellionides", "trichorhina",
    "armadillo", "cristarmadillidium", "merulanella", "nesodillo", "venezillo",
    "spherillo", "hemilepistus",
    # roaches / mantids / beetles / insects kept as pets
    "gromphadorhina", "blaberus", "eublaberus", "pycnoscelus", "therea",
    "lucihormetica", "hemiblabera", "elliptorhina", "panchlora", "macropanesthia",
    "hymenopus", "pseudocreobotra", "tenodera", "creobroter", "deroplatys",
    "asbolus", "eleodes", "gymnetis", "mezium", "phloeodes", "chalcosoma",
    "megaphasma", "megasoma", "dynastes", "psytalla", "platymeris",
    "stenopelmatus", "romalea", "megaphasma",
    # velvet worms
    "epiperipatus", "principapillatus", "peripatus",
    # frequent vendor misspellings (so real animals still canonicalize)
    "harpacta", "harpactra", "aviculaira", "aviculria", "phormigochilus",
    "melapoeus", "tapiniauchenius", "phiddipus", "dolichotherle",
    "psuedoclamoris", "seleobrachys", "lasiodrides", "eupaleastrus",
    "gromphadorina", "phyrnus", "chilobrachy", "pheiddipus", "poecilotheia",
    "grammastola", "brachypelmma", "tliltocatal", "acanthoscuria",
    # real invert genera surfaced by the Vendors QA sweep (were missing)
    "acanthophrynus", "alienostreptus", "amazonius", "anasaitis", "anqasha",
    "antikuna", "barylestis", "cyrtopholis", "devicarina", "edentistoma",
    "gigathele", "hadruroides", "hemiscolopendra", "luthela", "lyssomanes",
    "metaphidippus", "misumena", "myrmekiaphila", "naphrys", "nauphoeta",
    "pandinoides", "phlogiellus", "psyttala", "scolopocryptops", "stahnkeus",
    "superstitionia", "urupelma", "vacrothele", "lasiocyano", "melopoeus",
    "kukulcania", "tigrosa", "selenops", "arilus", "nebo", "hapalotremus",
    # more frequent vendor misspellings of known genera
    "ceratogryus", "cyriopagapus", "melopeus", "pelinobus", "theraposa",
    "tlitocatl", "eupelaestrus", "lasiocyaneo", "cyriopagapous", "psytalla",
}

# Specific taxon keywords (catch common-name-only real listings).
TAXON_KEYWORDS = [
    "tarantula", "scorpion", "centipede", "millipede", "isopod", "vinegaroon",
    "amblypygi", "amblypygid", "whip spider", "whip scorpion", "tailless whip",
    "solifug", "sun spider", "camel spider", "harvestman", "opiliones",
    "velvet worm", "velvet spider", "trapdoor", "funnel-web", "funnel web",
    "curtain web", "purseweb", "huntsman", "fishing spider", "wolf spider",
    "jumping spider", "orb weaver", "orbweaver", "widow", "recluse",
    "assassin bug", "wheel bug", "praying mantis", "flower mantis",
    "ghost mantis", "hissing", "baboon", "birdeater", "bird eater",
    "birdeating", "pink toe", "pinktoe", "earth tiger", "tiger rump",
    "tigerrump", "woodlouse", "pillbug", "sowbug", "pill millipede",
    "roach", "cockroach", "beetle", "mantis",
]


def _mk_re(words):
    # Trailing "s?" so a singular deny term ("frog") also catches its plural
    # ("frogs") — otherwise \bfrog\b misses "milk frogs" and a vertebrate slips
    # through onto the binomial fallback.
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")s?\b")


_STRONG_RE = _mk_re(STRONG_DENY)
_WEAK_RE = _mk_re(WEAK_DENY)

# Art prints titled with a photo dimension ("Print 5X7 of <species>…") name a real
# genus, so they'd otherwise pass the genus-allow. Deny "print" next to an NxN size.
_ART_PRINT_RE = re.compile(
    r"\bprint\b.{0,15}\b\d{1,2}\s*[x×]\s*\d{1,2}\b|\b\d{1,2}\s*[x×]\s*\d{1,2}\b.{0,15}\bprint\b",
    re.I)
# Bulk feeder pack: a live PET is never priced "(25 count)" / "50 ct" / "pack of
# 100". Used to drop feeder insects (roaches/worms) that otherwise pass on a taxon
# keyword like "roach" — but only when no real invert GENUS is present, so a
# genuine "Grammostola … 10 sling pack" stays livestock.
_FEEDER_PACK_RE = re.compile(r"\b\d{1,4}\s*(?:count|ct|pcs|pieces)\b|\bpack\s*of\s*\d{1,4}\b", re.I)
_LOWER_BINOMIAL = re.compile(r"\b([A-Z][a-z]{5,})\s+([a-z]{3,})\b")
_GENUS_SP = re.compile(r"\b([A-Z][a-z]{4,})\s+(?:sp|cf|aff)\b", re.I)
_LEAD_QUALIFIER = re.compile(
    r"^(?:female|male|unsexed|adult|juvenile|juvie|sub-?adult|sub|slings?|"
    r"spiderlings?|mature|confirmed|probable|likely|young|pair|mm|pf|cb|wc|ph|cbb)"
    r"\b[\s.:,\-]*", re.I)
_STOP_SPECIES = {"and", "for", "the", "with", "was", "big", "top", "red", "blue",
                 "black", "green", "gold", "pink", "giant", "dwarf", "sale", "only"}


# Local-pickup / in-person-only listings. These ARE livestock, but they can't be
# bought online, and vendors list them ALONGSIDE the shippable copy — so counting
# them double-counts stock and invents phantom duplicates (a beta tester saw
# "2 listings at 0.5\"" for a Caribena versicolor that Spider Shoppe lists once,
# the second being "[Vancouver Pick-up]"). Checked against the RAW title, because
# is_livestock() strips a leading "[...]" prefix before its own tests.
_PICKUP_ONLY_RE = re.compile(
    r"pick[\s\-]?up\b|\blocal\s*pick|\bin[\s\-]?store\s*only\b|\bexpo\s*only\b|"
    r"\bshow\s*only\b|\bno\s*ship(?:ping)?\b|\bcash\s*(?:and|&|n)\s*carry\b", re.I)


def is_pickup_only(title: str) -> bool:
    """True for local-pickup / in-person-only listings (not purchasable online)."""
    return bool(title) and bool(_PICKUP_ONLY_RE.search(title))


def is_livestock(title: str) -> bool:
    """True when the title looks like a live invertebrate listing."""
    if not title:
        return False

    stripped = title.strip()
    stripped = re.sub(r"^\s*[\[(][^\])]{0,40}[\])]\s*", "", stripped).strip()
    stripped = stripped.lstrip('"“”*- ').strip()
    for _ in range(3):
        new = _LEAD_QUALIFIER.sub("", stripped)
        if new == stripped:
            break
        stripped = new.strip()

    low = stripped.lower()

    # (1) Strong deny — apparel / merch / feeders / verts / consumables.
    if _STRONG_RE.search(low):
        return False
    if _ART_PRINT_RE.search(low):        # "Print 5X7 of <species>" art, not livestock
        return False

    tokens = re.findall(r"[a-z]+", low)

    # (2) Deny plant / shell / vertebrate genera.
    if tokens and tokens[0] in DENY_GENERA:
        return False

    # (2b) Bulk feeder pack ("(25 count)", "50 ct", "pack of 100") with no invert
    # genus → feeder insects, not livestock (drops Josh's "Orange Head Roaches
    # (25 count)" that would otherwise pass on the "roach" taxon keyword).
    if _FEEDER_PACK_RE.search(low) and not any(t in GENUS_SET for t in tokens):
        return False

    # (3) Positive signal: known invert genus token, or specific taxon keyword.
    if any(t in GENUS_SET for t in tokens):
        return True
    padded = " " + low + " "
    for kw in TAXON_KEYWORDS:
        if kw in padded:
            return True

    # (4) Weak deny — containers / substrate / decor (no genus/taxon here).
    if _WEAK_RE.search(low):
        return False

    # (5) Clean lowercase binomial (rare/misspelled genera) or "Genus sp.".
    taxon = re.sub(r"\([^)]*\)", " ", stripped)
    m = _LOWER_BINOMIAL.search(taxon)
    if m and m.group(2) not in _STOP_SPECIES:
        return True
    if _GENUS_SP.search(taxon):
        return True

    return False
