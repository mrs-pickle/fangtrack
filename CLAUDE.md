# FangTrack — Project Guardrails (CLAUDE.md)

FangTrack: Flask/Jinja2 market-intel app for the exotic-invert hobby. Crawls ~29
vendor sites daily, normalizes listings, scores deals/rarity, serves a dashboard.
Local dev = SQLite + Windows/Python 3.14. Prod = Render (Postgres) at fangtrack.com.

## Locked design constants (no change without Mike's written OK in chat)
- Brand, UI, `templates/`, `static/` — locked; visual/brand changes only at Mike's direction.
- Crawl etiquette: **≥2s between requests to the same vendor**, sequential per vendor,
  no parallel-hammering, existing rotating UAs only — no evasion beyond that.
- `models.Availability` values are canonical ("in_stock"/"out_of_stock"/…). Never invent new ones.
- Sold-out listings are never counted or saved (pipeline `_is_stocked()` filter).
- Prod web = **1 gunicorn worker** on Render Standard (1 CPU/2GB). render.yaml `plan: standard`
  is pinned (a `plan:` value there reverts the instance type on every blueprint sync).
- Web is **read-only for heavy builds** (`_WEB_READONLY`): it never builds dashboard/species
  caches on a request. The cron builds + persists them (`cache_blob`); the web only loads them.

## Conventions
- Backend: SQLite default; Postgres when `DATABASE_URL` set (`database/pg.py` adapter).
  Raw sqlite3 style (`?`, PRAGMA, sqlite3.Row). Keep SQL portable — the adapter only
  translates a bounded set of SQLite-isms (no `INSERT OR REPLACE`; use DELETE+INSERT).
- Scrapers report **facts only**. Deal grades + rarity tiers are computed by the engine
  (`scoring/`), never inside a scraper.
- Keep `fetch()` and `parse()` separated; `parse()` stays offline-testable against fixtures.
- Test a vendor: `python main.py --vendor <key>`. Tests: `python -m pytest tests/` (must pass).
- Windows local: `python` (3.14), not `python3`.
- New working vendor → wire into main.py registry, vendors/__init__.py REGISTRY, and app crawl path.
- Caches (snapshot/market/movers/intel/summary/rarity_legend/species/browse): 1h TTL,
  invalidated + persisted by the crawl.

## Never-do (without explicit written approval)
- Don't modify DB schema, `templates/`, `static/`, or brand for scraper/feature work.
  (Infra/perf schema additions like `cache_blob` are separate, flagged decisions.)
- Don't touch `market_history.sqlite` contents beyond normal crawl writes (backups in database/backups).
- Don't reduce/remove crawl throttling or add scraping evasion.
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
- 2026-07-18 — Precompute: cron builds all dashboard/species caches → JSON in new `cache_blob`
  table; web is `_WEB_READONLY` and only loads them. Why: ~130s cold build on the request path
  jammed the 1-core health check → restart loop; removes builds from the web entirely.
- 2026-07-18 — render.yaml `plan: standard` pinned; web=1 worker; analytics cached 1h.
  Why: fit Render Standard, stop OOM + 5s-health-check flap.
- 2026-07-18 — Email via Resend (smtp.resend.com); `/submit`+resets+alerts use it;
  `NOTIFY_EMAIL=mike@fangtrack.com`. Why: transactional deliverability for launch.
- 2026-07-18 — Live on Render/Postgres at fangtrack.com; DNS + Resend DKIM/SPF/DMARC verified.
- 2026-07-18 — Security headers added (nosniff/X-Frame/Referrer/HSTS). Deep security pass pending.
- OPEN ITEMS: shipping scan PG bug (`origin_zip` ambiguous → skipped); a few vendors
  (Big Z's, Fear Not, Urban Tarantulas) return non-JSON to Render's IP; rotate DB password +
  Resend key (both exposed in chat); change admin pw; free Postgres expires ~90d.
