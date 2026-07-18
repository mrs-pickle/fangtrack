> ## ✅ BUILD STATUS — shipped overnight July 12→13, 2026
> Per Mike's "implement every suggestion in here — all of them," the following are now live
> (server restarted on fresh code; 11/11 unit tests pass):
>
> **Keepa (memory):** price-history graph upgraded (all-time-low band, market-price line,
> "lowest ask now" marker, tooltips) · **price-drop / back-in-stock / fire / saved-search
> alerts** with an in-app **Alerts inbox** (nav badge) + email delivery (auto-enabled when
> SMTP is set in Settings) · **saved searches** ("Deal Finder") that become recurring alerts.
>
> **StockX (confidence):** **market-summary strip** on every spider card (Lowest Ask ·
> Market Price · All-Time Low · 90-Day Range · Live Listings · Rarity) · **52-week-style
> range bar** with a "you are here" marker · **inferred recent sales** ("likely recently
> taken at ~$X", URL-matched, clearly labelled) · **heating/cooling** momentum (span-guarded
> so it stays honest until ~2 weeks of history) · **liquidity** ("seen at N vendors · M/90d").
>
> **TCGplayer (collector):** **faceted Species browse** (Origin / Care / Rarity / Price /
> Genus, with counts) · **named + coloured rarity tiers**, percentile-ranked into a real
> pyramid (Mythic = top ~4%) · **Market Price** = trimmed median of recent asks (also drives
> the Deals "vs market" delta) · **Collection portfolio value** + priced-count · **genus /
> family landing pages** with a family price index · **printer-ready collection labels**.
>
> **Cross-cutting:** spider card is now the center of gravity (add-to-watchlist/collection,
> buy links, family link) · **sparklines** on tiles, deal rows, and movers · consistent named
> rarity + deal tiers · **Market Movers** home module (all-time-low deals, biggest drops,
> back-in-stock, heating-up) · honest labelling throughout ("Ask" not "price", "Market Price
> (recent asks)", inferred sales marked).
>
> **Deferred (with reason):** *Browser-extension overlay* — a separately-distributed artifact
> (own manifest + store listing); can't ship inside the app tonight, still the distribution
> play. *Free core / paid depth* — a pricing decision, not code. Everything else above shipped.

# FangTrack — Feature & Design Ideas from Keepa, StockX & TCGplayer

Research pass on the three platforms our value prop cites ("Keepa-style price history,
StockX-style deal scoring, TCG-inspired rarity"). For each, what they do well and the
specific, buildable FangTrack version. Ordered within each section by leverage.
Sources: [Keepa](https://keepa.com), [StockX market data](https://stockx.com/news/how-to-view-market-data-on-stockx-pro/),
[TCGplayer Market Price](https://help.tcgplayer.com/hc/en-us/articles/213588017-TCGplayer-Market-Price).

---

## 1. Keepa → price history & alerting (our "memory")

What makes Keepa sticky: **the graph is the product**, and **free price-drop alerts** create the habit loop.

- **★ The price-history graph as the hero of the spider card.** Keepa's graph zooms from daily
  ticks to years, overlays multiple series (new/used/buy-box), and shades events. Ours is a start;
  next: a real time-axis line once we have multi-day data, with **all-time-low / high bands**, a
  **"you are here" marker** for the current lowest ask, and hover tooltips (price · vendor · date).
  This is the single feature that will most sell the "Keepa for tarantulas" pitch — it needs the
  daily crawl history to accumulate (why the 5 AM scheduler matters).
- **★ Price-drop & back-in-stock alerts (email/push).** Keepa's core habit. We already detect
  watchlist hits every crawl — the missing half is *delivery*. Send "🎯 Grammostola pulchra just
  dropped to $X at Vendor" and "back in stock" the moment a crawl sees it. This is the retention engine.
- **A "Deal Finder" query builder.** Keepa Pro lets sellers filter by rank/category/price. Our
  Deals page has filters; the Keepa move is **saved searches** ("all 💎+ Poecilotheria under $150,
  females") that become recurring alerts. Turns one-off browsing into a subscription reason.
- **Browser-extension future.** Keepa's overlay on Amazon is its growth hack. Phase-3 analog: a
  FangTrack overlay that shows our price history + rarity when a user is *on a vendor's product page*.
  Park, but it's the distribution play.
- **Free core, paid depth.** Keepa gives graphs + alerts free, charges for seller analytics. Mirrors
  our plan — keep the buyer view free, monetize the supply-side intel.

## 2. StockX → market microstructure & deal confidence (our "scoring")

StockX's genius is making an illiquid market *feel* like a stock exchange with a few numbers.

- **★ The "market summary" strip on every spider card.** StockX shows **Last Sale, Lowest Ask,
  Highest Bid, 52-week range, 24h/7d volume** in one glance. Our species version:
  **Lowest Ask (current cheapest), All-Time Low, Market Median, 90-day range, and "listings live now"** —
  a compact stat row above the chart. This is the credibility layer; it says "this is a real market."
- **★ "Last Sale" vs "Lowest Ask" framing.** StockX separates *asking* prices from *what actually
  sold*. We only see asks (vendors list, we can't see closes). Honest analog: label our number the
  **"Lowest Ask"** and, where a listing disappears between crawls at/near a price, infer a **likely
  sale** and show a faint "recently taken at ~$X" — the beginning of a sold-price signal without
  pretending we have transaction data.
- **Price-volatility / "market moving" badges.** StockX flags fast movers. We have trend arrows;
  strengthen into a **"heating up / cooling" tag** per species (median rising/falling over 30d) so
  buyers sense momentum. Feeds FOMO in a defensible, data-backed way.
- **52-week range bar.** A tiny horizontal bar showing where the current price sits within its
  historical range is instantly legible and very StockX. Cheap to build once history exists.
- **Sales volume as a liquidity signal.** StockX shows how *active* a market is. Our analog:
  **"seen at N vendors · M listings in 90 days"** — tells a buyer whether a species is liquid
  (easy to find, price-competitive) or thin (grab it when you see it). Pairs perfectly with rarity.

## 3. TCGplayer → rarity, taxonomy & browse (our "collector layer")

TCGplayer nails the *collector* experience: rich taxonomy, condition/rarity facets, and a market
price built from real sales — plus collection tools that create attachment.

- **★ Faceted browse on the Species tab.** TCGplayer filters by set / rarity / condition / printing.
  Our facets: **genus/family, rarity tier, size class, price band, New-World vs Old-World, temperament
  (beginner/advanced), region**. The species tiles we just shipped are the StockX/TCG browse grid —
  add a left-rail of facets and it becomes a real catalog to explore, not just search.
- **★ Rarity tiers with names & color, not just a number.** TCG rarity (Common→Mythic) is iconic
  because it's *named and colored*. We already have TCG-inspired badge classes (r-common…r-mythic).
  Lean in: show the **tier name on the spider card** ("Rarely seen — 8/10"), and a legend. This is
  the most on-brand differentiator and costs little.
- **★ "Market Price" = recent-sales-based, not lowest listing.** TCGplayer's headline number is a
  blended recent-transaction value, which they argue is more honest than "lowest listed." Our
  equivalent: alongside Lowest Ask, show a **Market Price = trimmed median of recent asks** (drop the
  outliers), so a lone lowball or a lone gouger doesn't define the species. This directly upgrades
  deal-scoring quality and is the natural home once history accumulates.
- **★ Collection Tracker with portfolio value.** TCG's Collection Tracker (Have/Want/Trade + live
  value) is a huge retention hook. Our Collection tab exists; add **"your collection is worth ~$X at
  today's market" + gain/loss over time**, and Want-list = the Watchlist. Turns a utility into a
  dashboard people check.
- **Set/family landing pages.** TCG organizes by set. Our analog: **genus/family pages** ("all
  Poecilotheria", "all Pamphobeteus") that list species tiles + a family price index. Great for SEO
  and browsing behavior, and trivial given canonical genus keys.
- **Printer-ready collection labels** (you already flagged this) fits the TCG/collector ethos.

---

## Cross-cutting UI / design moves
1. **Make the spider card the center of gravity** — chart + StockX stat strip + rarity tier +
   current listings table + "add to watchlist / collection." Every list should funnel here (we just
   wired tiles, dashboard, collection, watchlist to link in).
2. **Sparklines on tiles & deal rows** — a 3px price trend line per species turns lists into a
   market view at a glance (Keepa/StockX signature).
3. **Named, colored rarity + deal tiers everywhere** — consistent TCG-style visual language is our
   brand; use it on tiles, cards, and the market strip.
4. **A public "market movers" home module** — biggest drops, new fire deals, heating-up species —
   the StockX front-page energy, drives return visits.
5. **Honest labeling** — "Lowest Ask" not "price," "Market Price (recent asks)" not "value,"
   inferred sales clearly marked. Our credibility is the moat; never imply data we don't have.

## Suggested build order (once daily history is flowing)
1. StockX **market-summary strip** + **52-week range bar** on the spider card (high impact, low effort).
2. **Price-drop / back-in-stock alert delivery** (the retention engine — pairs with the scheduler).
3. **Faceted Species browse** + **named rarity tiers** (the TCG collector layer; tiles already exist).
4. **Trimmed-median "Market Price"** to upgrade deal scoring honesty.
5. **Collection portfolio value** + **saved searches / deal-finder alerts**.
6. Later: **sparklines**, **family landing pages**, **browser-extension overlay**.

The through-line: Keepa gives us the *memory* (history + alerts), StockX gives us the *confidence*
(market microstructure, honest asks), TCGplayer gives us the *collector pull* (rarity language,
faceted browse, portfolio). All three lean on the same foundation we just built tonight — clean
canonical species + accumulating daily price history.

---

## 🅿️ Parked ideas (post-launch / web + app phase)

### Shareable collections + a collector Leaderboard
*Added 2026-07-14 (Mike).* Once FangTrack is a public website + app with user accounts, let
collectors **build and share their collection** as a digital showcase — the social/pride hook
that makes hobbyists want to present their collection online.

- **My Collection** — a public, shareable profile page for each user's collection (opt-in
  visibility). Portfolio value, species list, rarity mix, photos, "wanted" list. A vanity URL
  to share on Facebook groups / Discord.
- **Leaderboard** — ranks collections across many slices; "100 ways to slice it," e.g.:
  - Most valuable collection (portfolio $)
  - Most Mythic / Legendary tiers held
  - Rarest single specimen (highest rarity score owned)
  - Most *Avicularia* / most of any given genus
  - Biggest collection (species count), most complete genus, most Old-World, most New-World
  - Most sexed-female, most breeding pairs, rarest locality forms
  - Fastest-growing this month, longest-kept, most $ saved via fire deals
- **Why it matters:** turns a private tracking tool into a community/status platform; drives
  sign-ups, retention, and viral sharing. Pairs with the existing Collection portfolio value,
  rarity tiers, and canonical species foundation.
- **Prereqs:** user accounts + auth, privacy controls (public/private/friends), collection
  photo uploads, anti-gaming (verify ownership / cap self-reported value), moderation.
