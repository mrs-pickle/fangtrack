"""
Size normalization for tarantula listings.
Parses seller-provided size text into numeric inch values.
Never invents or assumes sizes -- returns None for unknown/non-numeric.
"""
import re
from typing import Optional, Tuple

NON_NUMERIC_LABELS = {
    "sling", "slings", "spiderling", "spiderlings",
    "juvenile", "juveniles", "juv",
    "sub-adult", "subadult", "sub adult",
    "young adult", "adult", "adults",
    "small", "medium", "large",
    "unsexed", "unknown",
}


def parse_size(raw: Optional[str]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Parse size string -> (min_inches, max_inches, midpoint).
    Returns (None, None, None) for non-numeric or failed parse.
    """
    if not raw:
        return None, None, None

    text = raw.strip()
    lower = text.lower()
    check = re.sub(r'[""\s]*(inch(es)?|in\.?)?\s*$', "", lower).strip()
    if check in NON_NUMERIC_LABELS:
        return None, None, None

    # Normalize unicode fractions and inch marks
    n = text.replace("½", "0.5").replace("¼", "0.25").replace("¾", "0.75")
    n = n.replace("~", "").strip()
    n = re.sub(r'[""]', '"', n)
    n = re.sub(r'\b(inch(es)?|in\.?)\b', '"', n, flags=re.IGNORECASE)

    # Mixed number: "3 1/2" -> 3.5 (must come BEFORE the bare-fraction branch,
    # or "3 1/2" is misread as just 1/2 = 0.5).
    m = re.match(r"^(\d+)\s+(\d+)\s*/\s*(\d+)", n.strip())
    if m:
        val = int(m.group(1)) + int(m.group(2)) / int(m.group(3))
        return val, val, val

    # Fraction: 1/2
    m = re.match(r"^(\d+)/(\d+)", n.strip())
    if m:
        val = int(m.group(1)) / int(m.group(2))
        return val, val, val

    # Range: 1-1.5" or 1.5–3"
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-\u2013]\s*(\d+(?:\.\d+)?)", n)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo > hi:
            lo, hi = hi, lo
        return lo, hi, (lo + hi) / 2

    # Plus: 4"+
    m = re.search(r"(\d+(?:\.\d+)?)\s*\+", n)
    if m:
        val = float(m.group(1))
        return val, None, val

    # Single value: 2.5" or 2.5
    m = re.match(r"(\d+(?:\.\d+)?)\s*\"?", n.strip())
    if m:
        val = float(m.group(1))
        if 0.1 <= val <= 14.0:
            return val, val, val

    return None, None, None


# Embedded size token in a free-text title. Requires an explicit unit (inch
# mark / "inch" / "in" / "cm") or a fraction-with-mark so we never mistake a
# stray number in a name ("Pamphobeteus sp 2", "Poecilotheria 50") for a size.
# Inch marks seen in the wild: straight/curly double-quote, the doubled
# apostrophe (0.75''), and word forms. A number may be a normal decimal (2.5)
# or a leading-dot decimal (.75).
_NUM = r'(?:\d+(?:\.\d+)?|\.\d+)'
# fraction-aware number: matches "3/4" as well as "1.5" / ".75" (fraction first
# so a range endpoint like "3/4-1" isn't misread as "4-1").
_NUMF = r'(?:\d+\s*/\s*\d+|\d+(?:\.\d+)?|\.\d+)'
# Range/endpoint number that ALSO understands a mixed number ("3 1/2"). Mixed
# first so "3 1/2" is grabbed whole, not reduced to its "1/2" fraction.
_NUMM = r'(?:\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+(?:\.\d+)?|\.\d+)'
_INCH = r'(?:"|”|“|″|\'\'|inch(?:es)?|in\b)'
_SIZE_IN_TITLE = re.compile(
    r'(?<![\w])'
    r'(?:'
    rf'(?P<range>{_NUMM}\s*[-–]\s*{_NUMM})\s*(?:{_INCH}|cm)'
    rf'|(?P<mixed>\d+\s+\d+\s*/\s*\d+)\s*{_INCH}'
    rf'|(?P<frac>\d+\s*/\s*\d+)\s*{_INCH}'
    rf'|(?P<uni>[½¼¾])\s*{_INCH}?'
    rf'|(?P<single>{_NUM})\s*(?P<unit>{_INCH}|cm)\s*(?P<plus>\+)?'
    r')',
    re.IGNORECASE,
)
_UNI_FRAC = {"½": "0.5", "¼": "0.25", "¾": "0.75"}


def extract_size_from_title(title: Optional[str]) -> Optional[str]:
    """Pull a size token out of a product TITLE (e.g. 'Stromatopelma … 0.5\"'
    -> '0.5\"'). Returns a raw size string parse_size() understands, or None.
    Takes the LAST match since size is conventionally at the end of a title.
    Converts cm to inches so downstream stays in one unit."""
    if not title:
        return None
    import html
    title = html.unescape(title)   # decode &#8221; &#8211; etc. before matching
    matches = list(_SIZE_IN_TITLE.finditer(title))
    if not matches:
        return None
    m = matches[-1]
    is_cm = "cm" in m.group(0).lower()
    if m.group("range"):
        raw = m.group("range")
        # resolve each endpoint (which may be a fraction like 3/4) to a decimal,
        # so "3/4-1" -> 0.75-1, not the "4-1" the old numeric range produced.
        def _val(p):
            p = p.strip()
            mm = re.match(r"^(\d+)\s+(\d+)\s*/\s*(\d+)$", p)   # mixed "1 1/2"
            if mm:
                return int(mm.group(1)) + int(mm.group(2)) / int(mm.group(3))
            if "/" in p:
                a, b = re.split(r"\s*/\s*", p)
                return float(a) / float(b)
            return float(p)
        try:
            parts = [_val(p) for p in re.split(r"\s*[-–]\s*", raw)]
        except (ValueError, ZeroDivisionError):
            return raw + '"'
        if len(parts) == 2:
            lo, hi = parts
            if is_cm:
                lo, hi = lo / 2.54, hi / 2.54
            if lo > hi:
                lo, hi = hi, lo
            return f'{round(lo, 3)}-{round(hi, 3)}"'
        return raw + '"'
    if m.group("mixed"):
        mm = re.match(r"(\d+)\s+(\d+)\s*/\s*(\d+)", m.group("mixed"))
        val = int(mm.group(1)) + int(mm.group(2)) / int(mm.group(3))
        return f'{val}"'
    if m.group("frac"):
        return m.group("frac") + '"'
    if m.group("uni"):
        return _UNI_FRAC.get(m.group("uni"), "") + '"'
    if m.group("single"):
        val = float(m.group("single"))
        if is_cm:
            val = round(val / 2.54, 2)
        plus = m.group("plus") or ""
        return f'{val}"{plus}'
    return None


# Life-stage words → a bucket-representative midpoint. This is NOT a measured
# size; it places a listing in the life-stage bucket the VENDOR stated (e.g.
# "Juvenile female" → juvenile bucket) so it compares like-for-like. The centers
# match scoring.deals buckets (sling<0.75, juvenile<1.75, subadult<3, adult<5).
# Order matters: sub-adult before adult; juvenile before adult.
_LIFESTAGE = [
    (re.compile(r'\b(spiderlings?|slings?|babies|baby)\b', re.I), "Sling", 0.5),
    (re.compile(r'\bsub[\s-]?adults?\b', re.I), "Sub-adult", 2.5),
    (re.compile(r'\byoung\s+adults?\b', re.I), "Sub-adult", 2.5),
    (re.compile(r'\b(juveniles?|juvie?s?|juv)\b', re.I), "Juvenile", 1.25),
    (re.compile(r'\b(mature\s+males?|adults?)\b', re.I), "Adult", 4.0),
]


def lifestage_size(*texts) -> Tuple[Optional[str], Optional[float]]:
    """Detect a life-stage word in any of the given texts → (label, midpoint).
    Used only as a fallback when no numeric size is present, so a listing the
    vendor labelled 'Juvenile' still lands in the juvenile comparison bucket."""
    for t in texts:
        if not t:
            continue
        for rx, label, mid in _LIFESTAGE:
            if rx.search(t):
                return label, mid
    return None, None


# Multi-specimen pack: "10 X …", "50 Lot …", "10-lot", "10 pack", "10ct", "10/$100".
_PACK_RE = re.compile(
    r'(?:^|\b)(\d{1,3})\s*(?:x\b|[-\s]?lot\b|[-\s]?pack\b|\s?ct\b|\s?count\b|/\s*\$)',
    re.IGNORECASE,
)


def detect_pack(*texts):
    """Count of specimens if the listing is a multi-animal pack, else None.
    So a $200 'pack of 10' isn't mistaken for one $200 animal."""
    for t in texts:
        if not t:
            continue
        m = _PACK_RE.search(str(t))
        if m:
            try:
                n = int(m.group(1))
                if 2 <= n <= 200:
                    return n
            except ValueError:
                pass
    return None


def derive_size(size_text, *sources):
    """The single source of truth for turning a listing's size hints into
    (size_text, min, max, midpoint). Tries, in order: a clean size field →
    a numeric size embedded in the size field / variant / title → a life-stage
    word. Used by BOTH the scraper (_make_listing) and the DB save path
    (db.record) so they can never disagree again.
    """
    # 1. the size field parses cleanly on its own
    if size_text:
        lo, hi, mid = parse_size(size_text)
        if mid is not None:
            return size_text, lo, hi, mid
    # 2. a numeric size embedded anywhere (verbose variant, title, name)
    for src in (size_text, *sources):
        tok = extract_size_from_title(src)
        if tok:
            lo, hi, mid = parse_size(tok)
            if mid is not None:
                return (size_text or tok), lo, hi, mid
    # 3. life-stage word → bucket-representative midpoint
    label, mid = lifestage_size(size_text, *sources)
    if mid is not None:
        return (size_text or label), None, None, mid
    return size_text, None, None, None


# Phrases that signal a FULL-GROWN / ultimate size rather than the size of the
# specimen actually being sold. Kept broad on purpose: when the only size in a
# body sits in one of these contexts, returning None (Unknown) beats stamping a
# listing — often a $8 sling — with the species' adult leg span. Covers the
# label forms ("Adult Size:", "Full Grown Size:") AND the prose forms
# ("grows to 6\"", "grow to be about 5-6 inches", "can reach 6\"", "leg span").
_ADULT_SIZE_CTX = re.compile(
    r'full[\s-]?grown|fully\s+grown|adult\s*(?:size|leg\s*span)|'
    r'matures?\s*(?:to|at|size)|max(?:imum)?\s*size|ultimate\s*size|'
    r'grows?\s*(?:up\s*)?to|grow\s*to\s*be|can\s*(?:grow|reach|get)|'
    r'reach(?:es)?\b|leg\s*span',
    re.I,
)


def extract_size_from_description(text: Optional[str]) -> Optional[str]:
    """Pull the CURRENT size out of a product description body.

    Vendor descriptions often list two sizes — "Current Size: Approximately 3/4\""
    and "Full Grown Size: Approximately 5-6\"" — and we want the *current* one.
    So we prefer a "current size" label, then a plain "size:" line that is NOT a
    full-grown / adult / mature line, and only then a bare size token — but only
    when the body has no full-grown / grows-to / leg-span phrasing that would
    make a bare token ambiguous with the species' adult size.
    """
    if not text:
        return None
    import html as _html
    t = _html.unescape(re.sub(r"<[^>]+>", " ", text))
    t = re.sub(r"\s+", " ", t)

    # A labelled window like "Current Size: Approximately 3/4\"" can bleed into the
    # next field ("… 3/4\" Full Grown Size: 5-6\"") within the char budget. Take the
    # FIRST size token in the window — right after the label — not the last.
    def _first_tok(snippet):
        mm = _SIZE_IN_TITLE.search(snippet or "")
        return extract_size_from_title(mm.group(0)) if mm else None

    # 1. explicit "current size" (or "size now") label
    m = re.search(r'\b(?:current\s*size|size\s*now|approx(?:imate)?\s*size)\s*[:\-]?\s*'
                  r'(?:approx(?:imately)?\.?\s*)?([^<\n.;,]{1,28})', t, re.I)
    if m:
        tok = _first_tok(m.group(1))
        if tok:
            return tok
    # 2. a generic "size:" that isn't a full-grown / adult / grows-to line
    for m in re.finditer(r'\bsize\s*[:\-]\s*(?:approx(?:imately)?\.?\s*)?([^<\n.;,]{1,28})', t, re.I):
        pre = t[max(0, m.start() - 18):m.start()].lower()
        if any(w in pre for w in ("full grown", "full-grown", "adult", "mature",
                                  "max", "grown", "grow", "reach", "leg span")):
            continue
        tok = _first_tok(m.group(1))
        if tok:
            return tok
    # 3. no size label at all, but if the body never mentions a full-grown / adult
    # / grows-to / leg-span size (so there's no ambiguity), take the FIRST size
    # token it does contain ("… Field Collected Approximately 3 – 4 Inches").
    if not _ADULT_SIZE_CTX.search(t):
        first = _SIZE_IN_TITLE.search(t)
        if first:
            tok = extract_size_from_title(first.group(0))
            if tok:
                return tok
    return None


def price_per_inch(price: float, size_midpoint: Optional[float]) -> Optional[float]:
    if size_midpoint and size_midpoint > 0:
        return round(price / size_midpoint, 2)
    return None


def size_category(min_inches: Optional[float]) -> str:
    if min_inches is None:
        return "Unknown"
    if min_inches < 0.75:
        return "Sling"
    if min_inches < 2.0:
        return "Juvenile"
    if min_inches < 4.0:
        return "Sub-adult"
    return "Adult"
