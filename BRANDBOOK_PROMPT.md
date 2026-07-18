# FangTrack — Brand Book Prompt

> Paste the block below into Claude (Design / artifact) to generate the FangTrack brand book.
> Every hex is pulled from the live source as of 2026-07-14: the rarity ladder + deal badges come
> from `theme.py` (the single source of truth, `RARITY_TIERS` / `DEAL_BADGES`); all other tokens
> from `templates/base.html`.
>
> **Mike's directive: "I want a SYSTEM not a list."** The palette is drawn almost entirely from
> the Tailwind ramp — so the brand book must define an *extensible system* (named ramps + the
> rule for picking the next step), not a frozen inventory of hexes. That requirement is baked
> into the prompt below (see §0 and the final Rules).

---

```
Build a brand book / design system for FangTrack — a dark-mode market-intelligence web app for
the exotic-invertebrate hobby (tarantulas, scorpions, isopods, myriapods). It crawls ~36
specialist vendors and turns raw asking prices into decisions: is this a good deal, how rare is
this animal, is the price moving.

Deliver a single self-contained page: swatch grids with hex values, badge specimens rendered at
real size, component examples, type scale, and usage rules. Dark canvas — the product is dark-only.

═══ 0. MOST IMPORTANT: BUILD A SYSTEM, NOT A LIST ═══════════════════════════
The palette is drawn almost entirely from the TAILWIND color ramp. Document it that way.

  slate-600 #475569 · green-700 #15803d · sky-700 #0369a1 ·
  indigo-700 #4338ca · fuchsia-700 #a21caf · orange-700 #c2410c

Every tier/badge background is a ~600–800 step of a Tailwind hue, and every badge TEXT color is
the ~200–300 step of that SAME hue (e.g. indigo-700 bg #4338ca pairs with indigo-200 text
#c7d2fe). That pairing rule — "dark step of a hue as the fill, light step of the same hue as the
text" — is the actual system. State it explicitly and make it generative:

  • Name the ramps we use and the steps we pull from.
  • Give the rule for adding a NEW badge/tier: pick an unused Tailwind hue, take the 600–800 step
    for the background and the 200–300 step of the same hue for the text, and verify it does not
    collide with an existing background.
  • Show the escalation logic (cool/low-saturation → hot/high-saturation as rarity rises), so a
    future 7th tier or a sibling product (HerpTrack) can extend the ladder correctly.
  • Anyone reading this should be able to derive a new color, not just look one up.

Do NOT present the colors as a fixed inventory. Present the ramps, the pairing rule, and the
escalation logic — with the current values as the instantiation of that system.

═══ 1. BRAND CHARACTER ══════════════════════════════════════════════════════
Analytical, honest, collector-obsessed. It borrows from three products: Keepa (price memory),
StockX (market confidence, "asks not sales"), and TCGplayer (rarity language, collecting as a
game). Tone is precise and never overclaims — the palette should feel like an instrument panel,
not a toy store. The one deliberate flourish is the rarity ladder, which is intentionally TCG-like.

═══ 2. CORE TOKENS ══════════════════════════════════════════════════════════
Base / page          #0a0a0a
Surface (raised)     #141414
Card                 #1e1e1e
Border               #2a2a2a
Divider (subtle)     #232323
Row divider          #1e1e1e
Hover                #151515

Text primary         #f0f0f0
Text soft            #e0e0e0
Text quiet           #cfcfcf
Text muted           #888888
Text dim             #666666 / #555555 / #444444 (descending)

Accent (primary)     #1a73e8   ← CSS var --accent-blue (it is a blue, not a teal)
Accent hover         #1558c0
Fire                 #ff6b00
Gem (purple)         #a855f7
Down / good / cheap  #22c55e
Up / bad / expensive #ef4444

═══ 3. RARITY LADDER (the hero system) ══════════════════════════════════════
Six tiers, percentile-ranked across the whole catalog. Must read as an escalating ladder with
SIX DISTINCT hues: slate → green → sky → indigo → fuchsia → orange (a classic TCG rarity ramp).
No two tiers may share a background — and critically, no rarity background may equal any deal
badge background (the first three tiers were deliberately moved off gray-700/emerald-800/blue-700
precisely because those collided with the Above-market/Fair/Strong deal badges). Pills: radius
4px, 11px/700, padding 2px 8px, letter-spacing .02em.

Tier          Background         Text               Meaning
Ubiquitous    #475569 slate-600  #cbd5e1 slate-300  everywhere, always in stock
Common        #15803d green-700   #bbf7d0 green-200   widely carried
Uncommon      #0369a1 sky-700    #bae6fd sky-200     shop a few sellers to find it
Rare          #4338ca indi-700   #c7d2fe indi-200   a few sellers, sells fast
Legendary     #a21caf fuch-700   #f5d0fe fuch-200   lucky to see in stock
Mythic        #c2410c oran-700   #fed7aa oran-200   grail tier, rarest ~5%

A 1–10 numeric score maps onto the same ladder (shown as "7/10" pills):
1–2 Ubiquitous · 3–4 Common · 5–6 Uncommon · 7 Rare · 8 Legendary · 9–10 Mythic

═══ 4. DEAL BADGES ══════════════════════════════════════════════════════════
Grade          Background   Text       Glyph
Fire           #ff6b00      #ffffff    🔥   all-time-low delivered cost
Exceptional    #7c3aed      #f0f0f0    💎💎  20%+ below market
Strong         #1d4ed8      #bfdbfe    💎   10–20% below market
Fair           #065f46      #a7f3d0    👍   within ~10% of market
Above market   #374151      #9ca3af    👎   10%+ above market

═══ 5. MOMENTUM TAGS (price trend) ══════════════════════════════════════════
Radius 4px, 10px/700, padding 1px 7px, letter-spacing .04em
Heating ▲   bg #7f1d1d  text #fecaca
Cooling ▼   bg #064e3b  text #a7f3d0
Steady  →   bg #1f2937  text #9ca3af

═══ 6. SOURCE MARKERS (captive-bred / wild-caught) ══════════════════════════
Text-only, no background. A DIMMED variant with a "°" suffix means we INFERRED it rather than
the seller stating it — this distinction is a core honesty principle, not decoration.
              Stated     Inferred (dimmed, shows °)
CB            #22c55e    #166534   ← green-800, nudged off #15803d so it never reads as the Common rarity fill
WC            #ef4444    #b91c1c
LTC           #fbbf24    —
Unstated "?"  #555555    —

═══ 7. DASHBOARD "STANDOUTS" BADGES ═════════════════════════════════════════
MYTHIC  #c2410c / #fed7aa      $$$$   #374151 / #d1d5db
LEGEND  #a21caf / #f5d0fe      OWNED  #065f46 / #6ee7b7

═══ 8. OTHER CHIPS ══════════════════════════════════════════════════════════
Discount code     bg #064e3b  text #6ee7b7
Sale flag         #fbbf24
Private seller 👤  #a855f7
ADMIN tag         bg #2a1a3a  text #a855f7
Owned ✓           #1a73e8
Female ♀ #f9a8d4   ·   Male ♂ #93c5fd

═══ 9. PRICE RANGE BAR (52-week style) ══════════════════════════════════════
Track: linear-gradient(90deg, #15803d, #0369a1, #4338ca, #a21caf, #c2410c)
  — i.e. the rarity ladder (tiers 2–6, slate/Ubiquitous omitted), used as a continuous ramp.
  Height 8px, radius 5px.
"You are here" marker: #ffffff, 3px wide, drop shadow.
All-time-low marker:   #34d399, 2px wide.

═══ 10. COMPONENTS ══════════════════════════════════════════════════════════
Card            bg #1e1e1e, 1px #2a2a2a, radius 10px, padding 20px
Stat card       bg #141414, 1px #2a2a2a, radius 10px, padding 16px 20px
Table header    bg #141414, text #1a73e8, 10px UPPERCASE, letter-spacing .1em
Table cell      13px, bottom border #1e1e1e, row hover bg #141414
Input           bg #1e1e1e, 1px #2a2a2a, radius 6px; focus border #1a73e8
Button primary  bg #1a73e8, text #0a0a0a, radius 6px, 13px/700
Button ghost    transparent, text + 1px border #1a73e8
Button danger   transparent, text + 1px border #ef4444
Nav link        #888 → hover #f0f0f0 on #1e1e1e → active #1a73e8 on #1e1e1e
Flash success   bg #064e3b, border #059669, text #d1fae5
Flash error     bg #450a0a, border #b91c1c, text #fecaca
Species name    ALWAYS italic, color #1a73e8 (scientific names are italic everywhere)

═══ 11. TYPE ════════════════════════════════════════════════════════════════
Font: system-ui / -apple-system / sans-serif. Base 14px.
Scale: 26px KPI values · 22px panel values · 20px/900 page titles · 19/15px stat values ·
       13px body · 12px secondary · 11px captions · 10–10.5px uppercase micro-labels
All numerics: font-variant-numeric: tabular-nums.
Micro-labels: UPPERCASE, letter-spacing .06–.1em.
Radii: 10px cards · 8px inner cells · 7px list-row hover · 6px buttons/inputs · 20px pills ·
       4px badges

═══ 12. RULES TO DOCUMENT ═══════════════════════════════════════════════════
1. IT IS A SYSTEM, NOT A LIST. Tailwind ramps + the "dark step fill / light step of the same
   hue for text" pairing rule + the escalation logic. A reader must be able to DERIVE a new
   color, not just look one up. (See §0.)
2. Rarity color has ONE source of truth: theme.py (RARITY_TIERS). Templates render its
   generated CSS; no template hard-codes a rarity hex. Six distinct backgrounds; never let two
   tiers share one. (Rare and Legendary once collided on #7c3aed, which also silently
   mis-colored badges in two templates. #7c3aed now belongs EXCLUSIVELY to the Exceptional
   💎💎 deal badge and must never be a rarity color again.)
3. Directional color is from the BUYER's perspective: price DOWN is green #22c55e (good for
   you), price UP is red #ef4444.
4. #1a73e8 is the interactive/identity color: links, species names, active nav, table headers,
   primary buttons. Never use it decoratively.
5. #ff6b00 (fire) is reserved for genuine all-time lows and the "What is FangTrack?" nav item.
   Scarcity is what keeps it meaningful.
6. Inferred data must be visually distinguishable from stated data (dimmed + ° suffix). Never
   let a guess look like a fact — honesty is the product's moat.

═══ DELIVERABLE ═════════════════════════════════════════════════════════════
A full brand-book page containing:
  • The SYSTEM first: named Tailwind ramps, the fill/text pairing rule, the escalation logic,
    and a worked example of deriving a brand-new tier color correctly.
  • Swatch cards (hex + Tailwind name + role + text-on-bg pairing).
  • The rarity ladder as one escalating strip.
  • Every badge rendered as a real specimen at real size.
  • Component gallery + type scale.
  • The six rules above as a "Principles" section.
```
