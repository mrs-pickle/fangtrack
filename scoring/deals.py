"""
Deal rating engine for the Tarantula Market Tracker.

Ratings:
  💎💎  Exceptional Deal  -- >= 20% below median, historical low, or exceptional value
  💎   Strong Deal        -- 10-20% below median
  👍   Fair Market Price  -- within ~10% of median
  👎   Above Market       -- > 10-15% above median without justification

Comparisons are strictly market-based, not personal preference.
Matching rules:
  - Same normalized taxon (scientific_name_key)
  - Same sex GROUP (female / male / mature male / unsexed treated separately)
  - Female vs unsexed NEVER compared as equivalent
  - Mature male vs juvenile NEVER compared as equivalent
  - Similar size (+/- 0.75 inch when size is known)
  - Source type (CB / WC / unknown) is NOT a matching dimension. Most vendors
    never state a source, so splitting on it would knock the majority of honest
    listings out of contention. CB/WC is shown as information only and carries
    zero weight in the score. See _comparison_key.
"""
import statistics
from typing import Optional
from models import Listing, DealRating, Sex


def score_all_listings(listings: list[Listing]) -> list[Listing]:
    """
    Score every listing in the dataset against its peers.
    Modifies listings in place, returns the same list.
    """
    # Build comparison groups
    groups: dict[str, list[Listing]] = {}

    for listing in listings:
        key = _comparison_key(listing)
        groups.setdefault(key, []).append(listing)

    # Score each listing within its group
    for group_key, group in groups.items():
        _score_group(group)

    return listings


def _comparison_key(listing) -> str:
    """
    Build a grouping key for deal comparison:
    same taxon + same sex group + similar size bucket.

    Source type (CB/WC/unknown) is deliberately NOT part of the key — see the
    note below the parse. Accepts both Listing dataclass objects and plain dicts.
    """
    if isinstance(listing, dict):
        taxon       = listing.get("scientific_name_key") or (listing.get("scientific_name") or "").lower().strip()
        sex         = listing.get("sex") or "U"
        size_mid    = listing.get("size_midpoint")
        sex_group   = _sex_group_from_code(sex)
        source_type = listing.get("source_type") or "unknown"
    else:
        taxon       = listing.scientific_name_key or listing.scientific_name.lower().strip()
        sex_group   = listing.sex_group()
        size_mid    = listing.size_midpoint
        source_type = getattr(listing, "source_type", "unknown") or "unknown"

    size_bucket = _size_bucket(size_mid)

    # NOTE: source type (CB/WC) is intentionally NOT part of the comparison key.
    # The inferred CB/WC signal is too weak to price on today, so it is shown to
    # the user as information only and carries ZERO weight in deal scoring. When
    # vendors submit structured source data via the API we will re-introduce it
    # as a real pool. (Size stays a comparison dimension.)
    return f"{taxon}|{sex_group}|{size_bucket}"


def _sex_group_from_code(sex: str) -> str:
    """Map sex code to comparison group."""
    if sex in ("F",):          return "female"
    if sex in ("PF",):         return "probable_female"
    if sex in ("M", "MM"):     return "male"
    return "unsexed"


# ── Eight life-stage size buckets ────────────────────────────────────────────
# Adult range split into three to capture meaningful price separation.
# A 4" confirmed female GBB and a 7" Theraphosa blondi are different markets.
#
#  Bucket      Range         Typical listing description
#  ----------  ------------- -------------------------------------------------
#  xs          < 0.33"       Neonates, N1-N2 instars (listed as 1/8")
#  sling       0.33-0.75"    Spiderlings (listed as 1/4" to 1/2")
#  starter     0.75-1.5"     Well-started juvies (listed as 3/4" to 1.25")
#  juvenile    1.5-2.5"      Juveniles, becoming sexable
#  subadult    2.5-4.0"      Sub-adults, clearly sexable
#  adult_sm    4.0-5.5"      Adults of small/medium species (GBB, P. metallica)
#  adult_md    5.5-7.0"      Adults of medium-large species (L. parahybana)
#  adult_lg    7.0"+         Adults of large species (Theraphosa)

# Life-stage brackets fit to the collected data (July 2026): the catalog is
# dominated by <1" slings and 1-3" juveniles, thinning out through the adult
# range. Five brackets keep each populated while still comparing like with like.
SIZE_BUCKET_BREAKS = [
    (0.75, "sling"),      # spiderlings         (< 0.75")
    (1.75, "juvenile"),   # juveniles           (0.75-1.75")
    (3.00, "subadult"),   # sub-adults          (1.75-3")
    (5.00, "adult"),      # adults              (3-5")
]

SIZE_BUCKET_LABELS = {
    "sling":    'Sling (<0.75")',
    "juvenile": 'Juvenile (0.75-1.75")',
    "subadult": 'Sub-adult (1.75-3")',
    "adult":    'Adult (3-5")',
    "large":    'Large adult (5"+)',
    "unknown":  "Unknown",
}


def _size_bucket(midpoint):
    """
    Assign a life-stage size bucket from the midpoint in inches.
    Sizes above ~13" are almost always a parse error (no theraphosid is that
    large), so they're treated as unknown rather than a bogus "giant" bucket.
    """
    if midpoint is None or midpoint <= 0 or midpoint > 13:
        return "unknown"
    for threshold, label in SIZE_BUCKET_BREAKS:
        if midpoint < threshold:
            return label
    return "large"


def _get(l, attr, default=None):
    """Get attribute from Listing object or dict."""
    if isinstance(l, dict):
        return l.get(attr, default)
    return getattr(l, attr, default)


def _set(l, attr, value):
    """Set attribute on Listing object or dict."""
    if isinstance(l, dict):
        l[attr] = value
    else:
        setattr(l, attr, value)


def _score_group(group: list) -> None:
    """
    Score all listings in a single comparison group.
    Only uses in-stock listings for median calculation.
    Accepts both Listing dataclass objects and plain dicts.
    """
    available = [l for l in group if _get(l, "availability") != "out_of_stock"]
    prices = [_get(l, "price_usd") for l in available if (_get(l, "price_usd") or 0) > 0]

    if not prices:
        for l in group:
            _set(l, "deal_rating", None)
            _set(l, "deal_reason", "Insufficient data for comparison")
        return

    median_price = statistics.median(prices)
    min_price = min(prices)
    # Historical low from the listing's own field if pre-populated
    # (set by DB lookup before scoring)

    for listing in group:
        _set(listing, "market_average", round(median_price, 2))
        _set(listing, "current_lowest_price", round(min_price, 2))

        if _get(listing, "availability") == "out_of_stock":
            _set(listing, "deal_rating", None)
            _set(listing, "deal_reason", "Out of stock")
            continue

        price = _get(listing, "price_usd")
        if not price or price <= 0:
            continue

        # Calculate deviation from median
        pct_above = (price - median_price) / median_price * 100  # positive = above market
        pct_below = -pct_above  # positive = below market

        # Historical low check
        hist_low = _get(listing, "historical_low")
        is_historical_low = hist_low is not None and price is not None and price <= hist_low

        # Build rating
        qty = _get(listing, "quantity")
        qty_note = " — only 1 available" if qty == 1 else (f" — {qty} available" if qty and qty <= 3 else "")

        # Exceptional requires a real MARKET discount — not merely "matches its
        # own historical low", which is vacuous for a species/sex we've only
        # seen once. A historical low reinforces an already below-market price.
        if pct_below >= 20 or (is_historical_low and pct_below >= 10):
            _set(listing, "deal_rating", DealRating.EXCEPTIONAL)
            reasons = [f"{pct_below:.0f}% below market median (${median_price:.2f})"]
            if is_historical_low:
                reasons.append("matches or beats historical low")
            _set(listing, "deal_reason", "; ".join(reasons).capitalize() + qty_note)

        elif pct_below >= 10:
            _set(listing, "deal_rating", DealRating.STRONG)
            _set(listing, "deal_reason", f"{pct_below:.0f}% below market median (${median_price:.2f}) among {len(available)} comparable listings")

        elif pct_above <= 10:
            _set(listing, "deal_rating", DealRating.FAIR)
            _set(listing, "deal_reason", f"Within {abs(pct_above):.0f}% of market median (${median_price:.2f})")

        else:
            _set(listing, "deal_rating", DealRating.ABOVE_MARKET)
            _set(listing, "deal_reason", f"{pct_above:.0f}% above market median (${median_price:.2f}) -- {len(available)} comparable listings found")

        # Override to exceptional if it's the single cheapest confirmed female in dataset
        if (
            len(available) >= 2
            and _get(listing, "sex") == Sex.FEMALE
            and _get(listing, "size_midpoint") is not None
            and price == min_price
            and pct_below >= 15
        ):
            _set(listing, "deal_rating", DealRating.EXCEPTIONAL)
            _set(listing, "deal_reason", f"Lowest confirmed female price in dataset; {pct_below:.0f}% below comparable median")

        # ── Confidence gate ──────────────────────────────────────────────────
        # A top rating (💎/💎💎) is only trustworthy when the comparison is
        # like-for-like. If SIZE is unknown, or there is only a single listing
        # in the group (so it is being compared against itself), we cannot
        # verify a real discount — cap the rating at Fair. This stops unknown
        # size/sex listings from all lighting up as exceptional deals.
        size_known = _get(listing, "size_midpoint") is not None
        confident = size_known and len(prices) >= 2
        if not confident and _get(listing, "deal_rating") in (
            DealRating.EXCEPTIONAL, DealRating.STRONG
        ):
            _set(listing, "deal_rating", DealRating.FAIR)
            if not size_known:
                _set(listing, "deal_reason",
                     "Size not listed — can't confirm a like-for-like discount; shown at market")
            else:
                _set(listing, "deal_reason",
                     "Only one comparable listing — not enough data to rank as a deal")


# ──────────────────────────────────────────────────────────────────────────────
# rate_all — called by pipeline.py after each crawl
# ──────────────────────────────────────────────────────────────────────────────

def rate_all(snapshot: list, history_lows: dict) -> list:
    """
    Main entry point called by pipeline after each crawl.

    1. Annotates each listing with its all-time historical low price
       from `history_lows` dict: {(species_key, sex): min_price}
    2. Sets is_new_historical_low if current price beats the all-time low
    3. Runs deal scoring across the full snapshot

    Works with both Listing dataclass objects and plain dicts.
    """
    for l in snapshot:
        is_dict = isinstance(l, dict)

        key   = l.get("scientific_name_key")  if is_dict else l.scientific_name_key
        sex   = (l.get("sex") or "U")         if is_dict else (l.sex or "U")
        price = l.get("price_usd", 0)         if is_dict else l.price_usd

        if not key or not price:
            continue

        # Look up historical low for this species+sex, fall back to unsexed
        hist_low = history_lows.get((key, sex)) or history_lows.get((key, "U"))
        if hist_low is None:
            continue

        is_new_low = price <= hist_low

        if is_dict:
            l["historical_low"]        = hist_low
            l["is_new_historical_low"] = is_new_low
        else:
            l.historical_low        = hist_low
            l.is_new_historical_low = is_new_low

    # Score the annotated snapshot
    score_all_listings(snapshot)
    return snapshot


# ──────────────────────────────────────────────────────────────────────────────
# 🔥 FIRE DEAL FLAG
# All-time lowest TOTAL LANDED COST (price + shipping) ever seen in the system
# Supersedes 💎💎 as the top-tier signal when it fires.
# ──────────────────────────────────────────────────────────────────────────────

def compute_fire_deals(listings: list,
                        shipping_lookup: dict,
                        dest_zip: str = "00000",
                        db_path=None) -> None:
    """
    For each listing, compute landed_cost = price + vendor_shipping_rate.
    Compare against all-time minimum landed cost for the same species/sex/size_bucket.
    Set is_fire_deal=True and fire_reason when current landed cost = all-time low.

    Parameters
    ----------
    listings : list of dicts or Listing objects
    shipping_lookup : dict from get_all_shipping()  {vendor_key: {...}}
    dest_zip : destination zip (affects display; most vendors use flat rates)
    db_path : DB path for historical query
    """
    if db_path is None:
        from database.db import DB_PATH
        db_path = DB_PATH

    from database.db import get_connection
    from pathlib import Path

    conn = get_connection(Path(db_path))
    cur = conn.cursor()

    # Build lookup of all-time min (price + shipping) per species/sex/size_bucket
    # We approximate historical landed cost as price + that vendor's flat_rate
    cur.execute("""
        SELECT
            ph.scientific_name_key,
            ph.sex,
            ph.size_midpoint,
            ph.price_usd,
            ph.vendor_key,
            CASE
                WHEN ph.size_midpoint IS NULL THEN 'unknown'
                WHEN ph.size_midpoint < 0.5   THEN 'xs'
                WHEN ph.size_midpoint < 1.0   THEN 'sling'
                WHEN ph.size_midpoint < 2.0   THEN 'juvenile'
                WHEN ph.size_midpoint < 3.5   THEN 'subadult'
                WHEN ph.size_midpoint < 5.5   THEN 'adult_sm'
                ELSE 'adult_lg'
            END as size_bucket
        FROM price_history ph
        WHERE ph.price_usd > 0
    """)
    rows = cur.fetchall()
    conn.close()

    # Historical landed cost minimums: {(species_key, sex, size_bucket): min_landed}
    # and a count of distinct observations per bucket, so a bucket that has only
    # ever been seen once can't declare itself an "all-time low".
    hist_landed: dict[tuple, float] = {}
    hist_vendors: dict[tuple, set] = {}
    _UNKNOWN_SEX = {"U", "Unknown", "", None}
    for row in rows:
        vk   = row["vendor_key"]
        ship = shipping_lookup.get(vk, {})
        flat = ship.get("flat_rate") or 35.0  # default estimate
        free_at = ship.get("free_threshold")
        # Assume single-animal order (worst-case shipping)
        ship_cost = 0.0 if (free_at and row["price_usd"] >= free_at) else flat
        landed = float(row["price_usd"]) + ship_cost

        key = (row["scientific_name_key"], row["sex"] or "U", row["size_bucket"])
        hist_vendors.setdefault(key, set()).add(vk)
        if key not in hist_landed or landed < hist_landed[key]:
            hist_landed[key] = landed

    # Annotate each listing
    for l in listings:
        is_dict = isinstance(l, dict)

        vk      = l.get("vendor_key")        if is_dict else getattr(l, "vendor_key", None)
        key     = l.get("scientific_name_key") if is_dict else getattr(l, "scientific_name_key", None)
        sex     = (l.get("sex") or "U")      if is_dict else (getattr(l, "sex", None) or "U")
        price   = l.get("price_usd", 0)      if is_dict else getattr(l, "price_usd", 0)
        size_mid= l.get("size_midpoint")      if is_dict else getattr(l, "size_midpoint", None)

        if not key or not price:
            if is_dict: l["is_fire_deal"] = False
            continue

        # Compute current landed cost
        ship    = shipping_lookup.get(vk, {})
        flat    = ship.get("flat_rate") or 35.0
        free_at = ship.get("free_threshold")
        ship_cost = 0.0 if (free_at and price >= free_at) else flat
        landed  = price + ship_cost

        # Size bucket
        if size_mid is None:    sb = "unknown"
        elif size_mid < 0.5:    sb = "xs"
        elif size_mid < 1.0:    sb = "sling"
        elif size_mid < 2.0:    sb = "juvenile"
        elif size_mid < 3.5:    sb = "subadult"
        elif size_mid < 5.5:    sb = "adult_sm"
        else:                    sb = "adult_lg"

        hist_key = (key, sex, sb)
        hist_min = hist_landed.get(hist_key)
        # A fire deal is the lowest delivered cost in a bucket we can actually
        # compare: size AND sex must be known, and the bucket must be offered by
        # at least TWO DISTINCT vendors (real cross-market competition).
        # Otherwise a first/only sighting, an unknown size/sex, or a single
        # vendor's duplicate listings would trivially be their own record.
        comparable = (
            size_mid is not None
            and sex not in _UNKNOWN_SEX
            and len(hist_vendors.get(hist_key, ())) >= 2
        )
        is_fire = (
            comparable
            and hist_min is not None
            and landed <= hist_min * 1.01  # within 1% of record
        )

        reason = None
        if is_fire:
            reason = (
                f"🔥 All-time lowest delivered cost: ${landed:.2f} shipped "
                f"(${price:.2f} + ${ship_cost:.2f} shipping to {dest_zip})"
            )

        if is_dict:
            l["is_fire_deal"]     = is_fire
            l["landed_cost"]      = round(landed, 2)
            l["shipping_share"]   = ship_cost
            l["fire_reason"]      = reason
        else:
            setattr(l, "is_fire_deal",   is_fire)
            setattr(l, "landed_cost",    round(landed, 2))
            setattr(l, "shipping_share", ship_cost)
            setattr(l, "fire_reason",    reason)
