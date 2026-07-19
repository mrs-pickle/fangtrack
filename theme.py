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

The system (2026-07-19 rebrand, Mike-approved)
----------------------------------------------
Each tier has a single CORE colour on the hue ladder
    oklch(0.66 0.20 H),  H: 340 → 300 → 260 → 200 → 150, then neutral
    (pink → purple → blue → teal → green → gray, rarest → most common)
and the pill derives everything from the core:

    bg     = core @ 15% alpha          (10% in a light theme)
    text   = oklch(.78 .14 H)          (.45 .14 H in a light theme)
    border = core @ 35% alpha          (25% in a light theme)

To add a tier: pick the next hue on the ladder, apply the formula, and make
sure the CORE collides with nothing that shares a column (see tests).

DANGER — overloaded hexes
-------------------------
#7c3aed (violet-600) belongs EXCLUSIVELY to the Exceptional 💎💎 DEAL badge.
The Design-system draft put Legendary rarity AND Exceptional on #a855f7;
Exceptional keeps its historical violet precisely so a Legendary pill can
never be mistaken for an Exceptional badge. DEAL_BADGES below exists so the
test suite can assert the two systems stay distinguishable.

Some cores are deliberately SHARED with non-rarity roles (hue = one meaning
family): #a855f7 is also the brand accent/private-seller purple, #3b82f6 the
link blue, #22c55e the buyer-good green. Rarity pills stay recognisable by
TREATMENT (translucent bg + border), not hue alone.
"""
from __future__ import annotations


def _rgba(hex_core: str, alpha: float) -> str:
    r, g, b = (int(hex_core[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha:g})"


# ── Rarity tiers: rarest → most common ──────────────────────────────────────
# core = oklch(0.66 0.20 H) | text = oklch(.78 .14 H) | bg/border derived @15/35%
RARITY_TIERS: dict[str, dict] = {
    "Mythic": {
        "core": "#e93d82", "text": "#f9a8d4",        # H 340 (pink)
        "label": "MYTHIC", "css": "r-mythic",
        "scores": (9, 10), "band": 0.05,
    },
    "Legendary": {
        "core": "#a855f7", "text": "#d8b4fe",        # H 300 (purple)
        "label": "LEGEND", "css": "r-veryr",
        "scores": (8,), "band": 0.15,
    },
    "Rare": {
        "core": "#3b82f6", "text": "#93c5fd",        # H 260 (blue)
        "label": "RARE", "css": "r-rare",
        "scores": (7,), "band": 0.30,
    },
    "Uncommon": {
        "core": "#14b8a6", "text": "#5eead4",        # H 200 (teal)
        "label": "UNCOMMON", "css": "r-uncomm",
        "scores": (5, 6), "band": 0.55,
    },
    "Common": {
        "core": "#22c55e", "text": "#86efac",        # H 150 (green)
        "label": "COMMON", "css": "r-common",
        "scores": (3, 4), "band": 0.80,
    },
    "Ubiquitous": {
        "core": "#9ba1a6", "text": "#d4d4d8",        # neutral
        "label": "UBIQ", "css": "r-ubiq",
        "scores": (1, 2), "band": 1.01,
    },
}

# Derived pill colours (the pairing rule, applied once).
for _t in RARITY_TIERS.values():
    _t["bg"] = _rgba(_t["core"], 0.15)
    _t["border"] = _rgba(_t["core"], 0.35)

# Rarest → most common. The canonical order for legends, facets and sorting.
TIER_ORDER: list[str] = list(RARITY_TIERS.keys())

# ── Deal badges — a DIFFERENT system: FILLED chips (solid core bg), unlike the
# translucent rarity pills, so the two never read alike even where they share a
# hue. Text is white on dark cores, near-black on light cores. Defined here so
# the tests can prove Legendary and Exceptional stay distinguishable.
DEAL_BADGES: dict[str, dict] = {
    "fire":        {"bg": "#f97316", "text": "#ffffff"},   # 🔥
    "exceptional": {"bg": "#7c3aed", "text": "#f4f4f5"},   # 💎💎  violet-600, exclusive
    "strong":      {"bg": "#3b82f6", "text": "#ffffff"},   # 💎
    "fair":        {"bg": "#22c55e", "text": "#0a0a0b"},   # 👍
    "above":       {"bg": "#a1a1aa", "text": "#0a0a0b"},   # 👎
}

# ── Derived lookups ─────────────────────────────────────────────────────────
SCORE_TO_TIER: dict[int, str] = {
    s: name for name, t in RARITY_TIERS.items() for s in t["scores"]
}

# Percentile bands (most-common last) for catalog_rarity_tiers().
TIER_BANDS: list[tuple[float, str, str]] = [
    (t["band"], name, t["css"]) for name, t in RARITY_TIERS.items()
]

# 52-week range bar: the rarity ladder itself (solid cores), low → high.
# Ubiquitous (gray) is omitted — the bar is a price ramp and starts at the
# first chromatic step.  => green → teal → blue → purple → pink
RANGE_BAR_GRADIENT: str = "linear-gradient(90deg," + ",".join(
    RARITY_TIERS[n]["core"] for n in reversed(TIER_ORDER) if n != "Ubiquitous"
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
      * custom properties  --rarity-<slug>-core/-bg/-text/-border
      * the tier classes   .r-mythic … .r-ubiq  (translucent bg + border)
      * the score classes  .score-1 … .score-10 (score → its tier's colours)
      * the range-bar gradient
    """
    lines: list[str] = []

    lines.append(":root {")
    for name, t in RARITY_TIERS.items():
        slug = name.lower()
        lines.append(
            f"  --rarity-{slug}-core:{t['core']}; --rarity-{slug}-bg:{t['bg']}; "
            f"--rarity-{slug}-text:{t['text']}; --rarity-{slug}-border:{t['border']};"
        )
    lines.append("}")

    for name, t in RARITY_TIERS.items():
        slug = name.lower()
        lines.append(
            f".{t['css']} {{ background:var(--rarity-{slug}-bg); "
            f"color:var(--rarity-{slug}-text); "
            f"border:1px solid var(--rarity-{slug}-border); }}"
        )

    for name, t in RARITY_TIERS.items():
        slug = name.lower()
        sel = ",".join(f".score-{s}" for s in t["scores"])
        lines.append(
            f"{sel} {{ background:var(--rarity-{slug}-bg); "
            f"color:var(--rarity-{slug}-text); "
            f"border:1px solid var(--rarity-{slug}-border); }}"
        )

    lines.append(
        ".rangebar { position:relative; height:8px; border-radius:5px; "
        f"background:{RANGE_BAR_GRADIENT}; }}"
    )
    return "\n".join(lines)
