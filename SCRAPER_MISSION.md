# FangTrack Pro — Vendor Scraper Completion Mission

## Objective
Make every vendor in this project produce real, current listings when crawled, or be explicitly marked as retired with a reason. Work vendor by vendor: fix, run, verify listing count, then move on. Do not stop at "code looks right"; a vendor is done only when a live test run returns plausible listings.

## How to test a vendor
```
python main.py --vendor <vendor_key>
```
The registry in main.py is fault tolerant and will skip broken vendors with a warning. A successful vendor prints a listing count and status COMPLETE. Cross-check counts against the vendor's live site (a shop with 8 catalog pages should not yield 4 listings).

## Current state (verified July 12, 2026)
WORKING: urban_tarantulas (162 listings, Shopify products.json), arachnid_rarities (194 listings), tarantulalist.
PARTIAL: arachnoeden — connects to https://arachnoeden.org (correct domain, .com is wrong), paginates /shop/page/N/ fine, but only discovers 4 product links from the main shop grid. Real product URLs look like /shop/spiderlings/<slug>/ and /shop/females/<slug>/. The category index pages (/shop/spiderlings/, /shop/females/) likely have their own grids and pagination that are not being walked. Fix discovery so the full catalog is captured.
BROKEN PARSERS: juices_arthropods (fetches 124 product pages from sitemap, parses 0 — Squarespace, inspect actual product page HTML/JSON), joshsfrogs (site fully rebuilt, now at joshsfrogs.com/c/live_animals/arachnids/tarantulas — old paths all 301/404).
NEVER IMPLEMENTED (abstract stubs, no scrape method): spidershoppe, fear_not, exotics_unlimited, plumbs_exotics, jamies, hardcore_arachnids, buddha_bugs, natures_exquisite, tydye, marshall_arachnids, micro_wilderness, fanghub, wonderland_exotics, big_zs, pacific_northwest (pnw_arachnids), ghostys, eight_deadly_sins, swifts_inverts, fangztv, bhb_reptiles, canvas_exotics, tarantula_heaven, rooted_exotics, spider_room (class name mismatch: registry expects TheSpiderRoomScraper).
MISSING MODULE: vendors/generic_custom.py does not exist but 8 stub files import GenericCustomScraper from it. Create it (a configurable HTML catalog scraper on top of vendors/base.py BaseScraper) or rewrite those stubs on existing bases.
INTENTIONALLY SKIPPED: tarantula_spiders (site dead since 2018, leave as is).

## Approach guidance
1. For each stub vendor, first check if it is a Shopify store: GET https://<domain>/products.json?limit=5. If it returns JSON, subclass the existing shopify_base.py pattern (see urban_tarantulas.py) — these are quick wins. Do Shopify checks for all stubs FIRST to bank the easy ones.
2. For non-Shopify sites, fetch the shop/catalog page, inspect real HTML, and write a parser that extracts: scientific name, common name, size text, sex, price, product URL, availability. See models.py Listing for the full field list and vendors/arachnoeden.py for a custom-scraper example.
3. Wire every newly working vendor into: main.py registry, vendors/__init__.py, and the app's crawl path (see pipeline.py / app.py for how vendors are invoked by Run All Crawls).
4. If a vendor's site is dead, gone, or now sells nothing relevant, mark it clearly: make its scraper return a skipped status with a note (see tarantula_spiders handling) and record why in this file.

## Hard rules — do not violate
- CRAWL ETIQUETTE: minimum 2 seconds between page requests to the same vendor (base.py already throttles; do not remove or reduce it). Never parallel-hammer a single vendor. Identify with the existing user agent handling.
- SOLD OUT: listings marked sold out / out of stock must not be counted or saved. pipeline.py already filters via _is_stocked(); ensure every scraper sets availability using models.Availability values ("in_stock", "out_of_stock", etc.) so the filter works. Never invent new availability strings.
- DO NOT modify the SQLite schema, the templates/ folder, static/ assets, or anything brand-related. The UI and brand are locked.
- DO NOT touch database/market_history.sqlite contents beyond what normal crawl runs write. Backups exist in database/backups.
- Windows environment, Python 3.14. Test with `python`, not `python3`.
- If a site blocks or returns 403/429, back off and note it; do not add evasion beyond the existing rotating user agents.

## Definition of done
- `python main.py --vendor all` completes with zero "abstract class" errors and zero crash tracebacks.
- Each vendor is either COMPLETE with a plausible listing count or explicitly SKIPPED with a documented reason.
- A summary table appended to the bottom of this file: vendor_key | status | listing count | notes.
- Run All Crawls from the web app (start.bat, localhost:5000) works end to end and History records every run.

---

## Completion summary (verified July 12, 2026)

Full `python main.py --vendor all` run: **0 failures, 0 abstract-class errors, 0 crash tracebacks, 6,108 listings**. Web app Run All Crawls verified end to end (POST /sellers/crawl → pipeline → History records runs). Listing counts below are from that run's live crawls (variants found / in-stock saved after the sold-out filter). Vendors removed at Mike's direction on 2026-07-12: tarantula_heaven (content site), bhb_reptiles (no invert stock), canvas_exotics and rooted_exotics (dead domains) — files and registry entries deleted.

| vendor_key | status | listings (variants / in-stock) | notes |
|---|---|---|---|
| tarantulalist | COMPLETE | 2095 / 2095 | Aggregator. Fixed infinite ?page=N loop (site repeats grid for unknown pages) with dedup + page cap. |
| arachnoeden | COMPLETE | 153 / 153 | Was 4 listings. Real catalog is /product-category/{spiderlings,females,males,adult-males}/ with /page/N/ pagination. |
| fear_not | COMPLETE | 216 / 196 | Site is standard Shopify; replaced guess-the-path HTML crawler with ShopifyScraper. |
| spidershoppe | COMPLETE | 825 / 315 | Shopify. Domain corrected to spidershoppe.com (thespidershoppe.com is dead). |
| exotics_unlimited | COMPLETE | 68 / 64 | Shopify. |
| hardcore_arachnids | COMPLETE | 83 / 74 | Shopify. |
| buddha_bugs | COMPLETE | 201 / 138 | Shopify. Domain corrected to buddha-bugs.com (hyphenated). |
| natures_exquisite | COMPLETE | 79 / 77 | BigCommerce ClassicNext; crawled via new GenericCustomScraper (terrestrial/arboreal/semi-arboreal categories). |
| tydye | COMPLETE | 181 / 107 | Shopify. |
| marshall_arachnids | COMPLETE | 62 / 40 | Shopify. |
| micro_wilderness | COMPLETE | 124 / 71 | Shopify (www.microwilderness.com). |
| fanghub | COMPLETE | 1 / 0 | Wix. Store lists a single product (T. seladonia), currently sold out — crawler is correct, shop is just near-empty. |
| wonderland_exotics | COMPLETE | 104 / 104 | Wix; crawled via new WixScraper (store-products-sitemap.xml + embedded price/stock JSON). |
| big_zs | COMPLETE | 25 / 19 | Moved to https://www.bigzs.shop/ (Shopify). Old domains dead. |
| pacific_northwest | COMPLETE | 576 / 478 | Wix at pnwarachnids.com (old pacificnorthwestarachnids.com is dead). Largest catalog. |
| ghostys | COMPLETE | 22 / 22 | Shopify. |
| eight_deadly_sins | COMPLETE | 150 / 60 | Wix (products.json 400 was a red herring — Wix, not broken Shopify). |
| fangztv | COMPLETE | 89 / 82 | Shopify (www.fangztv.com). |
| spider_room | COMPLETE | 387 / 387 | Fixed class alias (TheSpiderRoomScraper) + parser returning CrawlResult instead of listing dicts; availability now in_stock. |
| urban_tarantulas | COMPLETE | 162 / 102 | Already working; unchanged. |
| juices_arthropods | COMPLETE | 117 / 29 | Fixed parser (was building CrawlResult with listing fields → 0 parsed). Sequential fetch (2s delay) replaces parallel Semaphore(5). Sitemap includes gear; supply filter added. |
| arachnid_rarities | COMPLETE | 194 / 70 | Already working; unchanged. |
| joshsfrogs | COMPLETE | 218 / 73 | Rewritten for rebuilt site: /c/live_animals/arachnids/tarantulas with ?page=N pagination, server-rendered Tailwind cards. |
| jamies | SKIPPED (temporary) | — | Jamie closes the Shopify storefront periodically (password wall). ShopifyScraper now detects /password / 401 and skips with a "temporarily closed" note; crawling resumes automatically when she reopens. Do not retire. |
| plumbs_exotics | SKIPPED | — | Ecwid JS storefront; prices/stock rendered client-side, static HTML has only the SPA shell. Nothing reliable to parse without a headless browser. |
| swifts_inverts | SKIPPED | — | Active site is swiftinverts.com, a legacy frameset with free-form price-list text (no per-item markup). No structured catalog. |
| tarantula_spiders | SKIPPED | — | Pre-existing intentional skip (site stale since 2018, email-order only). Unchanged. |

### Infrastructure added/fixed
- `vendors/generic_custom.py` — NEW configurable HTML catalog scraper (BaseScraper + category walk + pagination + supply filter). Unblocks the 8 stubs that imported it.
- `vendors/wix_base.py` — NEW WixScraper base (sitemap discovery, per-page embedded price/stock parse, sold-out detection).
- `vendors/retired.py` — NEW RetiredScraper base: returns status="skipped" + documented REASON instead of crashing.
- `vendors/shopify_base.py` — password-wall detection (temporarily closed stores skip cleanly and auto-resume).
- `vendors/__init__.py` — REGISTRY rewritten to the real scraper classes (was pointing at incompatible stubs.py engine); now fault-tolerant and identical to main.py's registry. This is what the web app's Run All Crawls iterates.
- `main.py` / `app.py` — stdout/stderr reconfigured to UTF-8: cp1252 Windows consoles crashed on ″ size marks (rich table) and the 🕷 banner emoji.
- Crawl etiquette preserved throughout: 2s min delay per vendor, sequential fetches only, canonical models.Availability values so pipeline's sold-out filter works.
