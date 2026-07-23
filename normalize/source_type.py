"""
WC / CB / LTC Source Type Detection
Parses listing titles, notes, and variant text to determine whether
an animal is Wild Caught (WC), Captive Bred (CB), Long-Term Captive (LTC),
or Unknown.

Why it matters for pricing:
  - WC Aphonopelma flood the US market in summer at $10-15, dragging
    the apparent median below what CB specimens cost ($30-50).
  - WC adult females of rare species (Cobalt Blue, King Baboon) command
    a PREMIUM over CB slings because size+maturity is already done.
  - LTC animals are somewhere in between.

NOTE: source type carries ZERO weight in deal scoring — CB, WC and unstated
listings all compete in the same pool (see scoring/deals._comparison_key). Most
sellers never state a source, so splitting on it would knock the majority of
honest listings out of contention. It is shown to the buyer as information.

How we know a listing's source, in priority order (recorded as source_provenance):
  stated            — the listing itself says CB/WC
  vendor-confirmed  — a human confirmed the seller's policy (Vendors admin page)
  vendor-policy     — the seller's own site states captive-bred only (scraped;
                      see tools/scan_source_policy.py)
  inferred-juvenile — far below this species' adult size, so it must be a
                      captive-bred juvenile (validated ~97% precision)
"""
from __future__ import annotations
import re

# Source type codes
CB  = "CB"       # Captive Bred (also: CBB = captive bred and born)
WC  = "WC"       # Wild Caught
LTC = "LTC"      # Long-Term Captive (WC but established)
UNK = "unknown"  # Not specified

_WC_PATTERNS = [
    r'\bwc\b',
    r'\bwild[\s-]?caught\b',
    r'\bwild[\s-]?caught\b',
    r'\bfield[\s-]?collected\b',
    r'\bwild[\s-]?collected\b',
    r'\bltc\b',
    r'\blong[\s-]?term[\s-]?captive\b',
]

_CB_PATTERNS = [
    r'\bcb\b',
    r'\bcbb\b',
    r'\bcaptive[\s-]?bred\b',
    r'\bcaptive[\s-]?born\b',
    r'\bhome[\s-]?bred\b',
    r'\bbreeder\b',
    r'\bbreeding[\s-]?project\b',
    r'\bf\d+\b',         # F1, F2, F3 generation
]

_WC_RE = re.compile('|'.join(_WC_PATTERNS), re.IGNORECASE)
_CB_RE = re.compile('|'.join(_CB_PATTERNS), re.IGNORECASE)


# ── VENDOR SOURCE POLICY ─────────────────────────────────────────────────────
# Many sellers state their captive-bred policy ONCE on their site rather than on
# every listing — so their listings look "unknown" even though they have in fact
# told us. We only record a policy we could QUOTE from the vendor's own site
# (verified by tools/scan_source_policy.py). Applied ONLY when the listing itself
# is silent, and always tagged source_provenance="vendor-policy" so the UI can
# show that it came from the seller's site policy, not from this listing.
#
# Re-verify with:  python tools/scan_source_policy.py
VENDOR_SOURCE_POLICY = {
    # ── Site-wide policy statement on the vendor's own site ──────────────────
    # "…the best selection of 100% captive-bred tarantulas for sale…"
    # (also: every sampled product page states captive-bred)
    "exotics_unlimited": CB,
    # "…We specialize in 100% captive bred tarantulas and inverts…"
    "ghostys": CB,
    # "…How Are We Unique? We Sell Only Captive-Bred Animals…"
    "joshsfrogs": CB,
    # "…We are a breeder of many of the newest jumping spider species…"
    "spider_room": CB,
    # ── Every sampled product page states captive-bred, none mention WC ──────
    # "…For Sale | Captive Bred | Great Basin Serpentarium…"  (6/6 pages)
    "great_basin": CB,
    # "CBB …"                                                  (6/6 pages)
    "marshall_arachnids": CB,
    # "…Captive bred tarantulas, invertebrates, supplies…"     (6/6 pages)
    "wonderland_exotics": CB,
    # ── DELIBERATELY NOT LISTED ─────────────────────────────────────────────
    # arachnid_rarities — homepage claims "captive bred scorpions" BUT sampled
    #   product pages sell wild-caught stock. Not a CB-only seller.
    # pacific_northwest, big_zs — product pages mention BOTH CB and WC.
    # fear_not, spidershoppe, urban_tarantulas, hardcore_arachnids, vexotic,
    #   buddha_bugs, plumbs_exotics, …  — state no source anywhere we can read.
    #   These need a human-confirmed policy (ask the vendor); we will not guess.
}

# Human-confirmed vendor policies, loaded from the DB at runtime (set in the
# Vendors admin page: "I asked Fear Not — they are captive-bred only").
# These OUTRANK the scraped map above, because a human checked. Listings that
# state their own source always still win over any vendor-level policy.
VENDOR_POLICY_CONFIRMED: dict[str, str] = {}


def set_confirmed_policies(mapping: dict) -> None:
    """Install human-confirmed vendor policies (called once per snapshot build)."""
    VENDOR_POLICY_CONFIRMED.clear()
    VENDOR_POLICY_CONFIRMED.update({k: v for k, v in (mapping or {}).items() if v})


# A vendor spec line that STATES the source, e.g. "CB/WC: WC", "Source: Captive Bred".
# Captures the stated VALUE so the label's own "CB" can't be mistaken for the answer.
_LABELLED_RE = re.compile(
    r"(?:cb\s*/\s*wc|wc\s*/\s*cb|source|origin\s*type|captive[\s-]?bred\s*/\s*wild[\s-]?caught)"
    r"\s*[:=]\s*"
    r"(ltc|long[\s-]?term[\s-]?captive|cbb?|wc|captive[\s-]?bred|wild[\s-]?caught)\b",
    re.IGNORECASE)


def detect_source_type(title: str = "", notes: str = "",
                        variant: str = "") -> str:
    """
    Detect WC / CB / LTC / unknown from any combination of
    listing title, notes, and variant text.

    Returns: 'CB' | 'WC' | 'LTC' | 'unknown'
    """
    combined = f"{title} {notes} {variant}".strip()
    if not combined:
        return UNK

    # LABELLED SPEC FIELD FIRST. Several vendors publish a spec block like
    # "CB/WC: WC" — the answer is the value AFTER the label. Pattern-matching the
    # raw text there is actively WRONG: the label itself contains "CB", so a
    # wild-caught animal would be reported as captive-bred (both tokens match and
    # the tie-break trusts CB). Read the stated value instead.
    m = _LABELLED_RE.search(combined)
    if m:
        val = m.group(1).lower()
        if re.match(r"ltc|long", val):
            return LTC
        if val.startswith("wc") or "wild" in val:
            return WC
        return CB

    has_wc = bool(_WC_RE.search(combined))
    has_cb = bool(_CB_RE.search(combined))

    # LTC takes precedence over generic WC
    if re.search(r'\bltc\b|long[\s-]?term[\s-]?captive', combined, re.IGNORECASE):
        return LTC
    if has_wc and not has_cb:
        return WC
    if has_cb and not has_wc:
        return CB
    if has_cb and has_wc:
        # Both mentioned — trust CB label (some CB sellers note WC parents)
        return CB

    # Size-based inference: slings (< 1") almost never WC
    # Not applied here — done at the listing level with size context.
    return UNK


# Many vendors state the source only in the product DESCRIPTION ("CB/WC: WC",
# "captive bred here at the shop"), never in the title or variant — so the
# listing looked "unknown" even though it told us. Prose is noisier than a
# title, so we read only UNAMBIGUOUS signals here: the labelled spec field and
# explicit phrases. The weak title tokens are deliberately NOT used —
# "breeder" ("a favourite among breeders"), bare "cb", and "F2" all turn up
# incidentally in marketing copy and would manufacture a source we were never told.
_PROSE_CB_RE = re.compile(
    r"\b(?:captive[\s-]?bred|captive[\s-]?born|home[\s-]?bred|cbb)\b", re.IGNORECASE)
_PROSE_WC_RE = re.compile(
    r"\b(?:wild[\s-]?caught|field[\s-]?collected|wild[\s-]?collected|"
    r"imported\s+from\s+the\s+wild)\b", re.IGNORECASE)
_PROSE_LTC_RE = re.compile(r"\b(?:ltc|long[\s-]?term[\s-]?captive)\b", re.IGNORECASE)


def detect_source_type_in_prose(text: str = "") -> str:
    """Detect a source the vendor STATED in free-text description copy.

    High-confidence signals only (see note above). Returns UNK when the prose
    is silent or says both, so a guess never outranks an honest 'unknown'.
    """
    if not text:
        return UNK
    m = _LABELLED_RE.search(text)
    if m:                                   # an explicit spec field wins outright
        return detect_source_type(m.group(0))
    if _PROSE_LTC_RE.search(text):
        return LTC
    has_cb = bool(_PROSE_CB_RE.search(text))
    has_wc = bool(_PROSE_WC_RE.search(text))
    if has_cb != has_wc:                    # exactly one -> trust it
        return CB if has_cb else WC
    return UNK                              # silent, or contradicts itself


def infer_source_type_from_size(detected: str, size_midpoint: float = None) -> str:
    """
    If detection was inconclusive and the animal is a tiny sling, call it CB.
    Absolute-size rule only — kept conservative at 0.75" because dwarf species
    are ADULT at ~1", and we do see genuine wild-caught animals at 1.0".
    The stronger, species-relative rule lives in infer_source_relative_to_adult.
    """
    if detected != UNK:
        return detected
    if size_midpoint is not None and size_midpoint < 0.75:
        return CB
    return UNK


# Fraction of a species' adult size below which an animal must be a juvenile.
# Validated against our own labelled data (218 seller-stated CB/WC listings):
#   ratio <0.20 -> 100% CB · <0.30 -> 97.3% · <0.35 -> 97.6% · <0.40 -> 94.2%
# 1/3 keeps ~97% precision. A sling of a large species cannot be wild-collected;
# nobody field-collects 1/4" spiderlings commercially.
JUVENILE_RATIO = 0.33


def infer_source_relative_to_adult(detected: str, size_midpoint, adult_size):
    """A listing well under its own species' adult size is a juvenile → CB.
    This is the species-relative rule: 1" is a sling for Theraphosa (10" adult)
    but an ADULT for a dwarf species — so absolute size alone can't decide."""
    if detected != UNK:
        return detected, ""
    if not size_midpoint or not adult_size or adult_size <= 0:
        return UNK, ""
    if (size_midpoint / adult_size) < JUVENILE_RATIO:
        return CB, "inferred-juvenile"
    return UNK, ""


def annotate_source_types(listings: list) -> None:
    """
    Add source_type field ('CB', 'WC', 'LTC', 'unknown') to each listing.
    Modifies in place. Works with dicts and Listing objects.
    """
    def _get(l, k, is_dict):
        return ((l.get(k) or "") if is_dict else (getattr(l, k, "") or ""))

    # Adult-size proxy per species = the largest specimen anyone is offering.
    # Lets us tell "1in sling of a 10in species" (must be CB) apart from
    # "1in adult of a dwarf species" (could be wild-caught).
    adult = {}
    for l in listings:
        d = isinstance(l, dict)
        k = _get(l, "scientific_name_key", d)
        m = (l.get("size_midpoint") if d else getattr(l, "size_midpoint", None))
        if k and m:
            adult[k] = max(adult.get(k, 0.0), float(m))

    for l in listings:
        is_dict = isinstance(l, dict)
        # Read EVERY stored text field a seller might put "CB"/"WC" in. We used to
        # miss variant_name and scientific_name — sellers routinely write
        # "Sub Adult/Adult WC" or "… 4\"-5\" MALE (WC)" there.
        title   = _get(l, "raw_title", is_dict) or _get(l, "scientific_name", is_dict)
        notes   = _get(l, "notes", is_dict)
        variant = " ".join(filter(None, [
            _get(l, "raw_variant", is_dict),
            _get(l, "variant_name", is_dict),
            _get(l, "size_text", is_dict),
        ]))
        blob    = " ".join(filter(None, [
            _get(l, "raw_title", is_dict),
            _get(l, "scientific_name", is_dict),
        ]))
        mid     = l.get("size_midpoint") if is_dict else getattr(l, "size_midpoint", None)

        detected = detect_source_type(f"{title} {blob}", notes, variant)

        # Fall back to the product DESCRIPTION when the title/variant are silent.
        # Many sellers only state CB/WC down in the body copy, so the listing did
        # tell us — we just were not reading it. Title/variant still win outright;
        # the description can only fill an 'unknown', never overturn a statement.
        if detected == UNK:
            detected = detect_source_type_in_prose(_get(l, "description", is_dict))

        # Vendor-level policy: many sellers are breeders who state "all captive
        # bred" once on their site rather than on each listing. Apply only when
        # the listing itself is silent, and record HOW we know (provenance).
        vendor = _get(l, "vendor_key", is_dict)
        provenance = "stated" if detected != UNK else ""
        if detected == UNK:
            # human-confirmed policy outranks the scraped one
            pol = VENDOR_POLICY_CONFIRMED.get(vendor)
            if pol:
                detected, provenance = pol, "vendor-confirmed"
            else:
                pol = VENDOR_SOURCE_POLICY.get(vendor)
                if pol:
                    detected, provenance = pol, "vendor-policy"

        # 3) tiny sling (absolute) → CB
        final = infer_source_type_from_size(detected, mid)
        if final != detected and not provenance:
            provenance = "inferred-juvenile"

        # 4) species-relative: well under this species' own adult size → CB
        if final == UNK:
            key = _get(l, "scientific_name_key", is_dict)
            final, prov2 = infer_source_relative_to_adult(final, mid, adult.get(key))
            if prov2:
                provenance = prov2

        if final != UNK and not provenance:
            provenance = "stated"

        if is_dict:
            l["source_type"] = final
            l["source_provenance"] = provenance or ""
        else:
            setattr(l, "source_type", final)
            setattr(l, "source_provenance", provenance or "")
