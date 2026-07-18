"""
Canonical species identity.

Vendor titles are messy — "Theraphosa blondi", "Theraphosa blondi - Goliath
Bird Eater - 2\"-2.5\"", "Theraphosa blondi (Goliath Birdeater) about 2 1/2\""
must all collapse to ONE species so grouping, dedup, deal scoring, the species
list and the "spider card" all agree.

canonical_species(raw) -> (key, display, common)
  key     : lowercase "genus species" (or "genus sp <descriptor>") — the join key
  display : "Genus species" (or "Genus sp. 'Descriptor'")
  common  : best common name (curated map, else harvested from a parenthetical)

Only real invert genera (normalize.livestock.GENUS_SET) anchor the parse, so
supply/plant/junk titles return key="" and are excluded from species views.
"""
from __future__ import annotations

import re

from normalize.livestock import GENUS_SET, DENY_GENERA, is_livestock
from normalize.common_names_map import COMMON_NAMES
from normalize.key_aliases import canonicalize_key

# tokens that are never part of a species name (size / sex / life-stage / trade)
_NOISE = re.compile(
    r"\b("
    r"female|male|unsexed|adult|juvenile|juvie|sub-?adult|sub|sling|slings|"
    r"spiderling|spiderlings|mature|confirmed|probable|likely|young|pair|mm|pf|"
    r"cb|cbb|wc|ltc|fh|about|approx|approximately|inch|inches|in|"
    r"pure|bloodline|bloodlines|rare|beautiful|stunning|freebie|communal|"
    r"best|beginner|intermediate|advanced|event|crawler|sale|new"
    r")\b", re.I)

_FORMS = {"rcf", "dcf", "usambara", "kigoma", "mikumi", "tcf", "highland",
          "lowland", "blue", "green", "orange", "red", "gold"}

# Title-Case words that are NEVER a Latin species epithet — colours, hobby
# descriptors, common-name fragments. Lets us accept "Grammostola Grossa" (a
# real Title-Cased binomial) while still rejecting "Grammostola Red Knee".
_EPITHET_DENY = {
    "red", "blue", "green", "gold", "golden", "orange", "purple", "pink",
    "black", "white", "silver", "brown", "yellow", "grey", "gray", "scarlet",
    "cobalt", "electric", "metallic", "giant", "dwarf", "common", "rare",
    "beautiful", "stunning", "curly", "hair", "knee", "leg", "legs", "rump",
    "bird", "birdeater", "spider", "tarantula", "tiger", "baboon", "star",
    "starburst", "bottle", "rose", "king", "queen", "fire", "flame", "velvet",
    "earth", "tree", "pink", "toe", "pinktoe", "zebra", "chevron", "sun",
    "suntiger", "fang", "blonde", "blond", "birdeating", "horned", "feather",
    "featherleg", "skeleton", "ghost", "jewel", "ornamental", "mountain",
    "desert", "forest", "jungle", "beauty", "female", "male", "unsexed",
    "juvenile", "adult", "sling", "spiderling", "sub", "mature", "the", "and",
    "with", "for", "new", "sale", "captive", "wild",
}


def _clean(raw: str) -> str:
    # Do NOT cut at the first dash — vendors write the binomial in either order
    # ("Genus species - Common" AND "Common - Genus species"). We keep all words
    # and let the genus-scan + lowercase-epithet logic find the species wherever
    # it sits; marketing words around it are skipped naturally.
    s = raw or ""
    s = re.sub(r"^\s*[\[(][^\])]{0,40}[\])]\s*", "", s).strip()   # leading store tag
    s = re.sub(r"\([^)]*\)", " ", s)                              # parentheticals
    s = re.sub(r'["“”\'‘’]', "", s)
    return re.sub(r"\s+", " ", s).strip()


def _harvest_common(raw: str) -> str | None:
    """Pull a common name out of a trailing/parenthetical phrase, if present."""
    m = re.search(r"\(([^)]{3,40})\)", raw or "")
    if m:
        cand = m.group(1).strip()
        if not re.search(r"\d|inch|\"|female|male|sling", cand, re.I):
            return cand
    # "Genus species - Common Name - size"
    parts = re.split(r"\s+[-–—]\s+", raw or "")
    if len(parts) >= 2:
        cand = parts[1].strip()
        if cand and not re.search(r"\d|inch|\"|female|male|sling|pickup", cand, re.I) and len(cand) <= 40:
            return cand
    return None


def _tok(t: str) -> str:
    """Strip surrounding punctuation, keep the word (case preserved)."""
    return re.sub(r"^[^A-Za-z]+|[^A-Za-z]+$", "", t)


def _parse_binomial(text: str):
    """Find a known-genus binomial in a token string.
    Returns (key, disp) or None; the sentinel "DENY" if a deny genus leads."""
    tokens = [_tok(t) for t in text.split()]
    tokens = [t for t in tokens if t]

    # Genus MUST be a known invert genus (keeps the species list clean — no
    # "Alaska shipping"/"Abalone shell" sneaking in via a binomial-looking pair).
    gi = None
    for i, t in enumerate(tokens):
        tl = t.lower()
        if tl in DENY_GENERA:
            return "DENY"
        if tl in GENUS_SET:
            gi = i
            break
    if gi is None:
        return None

    genus = tokens[gi].lower()
    species, descriptor = "", ""
    j = gi + 1
    while j < len(tokens):
        t = tokens[j]
        tl = t.lower()
        if tl in ("sp", "cf", "aff"):
            species = "sp"
            k = j + 1
            while k < len(tokens):
                dt = tokens[k]
                # descriptor = first trade word after "sp" (any case — trade
                # names are things like 'Mascara', 'Machala', 'antinous').
                if re.fullmatch(r"[A-Za-z]{3,}", dt) and not _NOISE.search(dt.lower()):
                    descriptor = dt.lower()
                    break
                k += 1
            break
        # A species epithet is normally an all-lowercase Latin word. Some vendors
        # Title-Case the whole binomial ("Grammostola Grossa"), so we also accept
        # a Title-Case word as the epithet — but only if it's not a known
        # marketing/common-name word, so "Green Bottle Blue" is still rejected.
        _is_epithet = ((re.fullmatch(r"[a-z]{3,}", t)
                        or (re.fullmatch(r"[A-Z][a-z]{3,}", t) and tl not in _EPITHET_DENY))
                       and not _NOISE.search(tl))
        if _is_epithet:
            # strip a sex/stage word glued to the epithet ("blondifemale",
            # "geniculatafemale", "cyaneopubescensfemale").
            species = re.sub(r"(female|male|unsexed|sling|spiderling|juvenile|adult)$", "", tl)
            if len(species) >= 3:
                break
            species = ""
        j += 1

    if not species:
        return None

    if species == "sp":
        key = f"{genus} sp {descriptor}".strip()
        disp = f"{genus.capitalize()} sp." + (f" '{descriptor.capitalize()}'" if descriptor else "")
    else:
        key = f"{genus} {species}"
        disp = f"{genus.capitalize()} {species}"
    return key, disp


def canonical_species(raw: str) -> tuple[str, str, str]:
    if not raw or not is_livestock(raw):
        return "", "", ""

    # Try the main text first (parentheticals stripped). If it has no known
    # genus, the real binomial is often INSIDE a parenthetical — a common-name-
    # first title like "Curly Hair Tarantula (Tliltocatl albopilosus)". Try each
    # parenthetical before giving up, so those key to the right species.
    candidates = [_clean(raw)]
    for m in re.findall(r"\(([^)]{0,60})\)", raw or ""):
        candidates.append(re.sub(r'["“”\'‘’]', "", m).strip())

    for idx, text in enumerate(candidates):
        res = _parse_binomial(text)
        if res == "DENY" and idx == 0:
            return "", "", ""     # deny genus in the primary text wins
        if res and res != "DENY":
            key, disp = res
            # Master alias pass: collapse misspelled / truncated keys onto the
            # one canonical key, then rebuild the display from the fixed key so
            # every scan yields clean "Genus species". See normalize/key_aliases.
            ckey = canonicalize_key(key)
            if ckey != key:
                key = ckey
                disp = _display_from_key(key)
            common = COMMON_NAMES.get(key) or _harvest_common(raw) or ""
            return key, disp, common
    return "", "", ""


def _display_from_key(key: str) -> str:
    """"genus species" -> "Genus species"; "genus sp desc" -> "Genus sp. 'Desc'"."""
    toks = key.split()
    if not toks:
        return ""
    if len(toks) >= 2 and toks[1] == "sp":
        desc = " ".join(toks[2:])
        return f"{toks[0].capitalize()} sp." + (f" '{desc.title()}'" if desc else "")
    return toks[0].capitalize() + ((" " + " ".join(toks[1:])) if len(toks) > 1 else "")
