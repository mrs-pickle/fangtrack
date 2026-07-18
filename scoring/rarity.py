"""
Rarity Score Engine
Assigns each species a 1-10 rarity score based on how available it is
across all vendors and historical observations in the DB.

Scale:
  10  ── Never seen before / single source, single sighting, premium price
   9  ── Extremely rare: 1 source total, few observations
   8  ── Very rare: 1-2 sources ever
   7  ── Uncommon: 2-3 sources
   6  ── Somewhat uncommon: 3-4 sources
   5  ── Moderate: 4-6 sources
   4  ── Fairly common: 6-9 sources
   3  ── Common: 9-13 sources
   2  ── Very common: 13-19 sources
   1  ── Ubiquitous: 19+ sources (Curly Hair / Salmon Pink tier)

Score is RELATIVE to the dataset and self-calibrates as more crawls run.
After a full 26-vendor crawl history, scores will spread more evenly.

Special flag:
  new_to_system = True  →  species has NEVER appeared in any prior crawl run
                            (only in the current batch). Shown as "🆕 NEW"

Rarity labels:
  10: 🔬 Scientific Specimen    (possibly first time ever listed)
  9:  🌑 Extreme Rarity
  8:  💜 Very Rare
  7:  🔵 Rare
  6:  🟣 Uncommon
  5:  🟢 Moderately Available
  4:  🟡 Common
  3:  🟠 Widely Available
  2:  ⚪ Very Common
  1:  ⚫ Ubiquitous
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from database.db import get_connection, DB_PATH


@dataclass
class RarityData:
    species_key:     str
    score:           int              # 1-10
    label:           str
    vendor_count:    int              # unique vendors that have ever listed it
    obs_count:       int              # total observations in price_history
    first_seen:      Optional[str]    # ISO date of first recorded observation
    last_seen:       Optional[str]    # ISO date of most recent observation
    last_price:      Optional[float]  # price at most recent observation
    last_vendor:     Optional[str]    # vendor at most recent observation
    current_vendors: list[str]        # vendors with it in their LATEST crawl
    new_to_system:   bool = False     # True = never seen in any prior crawl
    days_since_last: Optional[int] = None


RARITY_LABELS = {
    10: "🔬 Scientific Specimen",
    9:  "🌑 Extreme Rarity",
    8:  "💜 Very Rare",
    7:  "🔵 Rare",
    6:  "🟣 Uncommon",
    5:  "🟢 Mod. Available",
    4:  "🟡 Common",
    3:  "🟠 Widely Available",
    2:  "⚪ Very Common",
    1:  "⚫ Ubiquitous",
}


def _vendor_anchor(vendor_count: int) -> int:
    """Primary rarity signal: unique vendor count → anchor score."""
    if vendor_count >= 20: return 1
    if vendor_count >= 15: return 2
    if vendor_count >= 10: return 3
    if vendor_count >= 7:  return 4
    if vendor_count >= 5:  return 5
    if vendor_count >= 4:  return 6
    if vendor_count >= 3:  return 7
    if vendor_count >= 2:  return 8
    return 9  # 1 vendor


def _obs_modifier(obs_count: int) -> int:
    """Secondary signal: total observation density."""
    if obs_count >= 40: return -2
    if obs_count >= 20: return -1
    if obs_count >= 8:  return  0
    if obs_count >= 4:  return  1
    return 2  # 1-3 sightings: very little data, push toward rare


def _price_modifier(min_price: Optional[float], obs_count: int) -> int:
    """Price-as-rarity-signal. Only applied when obs < 10 (thin data)."""
    if obs_count >= 10 or min_price is None:
        return 0
    if min_price >= 300:  return  1
    if min_price >= 150:  return  0
    if min_price <= 20:   return -1
    return 0


def _recency_modifier(days_since_last: Optional[int]) -> int:
    """Species not seen in a while are harder to find — slightly rarer."""
    if days_since_last is None:    return 0
    if days_since_last > 365:      return 2   # gone over a year
    if days_since_last > 180:      return 1   # gone 6+ months
    if days_since_last < 7:        return -1  # very current stock
    return 0


def compute_rarity_score(vendor_count: int, obs_count: int,
                          min_price: Optional[float],
                          days_since_last: Optional[int],
                          new_to_system: bool) -> int:
    """Combine all signals into a 1-10 rarity score."""
    if new_to_system:
        # Seen for the first time ever in this crawl — floor at 8
        return max(8, min(10,
            _vendor_anchor(vendor_count)
            + _obs_modifier(obs_count)
            + _price_modifier(min_price, obs_count)
        ))
    score = (
        _vendor_anchor(vendor_count)
        + _obs_modifier(obs_count)
        + _price_modifier(min_price, obs_count)
        + _recency_modifier(days_since_last)
    )
    return max(1, min(10, score))


def compute_all_rarity(db_path: Path = DB_PATH,
                        current_run_ids: list[int] = None) -> dict[str, RarityData]:
    """
    Compute rarity scores for every species in the DB.

    Parameters
    ----------
    current_run_ids : list[int], optional
        If provided, any species ONLY appearing in these run IDs
        (and not in any earlier run) is flagged new_to_system=True.

    Returns
    -------
    dict mapping scientific_name_key → RarityData
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    now = datetime.now(timezone.utc)

    # --- Species aggregate stats ---
    cur.execute("""
        SELECT
            ph.scientific_name_key,
            MAX(ph.scientific_name)        AS scientific_name,
            COUNT(DISTINCT ph.vendor_key)  AS vendor_count,
            COUNT(*)                       AS obs_count,
            MIN(ph.price_usd)              AS min_price,
            MAX(ph.price_usd)              AS max_price,
            MIN(ph.observed_at)            AS first_seen,
            MAX(ph.observed_at)            AS last_seen
        FROM price_history ph
        WHERE ph.price_usd > 0
        GROUP BY ph.scientific_name_key
    """)
    stats = {r["scientific_name_key"]: dict(r) for r in cur.fetchall()}

    # --- Most recent price and vendor per species ---
    cur.execute("""
        SELECT ph.scientific_name_key, ph.vendor_key, ph.price_usd, ph.observed_at
        FROM price_history ph
        INNER JOIN (
            SELECT scientific_name_key, MAX(observed_at) AS max_obs
            FROM price_history
            GROUP BY scientific_name_key
        ) latest ON ph.scientific_name_key = latest.scientific_name_key
                 AND ph.observed_at = latest.max_obs
    """)
    latest = {}
    for r in cur.fetchall():
        k = r["scientific_name_key"]
        if k not in latest:
            latest[k] = {"vendor_key": r["vendor_key"],
                         "price_usd": float(r["price_usd"]),
                         "observed_at": r["observed_at"]}

    # --- Currently active: in the most recent crawl run per vendor ---
    cur.execute("""
        SELECT vendor_key, MAX(id) AS max_run
        FROM crawl_runs
        WHERE status IN ('complete', 'partial')
        GROUP BY vendor_key
    """)
    latest_runs = {r["vendor_key"]: r["max_run"] for r in cur.fetchall()}

    current_active: dict[str, list[str]] = {}   # key → [vendor_keys]
    if latest_runs:
        run_ids = list(latest_runs.values())
        placeholders = ",".join("?" * len(run_ids))
        cur.execute(f"""
            SELECT DISTINCT scientific_name_key, vendor_key
            FROM price_history
            WHERE crawl_run_id IN ({placeholders})
              AND availability != 'out_of_stock'
        """, run_ids)
        for r in cur.fetchall():
            current_active.setdefault(r["scientific_name_key"], []).append(r["vendor_key"])

    # --- New-to-system detection ---
    new_species: set[str] = set()
    if current_run_ids:
        placeholders = ",".join("?" * len(current_run_ids))
        # Species only appearing in current_run_ids and nowhere else
        cur.execute(f"""
            SELECT scientific_name_key
            FROM price_history
            GROUP BY scientific_name_key
            HAVING COUNT(DISTINCT CASE
                WHEN crawl_run_id IN ({placeholders}) THEN 1 ELSE NULL
            END) > 0
              AND COUNT(DISTINCT CASE
                WHEN crawl_run_id NOT IN ({placeholders}) THEN 1 ELSE NULL
            END) = 0
        """, current_run_ids + current_run_ids)
        new_species = {r["scientific_name_key"] for r in cur.fetchall()}

    conn.close()

    # --- Build RarityData for each species ---
    result = {}
    for key, s in stats.items():
        last_obs = s["last_seen"] or ""
        days_since = None
        if last_obs:
            try:
                last_dt = datetime.fromisoformat(last_obs.replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                days_since = (now - last_dt).days
            except Exception:
                pass

        new_flag  = key in new_species
        score     = compute_rarity_score(
            vendor_count   = s["vendor_count"],
            obs_count      = s["obs_count"],
            min_price      = s["min_price"],
            days_since_last= days_since,
            new_to_system  = new_flag,
        )
        lat = latest.get(key, {})

        result[key] = RarityData(
            species_key     = key,
            score           = score,
            label           = RARITY_LABELS[score],
            vendor_count    = s["vendor_count"],
            obs_count       = s["obs_count"],
            first_seen      = (s["first_seen"] or "")[:10],
            last_seen       = (s["last_seen"]  or "")[:10],
            last_price      = lat.get("price_usd"),
            last_vendor     = lat.get("vendor_key"),
            current_vendors = current_active.get(key, []),
            new_to_system   = new_flag,
            days_since_last = days_since,
        )

    return result


def annotate_listings_with_rarity(listings: list, db_path: Path = DB_PATH,
                                   current_run_ids: list[int] = None) -> None:
    """
    Add rarity_score, rarity_label, new_to_system, current_vendor_count,
    last_seen, last_seen_price to each listing (dict or Listing object).
    Modifies in place.
    """
    rarity = compute_all_rarity(db_path, current_run_ids)

    for l in listings:
        is_dict = isinstance(l, dict)
        key = l.get("scientific_name_key") if is_dict else getattr(l, "scientific_name_key", None)
        if not key:
            continue
        rd = rarity.get(key)
        if rd is None:
            continue

        if is_dict:
            l["rarity_score"]          = rd.score
            l["rarity_label"]          = rd.label
            l["new_to_system"]         = rd.new_to_system
            l["rarity_vendor_count"]   = rd.vendor_count
            l["rarity_current_sellers"]= len(rd.current_vendors)
            l["last_seen_date"]        = rd.last_seen
            l["last_seen_price"]       = rd.last_price
            l["last_seen_vendor"]      = rd.last_vendor
        else:
            l.rarity_score           = rd.score
            l.rarity_label           = rd.label
            l.new_to_system          = rd.new_to_system
            l.rarity_vendor_count    = rd.vendor_count
            l.rarity_current_sellers = len(rd.current_vendors)
            l.last_seen_date         = rd.last_seen
            l.last_seen_price        = rd.last_price
            l.last_seen_vendor       = rd.last_vendor


# ──────────────────────────────────────────────────────────────────────────────
# PER-SIZE-CLASS RARITY
# Answers "how hard is it to find THIS SPECIES at THIS SIZE/LIFE STAGE?"
# A species can be a 3/10 as slings but a 8/10 as confirmed adult females.
# ──────────────────────────────────────────────────────────────────────────────

from dataclasses import dataclass as _dc
from typing import Optional as _Opt


@_dc
class SizeClassRarity:
    species_key:  str
    size_bucket:  str
    size_label:   str
    score:        int
    label:        str
    vendor_count: int
    obs_count:    int
    min_price:    _Opt[float]
    max_price:    _Opt[float]
    last_seen:    _Opt[str]
    last_price:   _Opt[float]


SIZE_BUCKET_SQL = """
    CASE
        WHEN size_midpoint IS NULL    THEN 'unknown'
        WHEN size_midpoint < 0.33     THEN 'xs'
        WHEN size_midpoint < 0.75     THEN 'sling'
        WHEN size_midpoint < 1.50     THEN 'starter'
        WHEN size_midpoint < 2.50     THEN 'juvenile'
        WHEN size_midpoint < 4.00     THEN 'subadult'
        WHEN size_midpoint < 5.50     THEN 'adult_sm'
        WHEN size_midpoint < 7.00     THEN 'adult_md'
        ELSE 'adult_lg'
    END
"""

SIZE_BUCKET_DISPLAY = {
    "xs":       'Neonate  (<0.33")',
    "sling":    'Sling    (0.33-0.75")',
    "starter":  'Starter  (0.75-1.5")',
    "juvenile": 'Juvenile (1.5-2.5")',
    "subadult": 'Sub-adult (2.5-4.0")',
    "adult_sm": 'Adult S  (4.0-5.5")',
    "adult_md": 'Adult M  (5.5-7.0")',
    "adult_lg": 'Adult L  (7.0"+)',
    "unknown":  'Unknown',
}


def compute_size_class_rarity(db_path: Path = DB_PATH) -> dict[tuple, SizeClassRarity]:
    """
    Compute rarity for every (species_key, size_bucket) combination.
    Returns {(species_key, size_bucket): SizeClassRarity}

    This is the more actionable number for a buyer: knowing that G. pulchripes
    slings are widely available (score 3) but confirmed adult females are rare
    (score 7-8) changes purchasing strategy.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute(f"""
        SELECT
            scientific_name_key,
            {SIZE_BUCKET_SQL} AS size_bucket,
            COUNT(DISTINCT vendor_key)  AS vendor_count,
            COUNT(*)                    AS obs_count,
            MIN(price_usd)              AS min_price,
            MAX(price_usd)              AS max_price,
            MAX(observed_at)            AS last_seen
        FROM price_history
        WHERE price_usd > 0
          AND scientific_name_key IS NOT NULL
        GROUP BY scientific_name_key, size_bucket
        ORDER BY scientific_name_key, obs_count DESC
    """)

    rows = cur.fetchall()

    # Last price per (species, bucket)
    cur.execute(f"""
        SELECT ph.scientific_name_key,
               {SIZE_BUCKET_SQL} AS sb,
               ph.price_usd,
               ph.observed_at
        FROM price_history ph
        INNER JOIN (
            SELECT scientific_name_key,
                   {SIZE_BUCKET_SQL} AS size_bucket,
                   MAX(observed_at) AS max_obs
            FROM price_history
            GROUP BY scientific_name_key, size_bucket
        ) latest ON ph.scientific_name_key = latest.scientific_name_key
                 AND {SIZE_BUCKET_SQL} = latest.size_bucket
                 AND ph.observed_at = latest.max_obs
    """)
    last_prices: dict[tuple, float] = {}
    for row in cur.fetchall():
        k = (row["scientific_name_key"], row["sb"])
        last_prices[k] = float(row["price_usd"])

    conn.close()

    now = datetime.now(timezone.utc)
    result = {}

    for row in rows:
        sk  = row["scientific_name_key"]
        sb  = row["size_bucket"] or "unknown"
        vc  = row["vendor_count"]
        oc  = row["obs_count"]
        mp  = row["min_price"]
        mxp = row["max_price"]
        ls  = (row["last_seen"] or "")[:10]

        # Days since last seen
        days_since = None
        if ls:
            try:
                last_dt = datetime.fromisoformat(ls).replace(tzinfo=timezone.utc)
                days_since = (now - last_dt).days
            except Exception:
                pass

        score = compute_rarity_score(
            vendor_count    = vc,
            obs_count       = oc,
            min_price       = float(mp) if mp else None,
            days_since_last = days_since,
            new_to_system   = False,   # size-class new detection not needed here
        )

        result[(sk, sb)] = SizeClassRarity(
            species_key  = sk,
            size_bucket  = sb,
            size_label   = SIZE_BUCKET_DISPLAY.get(sb, sb),
            score        = score,
            label        = RARITY_LABELS[score],
            vendor_count = vc,
            obs_count    = oc,
            min_price    = float(mp) if mp else None,
            max_price    = float(mxp) if mxp else None,
            last_seen    = ls,
            last_price   = last_prices.get((sk, sb)),
        )

    return result


def annotate_with_size_class_rarity(listings: list,
                                     size_class_rarity: dict[tuple, SizeClassRarity]) -> None:
    """
    Add size_class_rarity_score, size_class_rarity_label, size_bucket,
    size_bucket_label to each listing dict/object.
    Uses the precomputed size_class_rarity dict for efficiency.
    """
    from scoring.deals import _size_bucket

    for l in listings:
        is_dict = isinstance(l, dict)
        sk  = l.get("scientific_name_key") if is_dict else getattr(l, "scientific_name_key", None)
        mid = l.get("size_midpoint")        if is_dict else getattr(l, "size_midpoint", None)
        if not sk:
            continue

        sb  = _size_bucket(mid)
        scr = size_class_rarity.get((sk, sb))

        bucket_label = SIZE_BUCKET_DISPLAY.get(sb, sb)

        if is_dict:
            l["size_bucket"]              = sb
            l["size_bucket_label"]        = bucket_label
            l["size_class_rarity_score"]  = scr.score       if scr else None
            l["size_class_rarity_label"]  = scr.label       if scr else None
            l["size_class_vendor_count"]  = scr.vendor_count if scr else None
            l["size_class_obs_count"]     = scr.obs_count   if scr else None
            l["size_class_last_seen"]     = scr.last_seen   if scr else None
            l["size_class_last_price"]    = scr.last_price  if scr else None
        else:
            setattr(l, "size_bucket",             sb)
            setattr(l, "size_bucket_label",       bucket_label)
            setattr(l, "size_class_rarity_score", scr.score        if scr else None)
            setattr(l, "size_class_rarity_label", scr.label        if scr else None)
            setattr(l, "size_class_vendor_count", scr.vendor_count if scr else None)
            setattr(l, "size_class_obs_count",    scr.obs_count    if scr else None)
            setattr(l, "size_class_last_seen",    scr.last_seen    if scr else None)
            setattr(l, "size_class_last_price",   scr.last_price   if scr else None)
