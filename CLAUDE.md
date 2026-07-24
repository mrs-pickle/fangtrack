# FangTrack — Project Guardrails (CLAUDE.md)

FangTrack: Flask/Jinja2 market-intel app for the exotic-invert hobby. Crawls ~29
vendor sites daily, normalizes listings, scores deals/rarity, serves a dashboard.
Local dev = SQLite + Windows/Python 3.14. Prod = Render (Postgres) at fangtrack.com.

## Locked design constants (no change without Mike's written OK in chat)
- **DEPLOY WORKFLOW (never break prod):** the site is LIVE with real users. Work
  `local → dev → main`; **prod deploys ONLY from `main`, only after tests pass**. Never
  `git push origin main` by hand or edit prod directly. Full process in `WORKFLOW.md`.
  **Session start: confirm the working branch is `dev` (not `main`) before making changes.**
  **REVIEW GATE: no merge to `main` until Mike has reviewed the batch (Claude drives a local
  preview so he can click through) and given an explicit "ship it" — generally end of day.**
- **DOCUMENTATION CADENCE (Mike's rule, 2026-07-21): update this Decision log at least every
  24 hours AND after every big decision set / ship.** Each entry: what changed, WHY, the
  gotcha, and prod status. Don't let a session end undocumented (we lapsed 07-20→07-21 and had
  to reconstruct 72h). Claude proactively reminds Mike to do this when a work batch wraps or a
  day rolls over; a daily scheduled reminder also fires. Memory: [[documentation-cadence]].
- Brand, UI, `templates/`, `static/` — locked; visual/brand changes only at Mike's direction.
  **The brand system is `BRANDBOOK.md`** (2026-07-19 rebrand: blue #2563eb + purple accent,
  oklch rarity ladder, translucent-vs-filled treatment rule). Colours live in
  `tokens/fangtrack.css` + `tokens/fangtrack.tokens.json`; rarity/deal colours ONLY in
  `theme.py`. Never invent a hex — derive it per BRANDBOOK.md §0 and keep the parity tests
  (`tests/test_tokens.py`, `tests/test_core.py`) green. Emails follow BRANDBOOK.md §13 via
  `render_email()` + `templates/email/`.
- Crawl etiquette: **≥2s between requests to the same vendor**, sequential per vendor,
  no parallel-hammering, existing rotating UAs only — no evasion beyond that.
- `models.Availability` values are canonical ("in_stock"/"out_of_stock"/…). Never invent new ones.
- Sold-out listings are never counted or saved (pipeline `_is_stocked()` filter).
- Prod web = **1 gunicorn worker** on Render Standard (1 CPU/2GB). render.yaml `plan: standard`
  is pinned (a `plan:` value there reverts the instance type on every blueprint sync).
- Web is **read-only for heavy builds** (`_WEB_READONLY`): it never builds dashboard/species
  caches on a request. The cron builds + persists them (`cache_blob`); the web only loads them.

## Conventions
- Design/brand: `BRANDBOOK.md` is the reference for ANY visual work (colors, type, badges,
  components, emails, voice). New colours are DERIVED (oklch formula + treatment rule), not
  picked. Token changes bump the `?v=` on base.html's `/tokens/fangtrack.css` link.
- Backend: SQLite default; Postgres when `DATABASE_URL` set (`database/pg.py` adapter).
  Raw sqlite3 style (`?`, PRAGMA, sqlite3.Row). Keep SQL portable — the adapter only
  translates a bounded set of SQLite-isms (no `INSERT OR REPLACE`; use DELETE+INSERT).
- Scrapers report **facts only**. Deal grades + rarity tiers are computed by the engine
  (`scoring/`), never inside a scraper.
- Keep `fetch()` and `parse()` separated; `parse()` stays offline-testable against fixtures.
- Test a vendor: `python main.py --vendor <key>`. Tests: `python -m pytest tests/` (must pass).
- Windows local: `python` (3.14), not `python3`.
- New working vendor → wire into main.py registry, vendors/__init__.py REGISTRY, and app crawl path.
- **Google Analytics on EVERY page (Mike's rule, 2026-07-21):** the gtag.js snippet
  (`G-06WHKW6W8K`) rides in base.html `<head>`, so every page that `{% extends "base.html" %}`
  is covered automatically. Any NEW page/response that does NOT extend base.html (standalone
  HTML, a bespoke print/export view, a new microsite) MUST include the same snippet right after
  `<head>` — never ship a user-facing page without it. Emails are exempt (mail clients strip JS).
- Caches (snapshot/market/movers/intel/summary/rarity_legend/species/browse): 1h TTL,
  invalidated + persisted by the crawl.

## Never-do (without explicit written approval)
- Don't modify DB schema, `templates/`, `static/`, or brand for scraper/feature work.
  (Infra/perf schema additions like `cache_blob` are separate, flagged decisions.)
- Don't touch `market_history.sqlite` contents beyond normal crawl writes (backups in database/backups).
- Don't reduce/remove crawl throttling (2s/vendor min stays). A Mike-APPROVED residential
  rotating proxy (to beat datacenter-IP blocks) is OK; no other evasion (no CAPTCHA-solving,
  no header spoofing beyond the rotating UAs).
- Don't warm heavy caches in a boot-time thread on the web (restart-loops the 1-core box).
- Don't push render.yaml casually — a sync re-applies plan/start-command/env, reverting manual changes.
- Don't enter live credentials (API keys, DB passwords) into fields for Mike — direct him to.

## Scraper contract
1. Subclass the right base: `shopify_base.ShopifyScraper` (check `/products.json?limit=5` first),
   `wix_base.WixScraper`, `generic_custom.GenericCustomScraper`, or `retired.RetiredScraper`
   (dead sites → status="skipped" + REASON).
2. Extract per listing: scientific name, common name, size text, sex, price, product URL, availability.
3. Emit `CrawlResult` with listing dicts; set canonical availability so the sold-out filter works.
4. Dead/empty/blocked → skip with a documented note (don't crash, don't retire silently).
   403/429 → back off + note, no evasion.
5. Verify with a live run; cross-check count vs the vendor's real catalog size.

## Decision log (newest first)
- 2026-07-23 (late) — PROD CRAWL + SITEMAP HARDENING SHIPPED (live 1270411). Mike ran the prod
  Run Crawl; it was the FIRST time `apply_key_aliases` had ever executed on production (see the
  entry below for why it never had). RESULT: the whole accumulated alias backlog collapsed at once —
  species catalog **1,312 → 1,222 (−90)**, matching the ~80–100 predicted from local. Tester's
  duplicate closed: /species/aphonopelma%20seemani now 404s, seemanni 200s. Site stayed healthy
  through the in-process crawl (/healthz 0.19–0.21s, no flap on the 1-core box — the threads 4→8
  change continues to hold; homepage briefly 2.8s while caches warmed, then back to 0.28s).
  FLAW FOUND BY VERIFYING RATHER THAN ASSUMING: the crawl heals `price_history` immediately (so the
  fragment's page 404'd right away) but the SITEMAP is built from the CACHED species catalog, which
  lags — so for the length of that window the sitemap advertised a URL that 404s, which Search
  Console reports as "Submitted URL not found (404)". Confirmed it was NOT an HTTP/edge cache (a
  cache-buster returned the same bytes). Waiting would have fixed this instance but the window
  reopens on EVERY future crawl that merges a fragment, so the fix is structural: the sitemap now
  filters every key through `canonicalize_key` and skips any non-canonical form, plus de-dupes
  (two fragments can canonicalize to the same URL). A fragment can no longer be advertised even
  while it is still sitting in the cache. Final prod sitemap: 1,228 urls / 1,222 species, 0
  misspellings, well-formed; 12/12 randomly sampled URLs return 200 (spot-checked as Googlebot
  would). LESSON: "the data is fixed" and "the site shows it fixed" are different claims — anything
  built from a cache needs checking separately from the table it derives from. Mike has GA4
  (14-month retention + internal-traffic filter) and Search Console done; sitemap URL handed over
  for submission: https://fangtrack.com/sitemap.xml
- 2026-07-23 — SEO/ANALYTICS INFRA + TESTER FIXES SHIPPED (dev→main, live 948052a; CI green on the
  matching SHA, 95 tests). Context: Mike wants best-practice infrastructure but NO ads / no SEO push
  this year — growth is organic sharing into invert communities. (a) LINK PREVIEWS were the actual
  gap: base.html had ZERO Open Graph tags and no meta description, so every link pasted into a FB
  group / Reddit / Discord unfurled as a bare URL (reads as spam). Added OG + Twitter card +
  canonical + a generated 1200x630 card (static/img/og_default.png, built from brand tokens).
  Species pages describe the animal from REAL data ("Market price $150 · 26 listings in stock ·
  14 vendors · all-time low $61"), built only from values we HAVE so a preview never shows "$None".
  Pages override with `{% set og_title/og_description %}` — child-set VARS, not Jinja blocks, because
  a block would also emit its text into <head>. og:image is ABSOLUTE (relative paths are silently
  dropped by every scraper). (b) PRODUCT EVENTS: GA4 alone reports pageviews, which can't answer
  "does the product work" — added sign_up, collection_import, watchlist_add, saved_search_create and
  vendor_click. vendor_click matters most (sending a buyer to a vendor IS the product); it's
  delegated from document so every table/tile/card is covered without opt-in. The others end in a
  POST→redirect with no page left to fire from, so track_event() queues in the session and the next
  page emits them exactly once (capped at 5; can never raise into a real request). (c) SITEMAP:
  /sitemap.xml built from the CACHED catalog (read-only web never rebuilds on a request), robots.txt
  advertises it, GOOGLE_SITE_VERIFICATION env var renders the GSC meta tag so verifying needs no
  deploy. Prod: 1,318 urls / 1,312 species. lastmod is PER-SPECIES (last date we actually observed a
  listing) — the first version stamped today on all ~1,200 pages every request, which is a lie told
  daily and exactly how crawlers learn to ignore the field. DECIDED AGAINST GTM (value is letting
  non-devs add tags; we have one tag and a deploy takes minutes — it would buy ~100KB, CSP
  complexity and debug indirection for nothing until there are ad pixels). (d) BETA TESTER 1
  ("Prices are all looking good!" — the 07-22 price batch holds, they verified it): MATURE MALE
  rendered as "?" — we parsed Spider Shoppe's "Mature Male" variant correctly (sex=MM) but the
  TEMPLATE only knew F and M, so MM and U (seller-stated unsexed) both fell through to "?", i.e. the
  site denied knowing something the vendor plainly stated, on every mature male and every unsexed
  animal. Root fix: ONE shared macro (templates/_sex.html) used by species_detail/deals/collection/
  labels — four templates each had their own copy, and vendor_detail.html had ALREADY handled MM
  correctly with nothing propagating. Also found en route: sizes rendered `2-3""` / `Adult"` (an inch
  mark appended unconditionally). (e) THE REAL FIND — A. seemanni showed as TWO cards though the
  seemani→seemanni alias had shipped days earlier: `_apply_key_aliases` was wired into
  app.run_crawl_thread (the ADMIN in-process crawl) ONLY, so the prod cron
  (scheduled_crawl.py → run_multi_vendor_pipeline) never called it — the alias healing had NEVER run
  on production, meaning every alias ever added (84 typo merges, Dominican Purple, …) sat unapplied.
  Moved into pipeline.apply_key_aliases, called from run_multi_vendor_pipeline where the cron AND the
  admin crawl converge; app._apply_key_aliases is now a thin delegate. THIRD instance of this exact
  shape (two snapshot builders → three listing writers → two crawl-completion paths) so a test now
  fails if it drifts. GOTCHA: the first CI "success" I saw was the PREVIOUS commit's run — always
  match head_sha before merging. Fragment merge only takes effect after a prod crawl runs the new
  pipeline. Mike did the GA4 (14-month retention, internal-traffic filter) + Search Console setup.
- 2026-07-22 (late) — SHIPPED the beta-tester batch (dev→main, live 386ac5e; CI green, 82 tests)
  + ran a full local crawl (29 vendors, 28 complete, 0 failed, 10.1 min, 8,807 raw). Prod verified:
  /, /deals, /species all 200 in 0.27-0.43s, "Est. landed" + estimate tooltip live, 0 discount codes.
  CAUGHT POST-SHIP by verifying the crawl instead of trusting the commit: the pickup filter did NOT
  clear the phantoms locally — 118 rows survived. ROOT CAUSE: there are THREE write paths, not two.
  `main.py --all` (the CLI) calls `database.db.save_listings()` directly, which bulk-INSERTs into
  price_history and never sees `pipeline._is_livestock`. The PROD cron (`scheduled_crawl.py`) uses
  `run_multi_vendor_pipeline`, which DOES gate — so prod was never affected and clears on its 09:00
  UTC run; only the CLI diverged. FIX: the same pickup gate now lives in `save_listings`, so CLI and
  cron agree about what is in stock. Re-crawled spidershoppe + fear_not: pickup rows 118 → 0
  (snapshot 3,921 → 3,797). LESSON (same shape as the two-snapshot-builder bug earlier the same
  day): this codebase has PARALLEL paths for the same job — two snapshot builders, three listing
  writers. A filter or annotation added to one is NOT in effect until every path has it, and the
  only way to know is to exercise the path the user/cron actually runs, not the one under test.
  NOTE: the CLI path also skips `_is_stocked`; sold-out rows are filtered by the scrapers upstream
  today, but that divergence is unguarded — worth folding into save_listings next session.
- 2026-07-22 (pm) — BETA-TESTER DATA-QUALITY batch (on `dev`, 221200f + 37dcd7a, HELD for Mike's
  ship word). Tester: "wrong prices and cb/wc statuses, sex missing when it's listed on the vendor's
  website" + one animal showing twice. DIAGNOSIS FIRST: the PRICES were correct in the raw crawl
  data ($48/$48/$124 moderatum, $58 versicolor) — the confusion was three price columns plus stale
  discount codes. (a) PICKUP DUPES: vendors list a local-pickup copy beside the shippable one, so
  one animal counted twice — `is_pickup_only()` + a gate in `pipeline._is_livestock` drops 124
  phantom listings (118 Spider Shoppe "[Vancouver Pick-up]", 6 Fear Not). They slipped through
  because `is_livestock` strips a leading "[...]" prefix. Crawl-time filter → existing rows clear on
  the next crawl. (b) DISCOUNT CODES suppressed via `DISCOUNT_CODES_ENABLED = False` (Mike: "leave
  the code column and filter, just remove all the codes until we figure a better way to scan them")
  — suppressed in CODE, not by clearing the table, so prod is fixed on deploy regardless of its own
  rows; 0/3,874 now carry a code. Scanner rework is next-session work. (c) HONEST LABELS:
  "Landed"/"Shipped" → "Est. landed"/"Est. shipped", `~` prefix + "Estimate… Not a quote" tooltip
  (it read as a real checkout total; it's price + the vendor's flat rate). (d) SEX FROM TITLE (real
  bug, 134 suspects → 127 fixed): each scraper reads only its OWN variant field, so sellers who put
  the sex in the TITLE ("Aphonopelma chalchodes - Male", variant '3"') showed Unknown across ALL
  vendors at once. `sex_from_title()` + `annotate_missing_sex()` recovers 127 listings over 8
  vendors (76F/30M/21 unsexed), fill-only (0 overwrites — a variant fact always wins). WHOLE WORDS
  only: never normalize_sex's single-letter codes (they collide with size/locality notation), and
  "PAIR M+F" stays Unknown (not one sexed animal). (e) CB/WC LABEL BUG (silent, the actual "wrong
  statuses"): a spec line "CB/WC: WC" was read as **CB**, because the LABEL contains "CB" and the
  both-mentioned tie-break trusts CB → wild-caught animals reported as captive-bred. `_LABELLED_RE`
  now reads the value AFTER the label. Added `detect_source_type_in_prose()` for descriptions but
  deliberately restricted to unambiguous signals — the loose version "resolved" 289 unknowns off
  "breeder"/bare "cb"/"F2" in marketing copy, i.e. it would have FABRICATED a source; the strict one
  fills 0 today, by design. Source misses re-measured: 0. GOTCHA/LESSON (cost a second commit):
  there are TWO snapshot builders — `pipeline.py`'s AND `app._build_snapshot` (the one every page
  reads). The sex fix landed only in pipeline, so the site still showed Unknown; caught by verifying
  the RENDERED snapshot (817→944 sexed) instead of trusting green unit tests. Any listing-level
  annotation must be added to BOTH or the site and the cron-built cache disagree. 82 tests green
  (9 new, tests/test_listing_facts.py). NOT bugs, verified: the versicolor 0.5" sling really is
  unsexed (nobody sexes slings) and the moderatum rows already carried F/M/MM.
- 2026-07-22 — SPECIES-SEARCH + EMAIL-LOGO SHIPPED (dev→main, live 3f4fdd3); LIGHT MODE v2 +
  COLLECTION RESOLVER built on dev (HELD). (a) SPECIES SEARCH rebuilt: the native <datalist>
  submitted the whole "Genus species (Common)" string but species_search matched by SUBSTRING of
  each field individually — the combined string is longer than any field, so a pick NEVER matched
  (silently broke autocomplete for every common-name species). Replaced with an ID-based ARIA
  combobox + `/api/species/suggest` (ranked exact›prefix›token›fuzzy, token-aware so 'poecil metal'
  → P. metallica, synonym-aware via a key_aliases reverse index, + hobby nicknames gbb/obt/gooty).
  Selecting navigates by the STABLE KEY, which structurally kills the whole bug class. Ranks the
  cached ~1k catalog in Python — no pg_trgm, identical on SQLite+PG. (b) AUGACEPHALUS RUFUS =
  "Peach Earth Tiger" (curated map wrongly overrode the correctly-harvested name with "Red Baboon");
  3 fragments (augacephalus/aspinochilus/phormingochilus sp rufus) collapsed to one. (c) EMAIL LOGO:
  Mike's lockup in the header; emails stay DARK with the WHITE logo variant (a light-email pass was
  built then reverted on his call). (d) tools/species_audit.py — conservative fragment audit;
  AUTO-SUGGESTS only same-genus near-duplicate displays (typos, 132 found), and lists
  same-epithet-cross-genus + shared-common-name as REVIEW-ONLY, because those are mostly
  coincidental (Archispirostreptus gigas ≠ Hysterocrates gigas; Heterometrus silenus ≠ spinifer) and
  auto-merging them would be WRONG. (e) COLLECTION 404 BUG (Mike: 3 species had no market value +
  404): collection.species_key was derived from whatever text was typed, so common names ("Peach
  Earth Tiger"), trade names and misspellings matched NO card; and `_apply_key_aliases` only heals
  price_history, NEVER the collection table — so even Dominican Purple (which HAS a working alias)
  stayed broken on a stale stored key. FIX: `resolve_species_key()` — ONE resolver for any user text
  (canonicalized key → exact catalog key → exact COMMON NAME → fuzzy ≥0.86), applied at collection
  render so legacy rows heal with no migration. All 36 local rows now resolve (was 3 broken); also
  fixes misspellings (hamori→hamorii) and common names (green bottle blue→Chromatopelma). LESSON:
  any table storing a species_key needs the same resolver — price_history was the only one being
  healed. (f) LIGHT MODE v2 (dev, HELD): rebuilt off the approved light-email palette; muted slate
  scale (page #e3e5ea, soft-grey cards — never pure white, fixing "too bright"/"tiles too white"),
  header 🌙/☀️ toggle persisted via cookie + users.theme_pref, theme-swapped logo (white lockup dark /
  black lockup light, 40px to match live), ~561 hexes→vars across 33 templates (each var's DARK value
  == the old hex so DARK IS BYTE-IDENTICAL). Page-by-page sweep clean (only intentional semantic
  fills remain). GOTCHA: Flask runs debug=False so templates/CSS are CACHED — restart the preview
  server after edits or you review stale UI. Mike's local preview is ALWAYS port 5050 (5000 does not
  work on his machine) — memory [[local-preview-port]].
- 2026-07-21 (pm) — EMAILS + GA SHIPPED (dev→main, live 00cf9db); LIGHT MODE built but HELD on a
  branch. Preflight-gated (73 tests, pg scan, compile) then shipped. (a) BRANDED ALERT + WATCHLIST
  EMAILS: both now extend base_email.html (wordmark, black bg/white text) + a stat bar; each
  scientific name HYPERLINKS to the exact listing (species-page fallback so it's always clickable)
  instead of a bare URL line; one-click UNSUBSCRIBE (itsdangerous-signed token → `/unsubscribe/<t>`
  sets `users.email_opt_out`, clears alert_categories; public route, auth-skip) + "manage
  preferences" in the shared footer. `_maybe_email` + the watchlist digest now send the branded
  multipart mail (plain-text fallback kept); admin `/email-test/<name>` + `/email-preview` for both.
  TEST SENDS delivered to mike@fangtrack.com from prod (also confirmed the Resend key works — closed
  the long-open #98). Mike saw the watchlist email render and APPROVED its light look as the basis
  for the future site light mode. (b) COLLECTION UPLOAD: stop folding the Common Name column into
  notes (notes = the Notes column only). (c) GOOGLE ANALYTICS: gtag.js (G-06WHKW6W8K) after <head>
  in base.html (covers every base-extending page); CSP script-src/connect-src widened for
  googletagmanager + google-analytics; NEW RULE in Conventions — every user-facing page carries the
  GA tag (standalone pages add it manually). (d) DEAD TOOLS removed: move_collection.py (Mike ran the
  collection move manually in Render), scan_source_policy2.py. (e) CLOUDFLARE: scanned via Chrome —
  the cache rule is CORRECT (OR expr /static/+/tokens/, Eligible-for-cache, Edge TTL ignore-cc 1-day,
  0 Page Rules) yet the edge STILL returns cf-cache-status:DYNAMIC even after a forced disable→enable
  REDEPLOY. Zone-side anomaly → PARKED: open a CF support ticket. Low impact (assets are
  immutable+1yr, cached in-browser regardless). (f) LIGHT MODE (HELD, branch `feature/light-mode`
  134e409, NOT shipped): header 🌙/☀️ toggle → data-theme on <html>, persisted via cookie +
  users.theme_pref; 535 hardcoded dark hexes → CSS vars across 33 templates (each var's DARK value ==
  the old hex, so dark is byte-identical — only light activates). Mike's feedback: tiles still
  black-bg, white too bright, logo must swap (spider icon + black "FANG"). GA + emails were SPLIT OUT
  of this branch and shipped separately so light mode could keep cooking. Redo next session off the
  approved EMAIL look; Mike provides the logo asset at session start. GOTCHA/LESSON: bundling GA into
  the light-mode commit meant a `git branch feature/light-mode` + `reset --hard` split, then
  re-applying GA cleanly to dev — keep independently-shippable features in separate commits.
  Memory: [[light-mode-wip]]. (g) CRAWL (local, on request): 29/29 complete, 9m43s, 3,592 in-stock —
  vendor-by-vendor within ±0–6 of this morning's prod 09:00 crawl (pulled from prod Crawl History).
- 2026-07-21 — SPECIES/COLLECTION polish + canonicalization (SHIPPED, dev→main). Follow-ups after
  Mike click-through. (1) Collection table now SORTABLE by any column — the global sorter can't
  handle the interleaved hidden edit rows, so a dedicated sorter in collection.html keeps each edit
  row paired to its display row on reorder. (2) UPLOADER read no sizes: `_COL_ALIASES["size"]` only
  matched headers containing "size"; broadened to leg span/legspan/DLS/length/current size/cm/…
  (size is stored as a free-text note, so wider header matching was all it needed). (3) DEDUP: one
  dropdown entry per trade-name species — Phormictopus sp. "Dominican Purple" had fragmented into
  3 keys (dropped "sp"/dropped genus). Added KEY_ALIASES collapsing them to `phormictopus sp
  dominican` (Holothele sp. Dominican blue dwarf stays distinct). ROOT GAP: canonicalize_key ran on
  NEW rows (db.record) but nothing re-canonicalized HISTORICAL rows on prod (tools/migrate_key_
  aliases.py is raw sqlite3 — can't touch Postgres). Added portable `_apply_key_aliases()` (pg
  adapter) wired into the crawl completion so fragments self-heal every crawl. (4) IN-STOCK toggle:
  confirmed #141 already matches Mike's spec (ON = in-stock only; OFF/default = all WEBSITE species
  incl out-of-stock with history, private sellers excluded) — no change. Note: "Dominican Purple
  not in stock" was NOT a bug — the in-stock copies are private sellers (hidden from non-owners) +
  the website copy (Juices) is sold out; Fear Not's wasn't in the last crawl.
- 2026-07-21 — BIG UX+TRUST+PERF batch SHIPPED (dev→main, live as 8780a42 + follow-ups 29199c3,
  7a2cfe7). Preflight-gated (73 tests, pg-portability scan, compiles) then Mike "ship it". (a) TOP
  DEALS rebuilt: `_curated_top_deals()` — tarantulas only (traits.TARANTULA_GENUS_DEFAULTS), in-stock,
  ONE per species, ranked by deal-grade+rarity, round-robined across price tiers (no more 4 curly-
  hairs / all $10 slings); rows show sex ♀/♂ + vendor links to the EXACT listing. (b) OWNED ✓ leak:
  the owned flag was baked into the SHARED snapshot from the global collection → logged-out visitors
  saw the admin's checkmarks; moved to per-request `_req_owned()` (empty for anon), also stripped
  from the shared intel blob. (c) FEEDER roaches: bulk "(25 count)" packs with no invert genus now
  denied by the livestock filter (Josh's Orange Head Roaches were showing as deals). (d) SPECIES:
  facet counts are now INTERSECTION-aware (Advanced+$250+ shows the real 4, not the global 63);
  In-Stock-Only toggle above Origin (live>0). (e) PRIVATE-SELLER RULE (Mike's call): private lists
  NEVER create species pages — get_species_catalog is WEBSITE-ONLY (killed the augacephalus/
  phormictopus-sp 404s + the private leak into the public catalog; full-site scan → 0 404s); private
  imports fuzzy-CONNECT to the nearest existing species (difflib ≥0.9, so typos link but distinct
  species never merge). (f) ALERTS rebuilt to PERSONAL + opt-in categories (Mike's pick): saved-
  search hits always alert their owner; market events (fire/drops/restocks) only if the user opted
  in (users.alert_categories, toggles on /account) — empty watchlist+no opt-in = 0 alerts (was 94).
  (g) UPLOADER: the collection INSERT used sqlite-only :named params → 500 on prod Postgres (the real
  "uploader broken", separate from the earlier IS ?→= ? fix); converted to positional ?. CSRF was a
  red herring — base.html JS stamps _csrf into every form. (h) SLOWNESS: server+Brotli were fast
  (0.3-0.6s, 30-40KB wire); the DECOMPRESSED DOM was heavy (/deals 445KB @100 rows), so deals 100→50
  and species 75→50 per page. (i) URBAN still-showing-on-drops: ban code was correct but the movers
  are served from a stale cron BLOB → added `_filter_banned_movers()` at RENDER time so the ban holds
  regardless of blob freshness (drops now empty because Urban WAS the whole list). (j) CACHE-REBUILD
  GAP: get_species_catalog/browse had no `force=` and short-circuit under _WEB_READONLY, so an
  in-process (admin Run Crawl) warm_and_persist re-persisted the STALE catalog; added force= +
  warm_and_persist(force=True). GENERAL LESSON: on the read-only web, any cache accessor that
  warm_and_persist rebuilds MUST accept force= or it re-persists stale data (get_snapshot already
  did; catalog/browse didn't).
- 2026-07-20 — PROD INCIDENT + HARDENING SHIPPED (live in ba6c873): recurring "HTTP health check
  timed out after 5s" flaps (6:35/7:18/8:05 AM CDT), self-recovered each time — NOT a crash/OOM (mem
  ~15%, CPU low). Root cause from live logs: single gunicorn worker saturated by BOT crawlers
  (ClaudeBot hammering /species/* 50-113KB, /species?page 270KB, /history 420KB) starving the 5s
  health probe; worst when overlapping the daily crawl's PG writes. FIXES: gunicorn --threads 4→8
  (validated — the in-process Run-Crawl on 07-21 ran with NO flap); /healthz + /robots.txt bypass the
  auth before_request (cookieless, CDN-cacheable); /robots.txt curbs bot load (Crawl-delay + disallow
  /*?,/history,/api); in-process daily-crawl scheduler hard-refuses to arm when DATABASE_URL is set.
  Verified: FANGTRACK_DAILY_CRAWL_HOUR NOT on prod web; FANGTRACK_PROXY_URL IS (unexpected, harmless).
- 2026-07-20 — UX + TRUST batch — SHIPPED (dev→main, ba6c873; was HELD, Mike shipped). (1) TRUST
  (critical): mrs2200's
  private-seller list surfaced in global "all-time-low" alerts on other accounts. Private-seller
  uploads write real crawl_runs+price_history rows, so species_market_stats (all-time-low/market
  price) + the snapshot-based fire mover included them, and the alerts engine emitted fire/drop/back
  events UNTAGGED (=global) off the unfiltered crawl snapshot. Fix: `private_seller_keys()` +
  exclude platform='private_seller' from species_market_stats & market_movers; alerts strip private
  sellers from the snapshot before movers+saved-search match, and saved_search events now carry the
  owner's user_id. (drops/back already excluded them via product_url IS NOT NULL.) Test added.
  (2) URBAN banned from dashboard movers (inflate-then-cut premium display specimens make fake
  "biggest drops") — `BANNED_MOVER_VENDORS` in market_movers (covers cron blob+web+alerts) + dashboard
  snap; still on /deals+species. (3) MOVER tiles: vendor name now links to that exact listing
  (product_url, new tab) on fire/drops/back, dashboard + /movers. (4) HEALTH: dashboard "N down" now
  agrees with Crawl History/Vendor QA — classify from each vendor's latest COMPLETE/PARTIAL run (not a
  later write-guard 'rejected'/'skipped' run); complete=healthy (write-guard already rejects real
  collapses), so fanghub (legit-empty social) is no longer "down". Cleared 4 local false-downs.
  (5) ADMIN merge: single `/admin` hub = Users + Crawler (nav dropped separate Crawler+Users links);
  Vendor QA already admin-gated. (6) SETTINGS consolidated onto `/account` ("Account & Settings"):
  name + public profile + display prefs for all users, admin-only Site Settings section; header ⚙
  gear removed; /settings GET→/account. Fixed latent bugs found en route: Run-Crawl + profile forms
  lacked _csrf (would 400); leaderboard/alerts linked non-admins to admin-only /settings (403).
  NOTE: settings.html's Change Password posted to a nonexistent /settings/password route — omitted;
  a real self-service password change is a follow-up. LTC on /deals = legit ("Long-Term Captive"
  source type in normalize/source_type.py), not a bug — left as-is. INFRA (shipped-ready, see below):
  gunicorn --threads 4→8 + /robots.txt. All 70 tests green; dashboard/admin/account render-verified.
- 2026-07-20 — PROD INCIDENT: health-check-timeout flap (NOT a crash), diagnosed + hardened (on
  `dev`, HELD). Render alerted "HTTP health check failed (timed out after 5s) while running your
  code" at 6:35 + 7:18 AM CDT, self-recovered each time (SAME instance 2wcft, no restart). Metrics:
  memory ~15% of 2GB, CPU near-baseline → NOT OOM, NOT a crash, NOT my dev code (still on dev). ROOT
  CAUSE from live logs: the single gunicorn worker (1-CPU box) gets briefly saturated by BOT-CRAWLER
  traffic on heavy pages — ClaudeBot (`+claudebot@anthropic.com`) hammering `/species/*` (50-113KB)
  and `/species?page=*` (~270KB) and `/history` (**420KB**) back-to-back — and at 6:35 that overlapped
  the daily crawl's Postgres WRITE load, so all 4 request threads were tied up on slow free-PG queries
  and `/healthz` couldn't answer within Render's 5s window → flagged, then recovered when the DB freed.
  Also fired 2:17 + 3:28 PM yesterday (non-crawl times) → it's general worker-starvation, not
  crawl-specific. Verified in Render: `FANGTRACK_DAILY_CRAWL_HOUR` is NOT set on the web (so the
  in-process crawler is NOT running); `FANGTRACK_PROXY_URL` IS set on the web (unexpected — the web
  doesn't crawl; harmless but flagged). HARDENING SHIPPED to dev (e03d80e): (1)
  `_start_daily_crawl_scheduler()` hard-refuses to arm when DATABASE_URL is set (future-misconfig
  guard — an in-process web crawl would OOM/flap the box). (2) `/healthz` now bypasses the auth
  `before_request` entirely → pure in-memory 200, no user-load/session/CSRF, a slow DB can never delay
  the probe (also drops a pointless Set-Cookie on it). +1 test (69 green). OPEN LEVERS (need Mike):
  (a) gunicorn `--threads 4→8` in render.yaml (memory has huge headroom) for concurrency slack;
  (b) curb bot load — Cloudflare edge-cache `/species/*` + a rate-limit/Bot-Fight rule (ties into the
  still-DYNAMIC CF cache ticket), and/or a `robots.txt` Crawl-delay; (c) paid Postgres (#106) for DB
  headroom. `/history` at 420KB is also a fat page worth capping.
- 2026-07-19 — DATA-QUALITY fixes (on `dev`, HELD for Mike's ship word). (1) COLLECTION-UPLOAD pg bug:
  `_insert_collection_rows` used `WHERE user_id IS ?` → the pg adapter emits invalid `IS $1` → every
  logged-in collection upload 500'd on prod. `user_id` is always the current (non-null) user here, so
  `= ?` is correct AND portable. Grepped: no other `IS ?` left. (2) SIZE picked the ADULT grow-size
  from body text: Great Basin's $8 T. vagans sling showed "5-6\"" mined from "grow to be a moderate
  size of about 5-6 inches". `extract_size_from_description` step-3 guard only blocked
  `full grown|adult size|matures|max size` — missed the prose forms. Added `_ADULT_SIZE_CTX`
  (adds `grows to|grow to be|can grow/reach|reach(es)|leg span|ultimate size`); when the only size
  sits in that context we return None (Unknown) rather than stamp the species' adult leg span on a
  sling. Also fixed a latent step-1 bleed (a "Current Size: 3/4\" Full Grown Size: 5-6\"" window ran
  past the label and `extract_size_from_title` took the LAST token = 5-6\"; now takes the FIRST token
  in the labelled window). Great Basin's true per-specimen sizes live only in Wix variant OPTIONS the
  bulk GraphQL doesn't fetch → they become Unknown, which is honest (tracked: size-gap vendors). Stale
  5-6\" rows self-correct on the next crawl (scraper re-derives size_text). Tests: test_size.py +2
  (adult-grow-size never grabbed; labelled current-size still wins). (3) Urban G. actaeon "$9061 vs
  $2350" — NOT a bug: the vendor genuinely asked a premium on a 5\" female "DISPLAY specimen" (variant
  literally titled "…F'in wow!"), since dropped to $2350; the daily crawl already re-caught it at
  $1774. `market_price` is a TRIMMED median (drops single hi+lo) so the premium never polluted it — it
  can only surface as all-time/90d HIGH (a true fact). Left analytics untouched (no silent change
  before the review gate). Added `tools/inspect_listing.py` (read-only snapshot inspector, mirrors
  data_qa.py). NOTE: also need to log the SHIPPED trust+admin+speed+mobile batch below.
- 2026-07-19 — SHIPPED trust + admin + speed + mobile batch (merged dev→main, live as 886e29d).
  (a) TRUST: private sellers are now per-user private — a `vendors.user_id` owner column + request-time
  `_visible_to_user()` filter so a private_seller upload is visible ONLY to its uploader (closes the
  cross-user source-leak IDOR); `/sellers` import is `@login_required` (was admin) and stamps
  `user_id`; delete is owner-or-admin. Collection gained an opt-in leaderboard toggle (`/collection/share`,
  private by default). (b) ADMIN: custom `/admin/users` panel (name, email, links to each user's
  collection + watchlist; never selects password_hash) + registered-users count + metrics strip.
  (c) ACCOUNT: `/account` + `/account/name` let a user set first/last name in settings (NOT asked at
  signup); display name stays public, real name private (leaderboard shows display name). (d) SPEED
  1-6: species price-history LIKE→indexed equality; species picker scoped to 3 endpoints; header-meta
  memoized; species_detail chart downsampled ≤400 pts; tokens `Cache-Control: immutable`. Species
  detail 1.8s→0.7s (-62%), landing -23%. (e) MOBILE 1-6: breakpoint tokens (.hide-sm/.mobile-first/
  .species-layout/.stat-strip-2), 16px inputs (no iOS zoom), 44px tap targets, source legend on deals,
  nth-child column hiding. GOTCHA that cost a failed deploy (a357763): a SEMICOLON inside a SQL `--`
  comment in db.py's vendors CREATE TABLE broke the pg adapter's `split_script` (it splits on `;` but
  does NOT skip `--` comments) → CREATE split mid-statement → Postgres syntax error at boot → "Exited
  with status 1". SQLite parsed it fine so all 66 tests (SQLite-only) passed. Fix (886e29d): removed
  the semicolon. LESSON: never put `;` in an inline SQL comment; the split_script comment-blindness is
  a known adapter limit. Post-migration: 28 healthy / 1 down, migrations applied clean, no errors.
  CLOUDFLARE: origin headers now perfect (public/immutable, no Set-Cookie/Vary:Cookie) but edge still
  `cf-cache-status: DYNAMIC` after purge + Dev-Mode-off → concluded CF-side, needs a support ticket.
- 2026-07-19 — SHIPPED perf batch + CDN + PROXY-FROM-RENDER FIXED (thesis-critical). Merged to prod:
  (a) perf batch (dropped Tailwind Play CDN → static utility CSS; memoized species-card analytics
  5s+→~1.2s warm; polling tamed: alerts once-on-load, crawl-status 3s active/60s idle; proxy
  keepalive `httpx.Limits(max_connections=1, keepalive=600)` = one IP per vendor). (b) Static assets
  CDN-cacheable: the CSRF `before_request` wrote `session["_csrf"]` on EVERY request, so a Set-Cookie
  (+`Vary: Cookie`) rode on `/static` + `/tokens` → Cloudflare refused to cache. Fix: skip user-load
  + CSRF write for `/static`+`/tokens` paths (public, GET-only); `SEND_FILE_MAX_AGE_DEFAULT=1d`.
  (c) THE PROXY BUG: `FANGTRACK_PROXY_URL` on the **cron** was the whole cURL command
  (`curl -v -x http://…`), not a URL → httpx "Unknown scheme" → every proxied vendor died → only 3
  non-proxy vendors returned (the recurring "3-vendor crawl"). Mike fixed the env to the clean URL;
  then a 407 (Proxy Auth) surfaced from a paste typo — corrected against IPRoyal's CONNECTION panel
  (`http://<user>:<pass>@geo.iproyal.com:12321`, 1.99GB traffic left, Authenticated mode). Watched
  prod crawl then RECOVERED: 27/29 vendors, ~3,644 IN-STOCK (~7k raw pre-sold-out-filter); Underground
  all 65 pages (950 raw→57 in-stock); the 2 "down" are benign (fanghub=FB/IG drops always 0;
  feared_to_fascinated=429 rate-limited that run, write-guard kept last-good). NOTE: in-stock ~3,644 is
  the real healthy number — the "7.1k" in the older entry below was RAW (pre-filter). CLOUDFLARE cutover
  is LIVE (Porkbun NS → amos/tia.ns.cloudflare.com; SSL Full); cache rule added for `/static`+`/tokens`
  but edge still `cf-cache-status: DYNAMIC` post-fix+purge (Dev Mode off) — likely fresh-zone lag,
  REVISIT (re-check HIT; else CF support). Proxy password was printed to Render/Sentry logs by the
  "Unknown scheme" error — rotate the IPRoyal pw when convenient. `tools/move_collection.py` (dry-run
  migration, mrs2200→mike@fangtrack.com) deployed but NOT YET RUN — blocked from prod Render shell by
  the safety classifier; needs Mike to run it (or grant shell access). Daily cron unchanged: 09:00 UTC.
- 2026-07-19 — CRAWLER + DATA-QUALITY batch (on `dev`, reviewed, HELD for Mike's ship word).
  (1) Residential rotating proxy wired: `FANGTRACK_PROXY_URL` → `vendors/base.py` httpx `proxy=`
  (unset = direct), + `_throttle` jitter (2s floor + 0–1.5s). Local full scan through IPRoyal =
  29/29 vendors healthy, ~7.1k listings (was ~6/29, 3,645 on Render's datacenter IP). Also removed
  the hard-coded `Accept-Encoding: …br` header (CDNs returned undecodable brotli → JSON fails).
  (2) Per-vendor WRITE-GUARD in `run_multi_vendor_pipeline`: a run that collapses vs its last good
  (>=10 → <20%, not truncated) is finished status='rejected' (excluded from the snapshot) so the
  site keeps last good data + health shows 'down'; rejects once then accepts a confirmed low.
  (3) Honest dashboard health: `_dashboard_header_meta` classifies each ACTIVE scanner's latest run
  healthy/partial/down (was always "all healthy"). (4) Vendor QA on /sellers now admin-only.
  (5) SIZE FIX (all crawlers): `extract_size_from_title`/`parse_size` now read mixed numbers
  ("3 1/2\"" → 3.5, not 1/2); backfilled locally, self-corrects on next crawl. (6) Deals sticky
  headers restored on mobile. Monitoring live: Sentry (web+cron) + UptimeRobot. tester/12345 seed.
- 2026-07-19 — FULL REBRAND (Mike-approved in chat, dedicated design session): adopted the
  FangTrack Design project palette. Primary #1a73e8→#2563eb (+#3b82f6 links), purple #a855f7
  promoted to accent, zinc neutrals (#0a0a0b/#141417/#1c1c21/#2a2a31/#f4f4f5/#a1a1aa), fire
  #ff6b00→#f97316. NEW rarity system in theme.py: cores on oklch(0.66 0.20 H) ladder
  (pink→purple→blue→teal→green→gray), pills translucent (core@15% bg, @35% border); deal
  badges FILLED (solid core). Hues now shared across systems BY DESIGN (treatment
  disambiguates) — except Exceptional 💎💎 keeps exclusive violet #7c3aed (NOT #a855f7 as the
  Design draft had) so Legendary can never be confused with it. Tokens: tokens/fangtrack.css
  (+.tokens.json) served at /tokens/fangtrack.css, linked by base.html; tests/test_tokens.py
  enforces parity, test_core.py rewritten to the new invariants. ~640 mechanical hex swaps
  across all templates. PNG logo assets are monochrome white silhouettes (pixel-scanned) —
  rebrand-proof, no re-export needed. Branded multipart email infra added same day
  (render_email + templates/email/, /admin/email-preview/<name>); welcome copy APPROVED by
  Mike + wired into /register (best-effort, never blocks signup).
- 2026-07-19 — Deep security pass. FIXED: arbitrary-file-read (`/settings` + `/digest` now
  `@admin_required`; `digest_path` no longer user-writable); SECRET_KEY hardening (prod-like env
  with no key uses an EPHEMERAL random key, never the repo fallback — not a hard raise because the
  cron imports app.py too); Secure session cookie default in prod. Added `FANGTRACK_ADMIN_EMAILS`
  allowlist (promotes listed emails to admin at boot; promote-only). Audit verified SOUND: CSRF,
  SQL-injection (all parameterized incl. pg adapter), password hashing/reset, collection/watchlist
  IDOR scoping, file upload, open-redirect, login/register/forgot rate-limits.
- 2026-07-19 — Security round 2 (M1/M2/L3 FIXED): alerts saved-searches + feed now scoped to
  `user_id` (remove verifies ownership — closes the cross-user IDOR); registration NEVER grants
  admin (M2 — admin only via the allowlist); CSP added (allows Tailwind CDN + inline + https images,
  restricts the rest). Also fixed the same From-address bug in alerts `_maybe_email`. Auth test
  updated to the allowlist model; `_csrf` test helper uses /collection (settings is admin-only now).
- 2026-07-19 — `cache_blob` upsert MUST use `ON CONFLICT(name) DO UPDATE` (not DELETE+INSERT): the pg
  adapter auto-appends `RETURNING id` to a plain INSERT and cache_blob has no id → "column id does not
  exist" and warm_and_persist silently skipped (site showed 0). ON CONFLICT makes the adapter skip it.
- 2026-07-19 — APPROVED a residential rotating proxy (~$50/mo) for the crawler. Why: Shopify's
  `products.json` blocks Render's datacenter IP (only ~5/29 vendors returned data); a residential
  IP alone got blocked too, so it must ROTATE. Plan: `FANGTRACK_PROXY_URL` env → route base.py's
  httpx client through it; add crawl-time jitter. Amends the "no evasion" rule above. Thesis-critical.
- 2026-07-19 — Email `From` must be a verified-domain address (`noreply@fangtrack.com`, settable via
  `MAIL_FROM`), NOT the SMTP username. Resend accepts the SMTP session but silently drops mail whose
  From isn't a verified sender — this is why the first test emails never arrived. `send_email` logs in
  as `smtp_user` but sends From `mail_from`.
- 2026-07-18 — Precompute: cron builds all dashboard/species caches → JSON in new `cache_blob`
  table; web is `_WEB_READONLY` and only loads them. Why: ~130s cold build on the request path
  jammed the 1-core health check → restart loop; removes builds from the web entirely.
- 2026-07-18 — render.yaml `plan: standard` pinned; web=1 worker; analytics cached 1h.
  Why: fit Render Standard, stop OOM + 5s-health-check flap.
- 2026-07-18 — Email via Resend (smtp.resend.com); `/submit`+resets+alerts use it;
  `NOTIFY_EMAIL=mike@fangtrack.com`. Why: transactional deliverability for launch.
- 2026-07-18 — Live on Render/Postgres at fangtrack.com; DNS + Resend DKIM/SPF/DMARC verified.
- 2026-07-18 — Security headers added (nosniff/X-Frame/Referrer/HSTS). Deep security pass pending.
- 2026-07-19 — Dev-safety pipeline: `dev` branch + `main`=prod; CI (`.github/workflows/ci.yml`,
  pytest on push) gates merges; Sentry ready (set `SENTRY_DSN` env to enable). Workflow in
  `WORKFLOW.md`. Reason: yesterday's 15+ reactive prod pushes broke the live site repeatedly.
- OPEN ITEMS: SHIP the `dev` batch (rebrand + tokens + emails + onboarding + tester seed + proxy
  + write-guard + honest health + admin-gated QA + size/mobile fixes) — reviewed + green, HELD for
  Mike's explicit ship word; on ship: merge dev→main, resume the suspended cron, run ONE watched
  prod crawl (repopulates caches + is the "beats datacenter block" proof), seed tester/12345 on prod.
  Then: nurture campaign (reminder set Aug); paid Postgres + backups before ~mid-Oct expiry
  (reminder set Sep). Crawler-500 FIXED; proxy DONE. 2026-07-21: collection move mrs2200→
  mike@fangtrack.com DONE (Mike did it manually in Render — move_collection.py now dead code);
  IPRoyal proxy pw ROTATED (done). Still-open Render nicety (deferred, not urgent): remove the
  stray FANGTRACK_PROXY_URL from the WEB service env (web doesn't crawl; leave it on the cron).
- PARKED (2026-07-24) — ON-PAGE COPY / CONTENT (Mike: "park these ideas and let's discuss later.
  No decision as of now."). Question was whether to add copy (species summaries, explanations of
  deal grades) and whether it would help search. ANALYSIS TO PICK UP FROM: the deciding split is
  UNIQUE vs BOILERPLATE. (a) A "what is a deal grade / how market price works" block is the SAME
  text on 1,222 pages — repeated boilerplate adds no unique content, so it does NOTHING for
  rankings, but it does close the trust gap beta tester 1 kept probing ("are these numbers
  right?"). Do it for USERS, expect no search benefit; pairs with the parked freshness-stamp item.
  (b) Hand-written per-species descriptions: RECOMMENDED AGAINST — 1,222 of them is either a huge
  manual project or AI mass-generation, which is exactly Google's "scaled content abuse" spam
  pattern and hard to undo once indexed; it also competes with Tarantula Collective/forums on
  husbandry authority instead of on market data, which is FangTrack's actual unique claim.
  (c) THE SWEET SPOT, if we do anything: a trait-derived sentence per species, composed from the
  EXISTING `normalize/traits.py` badges (verified 400/400 sampled species have full data —
  hemisphere/habitat/size/temperament/experience/climate). e.g. "An Old World arboreal tarantula
  from tropical Asia. Large, defensive and fast — for experienced keepers. No urticating hairs,
  but potent venom." Unique per species, TRUE (derived from our own structured data, not invented),
  useful to a buyer, and sidesteps scaled-content risk because it is a spec sheet in prose.
  ~1 day, mostly composition rules. ALSO DECIDED: ignore Semrush's "low text-to-HTML ratio" and
  "low word count" as goals in themselves — Google has no word-count ranking factor and
  thin-content penalties target pages with NO unique value; a page with 26 live listings, price
  history and rarity is not thin. Padding to satisfy that warning would make the product worse.
- PARKED (2026-07-22) — COMPETITOR-DERIVED FEATURES (Keepa / StockX / TCGplayer research;
  Mike: "park these and let's discuss in the future"). Context: FangTrack ALREADY matches the
  core of all three — price history (Keepa), Market Price as a trimmed median of recent sales
  (TCG's exact methodology), all-time-low + 52-week range (StockX), collection tracker with
  portfolio value/gain-loss (TCG), watchlist targets, saved searches, movers. The gap is data
  QUALITY + TRUST, not feature count.
  BETA MUST-HAVES (small, trust-affecting):
    a. **Collection CSV EXPORT — confirmed MISSING** (import exists, export does not). TCG lets
       you export; no-export reads as lock-in to a tester who just handed you their collection.
    b. **Visible "as of / last scanned" freshness stamp** on species card + dashboard — Keepa
       updates hourly and says so; a market price without a timestamp isn't trusted.
    c. **One-click "Alert me under $X"** on the species card. The pieces exist (watchlist target,
       saved-search max_price) but Keepa's whole loop is threshold→notify in ONE action.
    d. Mobile pass on the light mode (SHIPPED 07-22, so this is now live-relevant — testers
       open on a phone first).
  FUTURE IDEAS (ranked):
    1. **BROWSER EXTENSION** — Keepa's actual moat (4M+ users) is overlaying price history on the
       retailer's page while you shop. A FangTrack overlay showing market price + deal grade +
       rarity on a vendor's product page is the highest-leverage differentiator we have.
    2. Price-premium % per listing ("23% above market") — StockX; we already compute market price.
    3. Liquidity/availability signal ("6 vendors, in stock 80% of days") — StockX volume analog;
       arguably MORE useful here than for sneakers since rarity drives buying.
    4. Portfolio value over time chart (TCG/StockX) — history already stored.
    5. Have/Want/Trade lists + community layer (TCG social) — keepers trade slings constantly.
    6. Surface vendor reliability from the Vendor QA data we already collect.
    7. Longer term: PWA/mobile app, public API.
- PARKED (2026-07-21, Mike's list — pruned 2026-07-23):
  - ~~LIGHT MODE~~ **DONE** — shipped 2026-07-22 (theme toggle + swapped logo + muted slate palette,
    live). Only remnant is the mobile pass, tracked as beta must-have (d) above.
  - ~~GA Tag Manager + web-service expansion~~ **RESOLVED**: Search Console DONE (property verified,
    sitemap submitted), Bing Webmaster DONE, GA4↔GSC link DONE, GA4 hygiene DONE (14-month
    retention + internal-traffic filter). **GTM: DECIDED AGAINST** — its value is letting non-devs
    add tags without a deploy; we have ONE tag and a deploy takes minutes, so it would buy ~100KB of
    script, CSP complexity, a second consent surface and debug indirection for zero gain. Revisit
    only if ad pixels or a marketing contractor arrive.
  - **Cloudflare edge cache still DYNAMIC** (STILL OPEN) — rule is correct (OR expr, eligible,
    1-day edge TTL, no Page Rules) and a disable/enable redeploy did NOT fix it → open a CF support
    ticket (zone-side). Low impact: assets are immutable+1yr and cached in-browser regardless.
  - **Discount-code scanner rework** (STILL OPEN) — codes are suppressed in code
    (`DISCOUNT_CODES_ENABLED = False`) since 2026-07-22; the column + filter remain. Needs a better
    way to scan/verify codes before re-enabling.
  - **Stray `FANGTRACK_PROXY_URL` on the WEB service env** (STILL OPEN, minor) — the web doesn't
    crawl; leave it on the cron, remove from web when convenient.
  - SEARCH/GOOGLE — remaining, small: `/family/<genus>` pages are real content but are NOT in the
    sitemap (add when next in there). EXPECTED-NOT-A-BUG: robots.txt `Disallow: /*?` blocks every
    query-string URL (incl. `/species?page=2` and all facets), so GSC will report them as "Blocked
    by robots.txt" — deliberate, it curbs the bot load that caused the 07-20 health-check flaps;
    species detail pages are path-based and fully crawlable.
