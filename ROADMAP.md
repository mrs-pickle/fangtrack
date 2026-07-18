# FangTrack — Roadmap & Vision

> **The standing reference.** We review this before each morning/evening code sprint
> to pick the next moves. Mike adds to it as ideas strike; parked ideas get folded in
> here rather than living in a separate list.
>
> Last updated: 2026-07-17

---

## Launch readiness (beta) — DO FIRST, before recruiting testers

Turning the single-user local app into a multi-user hosted product. Ordered by blocker-ness.

- **[DONE 2026-07-16] User accounts + auth.** Hand-rolled in `auth.py` (no flask-login/wtf
  dep): `users` table, register/login/logout, `@login_required`/`@admin_required`, `g.user`.
  First user to register = admin and inherits pre-existing collection/watchlist rows.
  `collection` + `watchlist` carry `user_id` and are row-scoped per user. Market pages
  (Dashboard/Deals/Species/Vendors/About) stay public; personal + admin routes are gated.
  *Remaining:* per-user `settings` (SMTP/ZIP still global JSON; alert email is on the user
  row); the shared market snapshot's "owned ✓" is still global (minor cross-user marker,
  not data); alerts/saved-searches not yet user-scoped.
- **[DONE 2026-07-16] Security quick-wins.** `secret_key` from `FANGTRACK_SECRET_KEY` env;
  `MAX_CONTENT_LENGTH=5MB` (uploader DoS guard); session-based CSRF on all POST/PUT/DELETE
  (token auto-stamped into every form + `X-CSRFToken` for fetch); `SESSION_COOKIE_HTTPONLY`
  + `SAMESITE=Lax`, and `SECURE` when `FANGTRACK_HTTPS` is set. Rate limiter on login/register.
- **[DONE 2026-07-16] First-run feature tour.** 8-step welcome carousel; first-VISIT now
  (localStorage `ft_tour_v1`), replay via `?tour=1` / Settings. Re-gate on per-user
  `tour_seen` once desired.
- **[DONE 2026-07-16] Deploy prep (Render).** `wsgi.py` (gunicorn/waitress), `requirements`
  updated, `FANGTRACK_DB_PATH` env for a persistent disk, `render.yaml` blueprint,
  `.env.example`, `.gitignore`, `DEPLOY.md`. Optional in-process daily crawl via
  `FANGTRACK_DAILY_CRAWL_HOUR` + crawl-thread re-entrancy guard. **Left for Mike:** the
  actual Render upload + env vars + disk seeding + crawl-strategy choice (see DEPLOY.md §4).
- **[DONE 2026-07-16] Responsive / mobile web.** base.html mobile CSS: nav scrolls
  internally, wide tables scroll in-place, grids collapse to 1 col, padding shrinks. Page
  fits 375px with no horizontal overflow. (Native app still parked in Mid term.)
- **[DONE 2026-07-16] Onboarding empty states.** Collection/Watchlist/Alerts already have
  first-run empty messages; the feature tour covers the walkthrough.
- **[DONE 2026-07-16] Canonicalizer alias bugs.** Fixed in `normalize/synonyms.py`:
  Augacephalus rufus (was → aspinochilus), Lasiocyano sazimai (was → lasiocyaneo), and the
  systematic Melapoeus→Melopoeus misspelling (lividus/minax/albostriatus/etc.). Collection
  row + common-names map updated. Next crawl's finalize re-canonicalizes price_history.
- **[DONE 2026-07-17] Postgres backend.** Opt-in dual backend: SQLite by default, Postgres
  when `DATABASE_URL` is set (`database/pg.py` adapter translates SQLite-isms at runtime).
  SQLite path unchanged. Migration tool `tools/migrate_to_postgres.py`; `render.yaml` now
  provisions Postgres + a `fangtrack-crawl` cron worker (shared DB — solves the
  disk-can't-be-shared problem). Translation unit-tested (`test_pg_translate.py`, 13/13).
  **Left for Mike:** run `tests/test_pg_live.py` against a real Postgres (Render or Docker)
  to validate end-to-end before switching production — couldn't run in the dev sandbox.
- **[DONE 2026-07-17] Ops hardening.** Rolling pre-crawl SQLite backups (`tools/backup_db.py`,
  keep 14, wired into app/CLI/scheduled crawls); optional Sentry (env-gated, no hard dep);
  rotating file logging (`logs/app.log`); test suites for crawl-lock, backup, upload parser,
  and the full auth flow (`tests/test_ops.py`, `tests/test_auth.py`). Two fresh-deploy bugs
  caught + fixed in the process: the empty-DB dashboard 500 (market_intelligence returned a
  list) and the collection/watchlist `user_id` column init-order on a brand-new DB.
  36 tests green (core 13 · pg-translate 13 · ops 5 · auth 5).

## Near term (weeks)

- **Let daily 5 AM crawl history mature** so price trends, drops, and heating/cooling
  fully light up. (These are span-guarded and stay honest until the history exists.)
- **Wire live email delivery** of fire deals and watchlist hits (infrastructure already
  in place — needs SMTP switched on).
- **[DONE 2026-07-17] Holiday/BOGO sale badge** on deal rows — an orange 🎉 SALE/HOLIDAY/BOGO
  chip (with % when known) shows on any listing whose vendor has an active sitewide sale.
  Detection already stored these as SITEWIDE/HOLIDAY/BOGO codes; now surfaced on Deals.
- **[SCAFFOLD DONE 2026-07-17] Shareable collections + collector Leaderboard.** Opt-in public
  profile at `/u/<handle>` (privacy toggle + handle in Settings) showing species/rarity/market
  value — **purchase prices stay private**. `/leaderboard` (public, nav-linked) ranks public
  collections by most-valuable, most-species, most-Mythic, biggest, and rarest-specimen. The
  viral/sign-up engine — auth unblocked it.
  - *Still to build:* collection photo uploads · friends-only privacy tier · anti-gaming
    (ownership verification, value caps) · moderation · more leaderboard slices (per-genus,
    breeding pairs, fastest-growing) · social share-cards (OG images).

## Mid term (months)

- **A mobile app** pairing the dashboard, collection, and alerts with camera-based logging.
- **Monetization** — a free core (browse, deals, basic alerts) with paid depth (advanced
  analytics, portfolio tools, breeder/seller dashboards). A pricing decision, not a
  technical one.
- **A feeders view** (currently filtered out) as an opt-in module.
- **HerpTrack** — a sister site applying the same engine to reptiles/amphibians; the
  crawler, normalizer, and scoring layers are largely reusable.
  (Candidate vendors already collected.)
- **Browser-extension overlay** — show FangTrack market price and rarity directly on any
  vendor product page. The distribution play.

## Long term (the vision)

- **The definitive market-intelligence layer for the exotic-pets hobby** — the
  price-and-rarity brain that keepers, breeders, and sellers all consult.
- **Expansion across invertebrate categories** and, via HerpTrack, into the broader
  exotic-pet market.

---

## Open engineering items (feed the sprints above)

These are known, scoped, and ready to pick up:

- **CB/WC source coverage → 90%.** Automated evidence tops out at **61%** (that is
  everything the vendors actually tell us). Confirming a captive-bred policy for the
  vendors that have *never once* listed a wild-caught animal reaches **89.6%**. Use the
  **Vendors → Source policy** panel. The remaining ~10% sit at sellers who demonstrably
  sell *both* CB and WC (spidershoppe, tydye, arachnid_rarities, plumbs_exotics) and
  don't say which per listing — genuinely irreducible without asking them.
- **[DONE 2026-07-17] Capture product descriptions at crawl time.** `Listing.description`
  (cleaned HTML → text, capped 800 chars) captured in the shopify/woo/wix bases, saved to
  `price_history.description` via both save paths. Feeds future source/size detection.
- ~~Sale badge on deal rows~~ **[DONE 2026-07-17]** — see Near term.
- **[PARTLY DONE 2026-07-17] Residual messy species keys.** Systemic canonicalizer wins:
  strip leading stage/sex words + trailing type-nouns ("… Tarantula"), +18 valid
  genera/subfamilies to GENUS_SET, +25 high-confidence common-name aliases. Migration
  collapsed 2146→2040 distinct keys. Underground_reptiles still sells ~780 items by
  common-name-only — those are left unmapped on purpose (guessing a species = dishonest
  data; the roadmap's "irreducible" set). Revisit only if a vendor-specific description
  parse can extract binomials.
- **[DONE 2026-07-17] Vendor crawl bottlenecks.** JSON store-API bases (Shopify/Woo/Wix)
  dropped 2.0s→1.0s per-request cadence (public read APIs), natures 2.0s→1.2s. Roughly
  halves `underground_reptiles` (~154s) and `natures_exquisite` (~152s). Validated in the
  2026-07-17 review crawl.

## Principles that constrain every item above

1. **Never imply data we don't have.** We see asks, not sales. “Lowest Ask,” not “price.”
   Inferred sales are labelled inferred. Source markers show *how* we know
   (stated / vendor-confirmed / vendor-policy / inferred).
2. **Honesty is the moat.** A wrong CB label is worse than an honest “?”.
3. **Clean canonical species + accumulating daily history** is the foundation everything
   else is built on. Protect it.
