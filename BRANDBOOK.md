# FangTrack Brand Book

*The design system for FangTrack — a dark-mode market-intelligence app for the
exotic-invertebrate hobby. This is the **2026-07-19 rebrand** (Mike-approved,
from the FangTrack Design project): blue-dominant with a purple accent, zinc
neutrals, and an oklch rarity ladder. Every value in this book is live in
code; where a value has a single source of truth, that file is named. This
book explains the **system** so you can derive a new colour, badge, or
component correctly — not just look one up.*

**Sources of truth**

| What | Where | Enforced by |
|---|---|---|
| Rarity tier colours | `theme.py` (`RARITY_TIERS`) | `tests/test_core.py` (distinguishability + drift tests) |
| Deal badge colours | `theme.py` (`DEAL_BADGES`) | same |
| Everything else (surfaces, text, accents, type, spacing) | `tokens/fangtrack.tokens.json` + `tokens/fangtrack.css` | `tests/test_tokens.py` (parity) |
| Email styling | `templates/email/base_email.html` (values injected from the tokens JSON at render time) | — |

---

## 0. The system, not a list

The identity rests on two generative rules.

> **The rarity formula.** A tier is one **core colour** on the hue ladder
> `oklch(0.66 0.20 H)`. The pill derives everything from the core:
> **bg = core @ 15% alpha · text = oklch(.78 .14 H) · border = core @ 35%**
> (light theme: 10% / oklch(.45 .14 H) / 25%).

> **The treatment rule.** Rarity pills are **translucent** (soft bg + border);
> deal-grade chips are **filled** (solid core bg, white text on dark cores,
> near-black on light ones). Hues may be shared across systems — *treatment*
> is what tells you which system you're reading.

**The hue ladder** (rarest → most common):

```
H: 340        300        260       200       150       (neutral)
   pink   →   purple  →  blue   →  teal   →  green  →   gray
   hot / rare  ─────────────────────────────►  cool / everywhere
```

**To derive a brand-new tier** (say a 7th above Mythic): extend the ladder at
the hot end — H ≈ 25 gives an orange-red core (`oklch(0.66 0.20 25)` ≈
`#f5484d`); apply the formula for bg/text/border; then check the core against
every *filled* chip colour and the Exceptional-violet rule below. Anyone with
an oklch picker can extend this system without guessing.

**Deliberate hue sharing.** A hue is a *meaning family*, reused across
systems: purple `#a855f7` = Legendary / brand accent / private sellers; blue
`#3b82f6` = Rare / Strong deal / links; green `#22c55e` = Common / Fair deal /
price-down-good. The **one forbidden overlap**: the Exceptional 💎💎 deal
badge keeps its exclusive violet `#7c3aed` (not accent purple) so a Legendary
pill can never be mistaken for an Exceptional badge — the descendant of the
original `#7c3aed` collision incident, and a test enforces it.

---

## 1. Brand character & voice

Analytical, honest, collector-obsessed. FangTrack borrows from three product
traditions: *price memory* (every listing has a history), *market confidence*
("Lowest Ask," never "price" — we see asks, not sales), and *rarity as a
collecting game* (the tier ladder is deliberately trading-card-like). The
palette should feel like an **instrument panel, not a toy store** — the one
flourish is the rarity ladder.

Voice rules (from `ROADMAP.md`, "Principles"):

1. **Never imply data we don't have.** "Lowest Ask," not "price." Inferred
   values are labelled inferred.
2. **Honesty is the moat.** A wrong CB label is worse than an honest "?".
   Visually: inferred data is dimmed and carries a `°` suffix — a guess must
   never look like a fact.
3. Precise, never overclaiming. Numbers carry the argument; adjectives don't.

Public-facing copy (emails, tour, transparency page) is written in Mike's
first-person voice: direct, warm, keeper-to-keeper. It never names competitor
products.

---

## 2. Core tokens (dark canvas)

The product is **dark-only**. Full set in `tokens/fangtrack.css` (`--ft-*`).

| Role | Value | Notes |
|---|---|---|
| Base / page | `#0a0a0b` | zinc-black |
| Surface (raised) | `#141417` | stat cards, table headers, row hover |
| Card | `#1c1c21` | |
| Nav | `#0e0e10` | |
| Border | `#2a2a31` | |
| Text primary | `#f4f4f5` | |
| Text 2 (muted) | `#a1a1aa` | |
| Text 3 (dim) | `#71717a` | then `#52525b` / `#3f3f46` descending |
| **Primary (identity)** | `#2563eb` | buttons, active nav, species names, table headers |
| Primary strong (hover) | `#1d4ed8` | |
| Link | `#3b82f6` | text links; one step lighter than primary |
| **Accent** | `#a855f7` | purple: private sellers, BETA pill, highlights (`#9333ea` strong) |
| Soft washes | primary/accent @ 15% | `--ft-primary-soft` / `--ft-accent-soft` |
| Fire | `#f97316` | all-time lows only + "What is FangTrack?" nav |
| Down / good / cheap | `#22c55e` | buyer's perspective |
| Up / bad / expensive | `#ef4444` | buyer's perspective |
| Radii | 6 / 8 / 12px | `--ft-radius-sm/md/lg` (legacy component radii remain: 10px cards, 4px badges, 20px pills) |

---

## 3. The rarity ladder (the hero system)

Six tiers, percentile-ranked across the whole catalog. **Single source of
truth: `theme.py`** — templates render `{{ rarity_css()|safe }}`; no template
ever hard-codes a rarity-exclusive hex (a test walks the tree to enforce it).

| Tier | H | Core | Text | Meaning |
|---|---|---|---|---|
| Ubiquitous | — | `#9ba1a6` | `#d4d4d8` | everywhere, always in stock |
| Common | 150 | `#22c55e` | `#86efac` | widely carried |
| Uncommon | 200 | `#14b8a6` | `#5eead4` | shop a few sellers |
| Rare | 260 | `#3b82f6` | `#93c5fd` | few sellers, sells fast |
| Legendary | 300 | `#a855f7` | `#d8b4fe` | lucky to see in stock |
| Mythic | 340 | `#e93d82` | `#f9a8d4` | grail tier, rarest ~5% |

Pill rendering: bg = core@15%, 1px border = core@35%, radius 4px, 11px/700,
padding 2px 8px, letter-spacing .02em.

The 1–10 numeric score maps onto the same ladder (rendered as "7/10" pills):
1–2 Ubiquitous · 3–4 Common · 5–6 Uncommon · 7 Rare · 8 Legendary · 9–10 Mythic.

## 4. Deal badges

**Filled** chips — the opposite treatment from rarity. Mirrored from
`theme.py DEAL_BADGES`.

| Grade | Background | Text | Glyph | Meaning |
|---|---|---|---|---|
| Fire | `#f97316` | `#ffffff` | 🔥 | all-time-low delivered cost |
| Exceptional | `#7c3aed` | `#f4f4f5` | 💎💎 | 20%+ below market (exclusive violet — never accent purple) |
| Strong | `#3b82f6` | `#ffffff` | 💎 | 10–20% below market |
| Fair | `#22c55e` | `#0a0a0b` | 👍 | within ~10% of market |
| Above market | `#a1a1aa` | `#0a0a0b` | 👎 | 10%+ above market |

## 5. Momentum tags

Radius 4px, 10px/700, padding 1px 7px, letter-spacing .04em.

| Tag | Background | Text |
|---|---|---|
| Heating ▲ | `#7f1d1d` | `#fecaca` |
| Cooling ▼ | `#064e3b` | `#a7f3d0` |
| Steady → | `#1f2937` | `#a1a1aa` |

## 6. Source markers (the honesty system)

Text-only, no background. The dimmed variant with a **`°` suffix** means the
value was *inferred* rather than stated by the seller — this distinction is a
core product principle, not decoration.

| Marker | Stated | Inferred (dimmed + °) |
|---|---|---|
| CB | `#22c55e` | `#166534` |
| WC | `#ef4444` | `#b91c1c` |
| LTC | `#fbbf24` | — |
| Unstated "?" | `#52525b` | — |

## 7. Other chips

| Chip | Values |
|---|---|
| Discount code | bg `#064e3b`, text `#6ee7b7` |
| Sale flag | `#fbbf24` |
| Private seller 👤 | `#a855f7` |
| ADMIN tag | bg `#2a1a3a`, text `#a855f7` |
| Owned ✓ | `#2563eb` |
| Female ♀ / Male ♂ | `#f9a8d4` / `#93c5fd` |

## 8. Price range bar (52-week style)

The track **is the rarity ladder** (solid cores) used as a continuous ramp —
Ubiquitous (gray) omitted because the bar is a price ramp and starts at the
first chromatic step: `linear-gradient(90deg, green → teal → blue → purple →
pink)`. Generated from `theme.py` (`RANGE_BAR_GRADIENT`). Height 8px, radius
5px. "You are here" marker `#ffffff` 3px with drop shadow; all-time-low marker
`#34d399` 2px.

---

## 9. Components

| Component | Spec |
|---|---|
| Card | bg `#1c1c21`, 1px `#2a2a31`, radius 10px, padding 20px |
| Stat card | bg `#141417`, 1px `#2a2a31`, radius 10px, padding 16px 20px |
| Table header | bg `#141417`, text `#2563eb`, 10px UPPERCASE, tracking .1em, sticky |
| Table cell | 13px, bottom border `#1c1c21`, row hover bg `#141417` |
| Input | bg `#1c1c21`, 1px `#2a2a31`, radius 6px; focus border `#2563eb` |
| Button primary | bg `#2563eb`, text `#0a0a0b`, radius 6px, 13px/700; hover `#1d4ed8` |
| Button ghost | transparent, text + 1px border `#2563eb`; hover wash `#2563eb20` |
| Button danger | transparent, text + 1px border `#ef4444` |
| Nav link | `#a1a1aa` → hover `#f4f4f5` on `#1c1c21` → active `#2563eb` on `#1c1c21` |
| Flash success | bg `#064e3b`, border `#059669`, text `#d1fae5` |
| Flash error | bg `#450a0a`, border `#b91c1c`, text `#fecaca` |
| Species name | **always italic**, `#2563eb` — scientific names are italic everywhere |
| Scrollbars | thumb `#26262b` on track `#0e0e10`, thin |

## 10. Typography

- **Font:** `system-ui, -apple-system, sans-serif`. Base **14px**.
- **Scale:** 26px KPI values · 22px panel values · 20px/900 page titles ·
  19/15px stat values · 13px body · 12px secondary · 11px captions ·
  10–10.5px uppercase micro-labels.
- **All numerics:** `font-variant-numeric: tabular-nums` — this is an
  instrument panel; columns of numbers must align.
- **Micro-labels:** UPPERCASE, letter-spacing .06–.1em.

## 11. Logo & iconography

- **Wordmark:** `FANG` in white + `TRACK` in primary blue `#2563eb`, weight
  900, letter-spacing −.02em. The two-tone split is the wordmark — never
  render it one colour. In HTML contexts prefer the *text* wordmark (it
  survives image blocking); the PNG mark sits beside it.
- **Mark:** the spider logo (`static/img/fangtrack_nav_logo.png`, embedded as
  a data URI in the nav). App icons at 32/64/128/256/512 in `static/img/`;
  `favicon.png` for tabs. All marks are monochrome white silhouettes
  (verified pixel-scan 2026-07-19) — they are rebrand-proof; colour lives
  only in the text wordmark and UI.
- **Tier pills under the wordmark:** `PRO` (bg `#2563eb`) for signed-in,
  `BETA` (bg `#a855f7`) for logged-out — 8px/800, tracking .12em.
- **Emoji are brand vocabulary,** used consistently: 🕷️ identity/welcome ·
  🔥 fire deal · 💎/💎💎 deal grades · 👍/👎 fair/above · 🧠 market
  intelligence · 👁️/🎒 watchlist/collection · 👤 private seller · 🏆
  leaderboard · ♀/♂ sex markers.

---

## 12. Principles (the six rules)

1. **It is a system, not a list.** The oklch rarity formula + the
   translucent-vs-filled treatment rule + the hue ladder. A reader must be
   able to *derive* a new colour, not just look one up.
2. **Rarity colour has ONE source of truth:** `theme.py`. Templates render its
   generated CSS; no template hard-codes a rarity-exclusive hex. And
   `#7c3aed` belongs exclusively to the Exceptional 💎💎 deal badge — never
   to rarity, and Legendary never borrows it back.
3. **Directional colour is the buyer's perspective:** price DOWN is green
   `#22c55e` (good for you); price UP is red `#ef4444`.
4. **`#2563eb` is the interactive/identity colour** — buttons, species names,
   active nav, table headers (links use `#3b82f6`). Never decorative. Purple
   `#a855f7` is the accent, not a second primary.
5. **`#f97316` (fire) is reserved** for genuine all-time lows and the "What is
   FangTrack?" nav item. Scarcity keeps it meaningful.
6. **Inferred ≠ stated, visibly.** Dimmed + `°` suffix on anything we guessed.
   Never let a guess look like a fact — honesty is the product's moat.

---

## 13. Email addendum

Emails share the same tokens (injected from `tokens/fangtrack.tokens.json` at
render time by `render_email()` in `app.py`) with email-specific constraints:

- **Table layout, fully inline styles,** 600px max width — no external CSS, no
  web fonts, no CSS variables (email clients strip them).
- **Dark canvas, explicitly.** Every element sets its own `background` and
  `color` so client dark-mode inversion can't produce unreadable text;
  `color-scheme: dark` is declared in the head.
- **Text wordmark, not the image,** as the primary brand mark (images are
  blocked by default in most clients). FANG white / TRACK primary blue.
- **One primary button per email** (primary blue, white text per
  `--ft-on-primary`), links in link blue elsewhere.
- Every email carries the footer: "FangTrack — private market intelligence
  tool", a link to *What is FangTrack?* (`/transparency`), and a contact line.
- Multipart always: the plain-text part is written for humans, not a tag-strip.
