"""
Price Trend Engine
Computes price direction over time for each (species, sex, size_bucket).

Returns:
  ↑  rising    — price trending upward vs prior period
  ↓  falling   — price trending downward (possible buy signal)
  →  stable    — price not moving significantly
  ?  new        — insufficient data (< 2 time points)

Trend is computed using simple linear regression on observed prices
over time, normalized by the median price to get percentage velocity.

Requires at least 2 distinct crawl dates for a (species, size_bucket) pair.
Meaningful results come after 3-4 weeks of regular crawls.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import statistics

from database.db import get_connection, DB_PATH


# ── THRESHOLDS ──────────────────────────────────────────────────────────────
RISING_THRESHOLD  =  5.0   # > +5% monthly velocity = rising
FALLING_THRESHOLD = -5.0   # < -5% monthly velocity = falling

TREND_EMOJI = {
    "rising":   "↑",
    "falling":  "↓",
    "stable":   "→",
    "new":      "?",
}

TREND_COLORS = {          # for Excel conditional formatting
    "rising":  "FFCDD2",  # light red
    "falling": "C8E6C9",  # light green (falling price = good for buyer)
    "stable":  "F5F5F5",  # near-white
    "new":     "FFFFFF",
}


def _linear_slope(xs: list[float], ys: list[float]) -> float:
    """Simple linear regression slope (Δy per unit x)."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den != 0 else 0.0


def compute_price_trends(db_path: Path = DB_PATH,
                          days_back: int = 90) -> dict[tuple, dict]:
    """
    Compute price trends for every (species_key, sex, size_bucket) combination
    that has at least 2 distinct observation dates.

    Returns dict: {(species_key, sex, size_bucket): trend_dict}
    where trend_dict has keys:
      direction:       'rising' | 'falling' | 'stable' | 'new'
      emoji:           '↑' | '↓' | '→' | '?'
      monthly_pct:     float — estimated % change per 30 days
      data_points:     int — number of distinct dates observed
      oldest_price:    float
      newest_price:    float
      oldest_date:     str
      newest_date:     str
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    size_case = """
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

    cur.execute(f"""
        SELECT
            scientific_name_key,
            sex,
            {size_case} AS size_bucket,
            AVG(price_usd)     AS avg_price,
            MIN(price_usd)     AS min_price,
            observed_at
        FROM price_history
        WHERE price_usd > 0
          AND observed_at >= datetime('now', '-{days_back} days')
        GROUP BY scientific_name_key, sex, size_bucket,
                 DATE(observed_at)   -- one data point per day
        ORDER BY observed_at ASC
    """)

    rows = cur.fetchall()
    conn.close()

    # Group by (species, sex, size_bucket) → list of (day_number, avg_price)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    groups: dict[tuple, list[tuple[float, float, str]]] = {}
    for row in rows:
        key = (row["scientific_name_key"], row["sex"] or "U", row["size_bucket"])
        obs_str = row["observed_at"][:10]
        try:
            obs_dt = datetime.fromisoformat(obs_str).replace(tzinfo=timezone.utc)
            day_num = (obs_dt - now).days  # negative = past
        except Exception:
            continue
        groups.setdefault(key, []).append((day_num, float(row["avg_price"]), obs_str))

    results = {}
    for key, points in groups.items():
        n = len(points)
        if n < 2:
            results[key] = {
                "direction":    "new",
                "emoji":        "?",
                "monthly_pct":  None,
                "data_points":  n,
                "oldest_price": points[0][1] if points else None,
                "newest_price": points[-1][1] if points else None,
                "oldest_date":  points[0][2] if points else None,
                "newest_date":  points[-1][2] if points else None,
            }
            continue

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        slope = _linear_slope(xs, ys)  # $ per day
        median_p = statistics.median(ys)
        # Convert to % per 30 days
        monthly_pct = (slope * 30 / median_p * 100) if median_p > 0 else 0

        if monthly_pct > RISING_THRESHOLD:
            direction = "rising"
        elif monthly_pct < FALLING_THRESHOLD:
            direction = "falling"
        else:
            direction = "stable"

        results[key] = {
            "direction":    direction,
            "emoji":        TREND_EMOJI[direction],
            "monthly_pct":  round(monthly_pct, 1),
            "data_points":  n,
            "oldest_price": round(points[0][1], 2),
            "newest_price": round(points[-1][1], 2),
            "oldest_date":  points[0][2],
            "newest_date":  points[-1][2],
        }

    return results


def annotate_with_trends(listings: list, db_path: Path = DB_PATH) -> None:
    """
    Add price_trend, trend_emoji, trend_monthly_pct, trend_data_points
    to each listing dict or Listing object. Modifies in place.
    """
    from scoring.deals import _size_bucket
    trends = compute_price_trends(db_path)

    for l in listings:
        is_dict = isinstance(l, dict)
        key = l.get("scientific_name_key") if is_dict else getattr(l, "scientific_name_key", None)
        sex = (l.get("sex") or "U")         if is_dict else (getattr(l, "sex", None) or "U")
        mid = l.get("size_midpoint")         if is_dict else getattr(l, "size_midpoint", None)
        if not key:
            continue
        sb = _size_bucket(mid)
        td = trends.get((key, sex, sb)) or trends.get((key, "U", sb)) or {}

        direction   = td.get("direction", "new")
        emoji       = td.get("emoji", "?")
        monthly_pct = td.get("monthly_pct")
        n_points    = td.get("data_points", 0)

        if is_dict:
            l["price_trend"]         = direction
            l["trend_emoji"]         = emoji
            l["trend_monthly_pct"]   = monthly_pct
            l["trend_data_points"]   = n_points
        else:
            setattr(l, "price_trend",       direction)
            setattr(l, "trend_emoji",       emoji)
            setattr(l, "trend_monthly_pct", monthly_pct)
            setattr(l, "trend_data_points", n_points)
