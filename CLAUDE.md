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
  Then: move Mike's collection mrs2200 → mike@fangtrack.com; nurture campaign (reminder set Aug);
  paid Postgres + backups before ~mid-Oct expiry (reminder set Sep). Crawler-500 FIXED; proxy DONE.
