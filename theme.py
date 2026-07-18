"""
FangTrack design tokens — THE single source of truth for rarity colours.

Why this file exists
--------------------
Rarity tier colours used to be duplicated across templates/base.html and
analytics/market.py. They drifted, and Rare + Legendary ended up sharing the
same background (#7c3aed) — which also silently mis-coloured badges in two
templates. Colours are now defined exactly ONCE, here, and everything else
derives from this module:

  * templates/base.html renders `{{ rarity_css()|safe }}` (injected by the app's
    context processor) — it no longer hard-codes a single rarity hex.
  * analytics/market.py imports RARITY_TIERS for the tier→css-class map, the
    percentile bands, and the dashboard "Standouts" pills.

If you change a rarity colour, change it HERE and nowhere else.

The system (not a list)
-----------------------
Every tier is a Tailwind ramp pair: the background is a ~600-800 step of a hue,
and the text is the ~200-300 step of the SAME hue. To add a tier, pick an unused
hue, take its 600-800 step for `bg` and the 200-300 step of that same hue for
`text`, and make sure the new `bg` collides with nothing (see tests).

The ladder is the classic trading-card rarity ramp, low -> high:
  slate -> green -> sky -> indigo -> fuchsia -> orange.
No rarity background equals any DEAL_BADGES background — the two systems are read
in different columns and must never share a colour (the test enforces this).

DANGER — overloaded hexes
-------------------------
#7c3aed (violet-600) now belongs EXCLUSIVELY to the Exceptional 💎💎 DEAL badge.
It must never be a rarity colour again. DEAL_BADGES below exists so the test
suite can assert no rarity background ever collides with a deal background.
"""
from __future__ import annotations

# ── Rarity tiers: rarest → most common ──────────────────────────────────────
# bg   = Tailwind 600-800 step   |   text = 200-300 step of the SAME hue
RARITY_TIERS: dict[str, dict] = {
    "Mythic": {
        "bg": "#c2410c", "text": "#fed7aa",          # orange-700 / orange-200
        "label": "MYTHIC", "css": "r-mythic",
        "scores": (9, 10), "band": 0.05,
    },
    "Legendary": {
        "bg": "#a21caf", "text": "#f5d0fe",          # fuchsia-700 / fuchsia-200
        "label": "LEGEND", "css": "r-veryr",
        "scores": (8,), "band": 0.15,
    },
    "Rare": {
        "bg": "#4338ca", "text": "#c7d2fe",          # indigo-700 / indigo-200
        "label": "RARE", "css": "r-rare",
        "scores": (7,), "band": 0.30,
    },
    "Uncommon": {
        "bg": "#0369a1", "text": "#bae6fd",          # sky-700 / sky-200
        "label": "UNCOMMON", "css": "r-uncomm",
        "scores": (5, 6), "band": 0.55,
    },
    "Common": {
        "bg": "#15803d", "text": "#bbf7d0",          # green-700 / green-200
        "label": "COMMON", "css": "r-common",
        "scores": (3, 4), "band": 0.80,
    },
    "Ubiquitous": {
        "bg": "#475569", "text": "#cbd5e1",          # slate-600 / slate-300
        "label": "UBIQ", "css": "r-ubiq",
        "scores": (1, 2), "band": 1.01,
    },
}

# Rarest → most common. The canonical order for legends, facets and sorting.
TIER_ORDER: list[str] = list(RARITY_TIERS.keys())

# ── Deal badges — a DIFFERENT system. Defined here only so the tests can prove
# no rarity colour ever collides with one. Their CSS still lives in base.html.
DEAL_BADGES: dict[str, dict] = {
    "fire":        {"bg": "#ff6b00", "text": "#ffffff"},   # 🔥
    "exceptional": {"bg": "#7c3aed", "text": "#f0f0f0"},   # 💎💎  violet-600
    "strong":      {"bg": "#1d4ed8", "text": "#bfdbfe"},   # 💎
    "fair":        {"bg": "#065f46", "text": "#a7f3d0"},   # 👍
    "above":       {"bg": "#374151", "text": "#9ca3af"},   # 👎
}

# ── Derived lookups ─────────────────────────────────────────────────────────
SCORE_TO_TIER: dict[int, str] = {
    s: name for name, t in RARITY_TIERS.items() for s in t["scores"]
}

# Percentile bands (most-common last) for catalog_rarity_tiers().
TIER_BANDS: list[tuple[float, str, str]] = [
    (t["band"], name, t["css"]) for name, t in RARITY_TIERS.items()
]

# 52-week range bar: the rarity ladder itself, low → high. Ubiquitous (gray) is
# omitted — the bar is a price ramp and starts at the first chromatic step.
# => emerald → blue → indigo → fuchsia → orange
RANGE_BAR_GRADIENT: str = "linear-gradient(90deg," + ",".join(
    RARITY_TIERS[n]["bg"] for n in reversed(TIER_ORDER) if n != "Ubiquitous"
) + ")"


def tier_for_score(score) -> str:
    """1-10 rarity score → tier name ('' when unknown)."""
    try:
        return SCORE_TO_TIER.get(int(score), "")
    except (TypeError, ValueError):
        return ""


def rarity_css() -> str:
    """The ONLY place rarity colours become CSS.

    Emits, for all six tiers:
      * custom properties  --rarity-<slug>-bg / --rarity-<slug>-text
      * the tier classes   .r-mythic … .r-ubiq
      * the score classes  .score-1 … .score-10 (score → its tier's colours)
      * the range-bar gradient
    """
    lines: list[str] = []

    lines.append(":root {")
    for name, t in RARITY_TIERS.items():
        slug = name.lower()
        lines.append(f"  --rarity-{slug}-bg:{t['bg']}; --rarity-{slug}-text:{t['text']};")
    lines.append("}")

    for name, t in RARITY_TIERS.items():
        slug = name.lower()
        lines.append(
            f".{t['css']} {{ background:var(--rarity-{slug}-bg); "
            f"color:var(--rarity-{slug}-text); }}"
        )

    for name, t in RARITY_TIERS.items():
        slug = name.lower()
        sel = ",".join(f".score-{s}" for s in t["scores"])
        lines.append(
            f"{sel} {{ background:var(--rarity-{slug}-bg); "
            f"color:var(--rarity-{slug}-text); }}"
        )

    lines.append(
        ".rangebar { position:relative; height:8px; border-radius:5px; "
        f"background:{RANGE_BAR_GRADIENT}; }}"
    )
    return "\n".join(lines)
