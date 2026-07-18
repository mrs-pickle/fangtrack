"""
MASTER SPECIES-KEY ALIAS REFERENCE
==================================

The single source of truth for collapsing malformed / misspelled / truncated
``scientific_name_key`` values onto ONE canonical key per species. This is the
list to extend whenever a scan surfaces a new junk key — every crawl runs the
result through ``canonicalize_key`` (wired into ``normalize.species_canonical``
and ``database.db.record``), so a fix added here cleans BOTH future scans and,
via ``tools/migrate_key_aliases.py``, all historical rows.

Two layers, applied in order:

1. ``KEY_ALIASES`` — exact ``bad key -> good key`` overrides. Use for epithet
   misspellings, truncated locality names, and reclassifications that the genus
   remap alone can't fix (e.g. ``tlitocatl khalenbergi -> tliltocatl kahlenbergi``).

2. ``GENUS_ALIASES`` — misspelled genus -> accepted genus, applied to the FIRST
   token of a key. Fixes a whole class at once (every ``theraposa <x>`` becomes
   ``theraphosa <x>``). Every target genus must exist in
   ``normalize.livestock.GENUS_SET`` or the corrected species stays hidden.

Keys are the lowercase "genus species" / "genus sp descriptor" form produced by
``canonical_species`` — NOT raw vendor titles. Scientific-name reclassifications
that operate on the full binomial still live in ``normalize/synonyms.py``; this
module is specifically for cleaning the derived key.
"""
from __future__ import annotations

# ── Misspelled genus → accepted genus (target must be in GENUS_SET) ──────────
GENUS_ALIASES: dict[str, str] = {
    "theraposa":          "theraphosa",
    "phiddipus":          "phidippus",
    "tlitocatl":          "tliltocatl",
    "tlitocatlt":         "tliltocatl",
    "phormigochilus":     "phormingochilus",
    "phormingohilus":     "phormingochilus",
    "seleobrachys":       "selenobrachys",
    "hapolopus":          "hapalopus",
    "xenethesis":         "xenesthis",
    "spinosatiapalpus":   "spinosatibiapalpus",
    "syctodes":           "scytodes",
    "kukulkania":         "kukulcania",
    "homeomma":           "homoeomma",
    "ybirapora":          "ybyrapora",
    "grandanameno":       "gandanameno",
    "brachinopus":        "brachionopus",  # invisible in browse (not in GENUS_SET) — data-merge only
    "abdomegaphobema":    "megaphobema",   # "abdomen. Megaphobema…" glued in title
    "cilantica":          "haploclastus",  # invisible in browse — merges devamatha/psychedelicus/kali
}

# ── Exact key → canonical key (epithet fixes, truncations, glued size text) ──
KEY_ALIASES: dict[str, str] = {
    # epithet misspellings
    "tlitocatl khalenbergi":          "tliltocatl kahlenbergi",
    "tliltocatl khalenbergi":         "tliltocatl kahlenbergi",
    "homeomma chilense":              "homoeomma chilensis",
    "homoeomma chilense":             "homoeomma chilensis",
    "homoeomma chilenense":           "homoeomma chilensis",
    "homeomma chilenense":            "homoeomma chilensis",
    "nhandu colloratovilosus":        "nhandu coloratovillosus",
    "nhandu coloratovilosus":         "nhandu coloratovillosus",
    "poecilotheria tigrinawesselli":  "poecilotheria tigrinawesseli",
    "chromatopelma cyanapubescense":  "chromatopelma cyaneopubescens",
    "omothymus violaceops":           "omothymus violaceopes",
    "grammostola quiroguay":          "grammostola quirogai",
    "lasiodora kluggi":               "lasiodora klugi",
    "melopoeus lividis":              "melopoeus lividus",
    # Party Mix is a pruinosus morph, not a species
    "porcellionides party":           "porcellionides pruinosus",
    "tliltocatl albopilosum":         "tliltocatl albopilosus",
    "tlitocatl albopilosum":          "tliltocatl albopilosus",
    # truncated locality forms → clean sp. descriptor
    "bonnetina mexican":              "bonnetina sp mexican",
    "chilobrachys vietnam":           "chilobrachys sp vietnam",
    "avicularia peru":                "avicularia sp peru",
    # junk size/marketing text glued into keys, for genera visible in the browse
    "hapolopus sp colombia formosus lg pumpkin patch tarantula 5i":    "hapalopus sp colombia",
    "hapolopus sp colombia formosus lg pumpkin patch tarantula 75- 1": "hapalopus sp colombia",
    "kukulkania hibernalis 1-2":      "kukulcania hibernalis",
    "spinosatiapalpus sp panama 2 female": "spinosatibiapalpus sp panama",
    "tlitocatlt vagans- female- pure bloodlines- campache mx": "tliltocatl vagans",
    # Haploclastus (was mis-keyed as "cilantica") — merge variants together
    "haploclastus khali":             "haploclastus kali",
    "cilantica sp kali":              "haploclastus kali",
    "cilantica sp kali 1":            "haploclastus kali",
    "cilantica sp kali about 1 1 4 - 1 1 2 very similar to psychedelicus rare": "haploclastus kali",
    "cilantica devamatha 3 4":        "haploclastus devamatha",
    "cilantica pyschedelicus":        "haploclastus psychedelicus",
    "cilantica psychedelicus":        "haploclastus psychedelicus",
    # ── Common-name-only keys → species (2026-07-17). Only well-established,
    #    unambiguous hobby common names; ambiguous ones are left as-is (honesty > coverage).
    #    Keys are the post-strip form (trailing "tarantula" etc. already peeled).
    "mexican red leg":                "brachypelma emilia",
    "mexican red knee":               "brachypelma hamorii",
    "mexican fireleg":                "brachypelma boehmei",
    "mexican fire leg":               "brachypelma boehmei",
    "mexican red rump":               "tliltocatl vagans",
    "brazilian black":                "grammostola pulchra",
    "brazilian white knee":           "acanthoscurria geniculata",
    "brazilian whiteknee":            "acanthoscurria geniculata",
    "curly hair":                     "tliltocatl albopilosus",
    "arizona blonde":                 "aphonopelma chalcodes",
    "green bottle blue":              "chromatopelma cyaneopubescens",
    "greenbottle blue":               "chromatopelma cyaneopubescens",
    "trinidad olive":                 "neoholothele incei",
    "regal jumping":                  "phidippus regius",
    "chaco golden knee":              "grammostola pulchripes",
    "costa rican zebra":              "aphonopelma seemanni",
    "salmon pink birdeater":          "lasiodora parahybana",
    "featherleg baboon":              "stromatopelma calceatum",
    "togo starburst":                 "heteroscodra maculata",
    "singapore blue":                 "omothymus violaceopes",
    "cameroon red baboon":            "hysterocrates gigas",
    "socotra island blue baboon":     "monocentropus balfouri",
    "gooty sapphire ornamental":      "poecilotheria metallica",
    "gooty sapphire":                 "poecilotheria metallica",
    "indian ornamental":             "poecilotheria regalis",
    # Megaphobema mesomelas rows that fell back to raw-name keys with size junk
    "abdomegaphobema mesomelas about 1 1 2":            "megaphobema mesomelas",
    "abdomegaphobema mesomelas female":                 "megaphobema mesomelas",
    "abdomegaphobema mesomelas male":                   "megaphobema mesomelas",
    "abdomegaphobema mesomelas costa rica red leg":     "megaphobema mesomelas",
    "abdomegaphobema peterklaasi about 1 1 4 - 1 1 2 rare": "megaphobema peterklaasi",
    "abdomegaphobema peterklaasi very rare":            "megaphobema peterklaasi",
}


import re as _re

# Words that mean "the real name ended here; everything after is a note." The key
# is truncated at the first one so size text and reclassification blurbs drop off.
_CUT_MARKERS = {"formerly", "coming", "about", "similar", "aka", "approx", "was",
                "very", "new", "rare"}
# Species placeholders: what follows is a LOCALITY (e.g. "sp new guinea"), not a
# note, so a cut-marker right after one must NOT truncate the key — otherwise
# "selenocosmia sp new guinea" collapses to "selenocosmia sp" and distinct
# localities merge into one.
_PLACEHOLDERS = {"sp", "sp.", "cf", "cf.", "aff", "aff."}
# Trailing tokens that are never part of a name — pure size/pack/stage fragments.
_TRAIL_JUNK = _re.compile(r"^(\d.*|.*\d.*|[-/]+|ct|pcs?|x|lg|sm|med|"
                          r"female|male|unsexed|spiderlings?|slings?|juvenile|adult|"
                          r"pair|trio|group|lot|auction)$")
# Generic type-nouns vendors append (e.g. underground_reptiles: "… Tarantula").
# Never part of a genus/epithet, so safe to peel off the end down to the binomial.
_TRAIL_NOUN = {"tarantula", "tarantulas", "spider", "spiders", "scorpion", "scorpions",
               "isopod", "isopods", "millipede", "millipedes", "centipede", "centipedes",
               "mantis", "roach", "roaches", "trapdoor"}
# Stage / sex / group words vendors prepend (e.g. "Adult Female X"). No genus is one
# of these, so safe to peel off the front down to the binomial.
_LEAD_JUNK = {"adult", "juvenile", "juvie", "subadult", "baby", "female", "male",
              "unsexed", "young", "large", "small", "medium", "med", "gravid",
              "mature", "immature", "pair", "trio", "group", "sub"}


def _strip_key_junk(kl: str) -> str:
    """Drop size numbers, pack counts, stage/sex prefixes, generic type-noun suffixes,
    and trailing note-words from a key, keeping at least the 'genus species' / 'genus sp'
    core. Generic so it cleans the whole class on every scan, not just known-bad keys."""
    toks = kl.split()
    # cut at the first note-marker (but never before token 2, and never when it
    # directly follows a species placeholder — that's a locality, not a note)
    for i, t in enumerate(toks):
        if i >= 2 and t in _CUT_MARKERS and toks[i - 1] not in _PLACEHOLDERS:
            toks = toks[:i]
            break
    # peel leading stage/sex/group words, never below 2 tokens
    while len(toks) > 2 and toks[0] in _LEAD_JUNK:
        toks.pop(0)
    # peel trailing type-nouns + size/pack/stage tokens, never below 2 tokens
    while len(toks) > 2 and (toks[-1] in _TRAIL_NOUN or _TRAIL_JUNK.match(toks[-1])):
        toks.pop()
    # a bare "genus sp" with the descriptor stripped keeps just 2 tokens
    return " ".join(toks)


def canonicalize_key(key: str) -> str:
    """Collapse a raw species key onto its canonical form. Idempotent."""
    if not key:
        return key
    k = " ".join(key.split())            # normalize whitespace
    kl = k.lower()
    if kl in KEY_ALIASES:                # exact override wins
        return KEY_ALIASES[kl]
    toks = kl.split()
    if toks and toks[0] in GENUS_ALIASES:
        toks[0] = GENUS_ALIASES[toks[0]]
        kl = " ".join(toks)
        kl = KEY_ALIASES.get(kl, kl)     # a genus fix may expose a further exact alias
    kl = _strip_key_junk(kl)
    return KEY_ALIASES.get(kl, kl)
