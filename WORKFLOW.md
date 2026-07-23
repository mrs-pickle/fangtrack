# FangTrack — Dev/Deploy Workflow (read this before touching anything)

**The site is LIVE at fangtrack.com with real users. Never work directly on production.**
Every change flows **local → dev → main(prod)**. Prod only ever deploys from `main`, and only
after the change has been tested.

## Environments
| Tier | Where | Data | Purpose |
|------|-------|------|---------|
| **local** | your PC (`python wsgi.py` / tests) | SQLite | Fast, free, private — 90% of iteration happens here |
| **staging** *(optional, see below)* | Render, deploys from `dev` | its OWN DB (never prod data) | Full-stack pre-prod check (Postgres path, email) |
| **production** | Render, deploys from `main` | prod Postgres | Real users. Sacred. |

## Branches
- `main` = **production**. Protected. Only tested merges land here.
- `dev` = integration. Day-to-day work happens on `dev` or short feature branches off `dev`.
- **Never `git push origin main` by hand.** Prod changes happen by merging `dev → main`.
- **NEVER merge a docs-only commit to `main` on its own.** Render redeploys on ANY push to
  `main` — it does not know the change was only a `.md` file — and the 1-worker box drops
  connections for ~30-60s while it swaps, so the live site 502s. This actually happened on
  2026-07-23: two decision-log commits (`22ac205`, `9924e19`) caused two needless outages, and
  Mike's Search Console sitemap submission landed inside one of them and came back
  "Couldn't fetch". **Documentation commits stay on `dev` and ride along with the next real code
  ship.** Zero config, no wasted restarts, and the log still lands on `main` — just batched.

## The daily loop
1. `git switch dev && git pull` — start from the latest dev.
2. Make changes. **Test locally**: `python -m pytest tests/` (must pass) + drive the affected page.
3. `git push origin dev` → **CI runs** (`.github/workflows/ci.yml`). Wait for green.
4. *(If staging exists)* it auto-deploys from `dev` → verify there (Postgres + email path).
5. **REVIEW GATE (Mike's rule — never skip).** Before anything reaches prod, Mike reviews the
   batch: Claude drives a local preview (`python wsgi.py` + the in-app browser) so Mike can
   *see and click through* every change. Backend-only fixes that can't be "seen" locally get an
   explicit note of what changed and how it was verified. **Mike gives an explicit "ship it"** —
   generally at end of day. No merge to `main` without that command.
6. On Mike's "ship it", **promote**: `git switch main && git merge dev && git push origin main`
   → prod deploys once, already-reviewed.
7. Watch the deploy go **Live**; sanity-check fangtrack.com.
8. **CRAWL PROD LAST (Mike's rule).** Shipping code changes **no existing row** — crawl-time
   filters and annotations (pickup dupes, sex-from-title, source detection) only take effect when a
   crawl re-runs them and rewrites `price_history` + the `cache_blob` caches. So the order is
   **preflight → ship → confirm live → crawl**, and it must be the **prod** crawl: a local
   `main.py --all` verifies the fix but changes nothing on fangtrack.com. Skip this and the deploy
   looks shipped while users still see the old data until the 09:00 UTC cron.
   Claude can't trigger it (needs an admin session, and Claude never enters Mike's credentials) —
   Claude asks Mike to hit **Run Crawl** in `/admin`, or states plainly that prod stays stale
   until the cron.

## Rollback (when a bad deploy reaches prod anyway)
Render → `fangtrack` web service → **Events/Deploys** → find the last good deploy → **Rollback**.
~2 minutes, one click. Then fix forward on `dev`.

## Monitoring (how you find out something broke)
- **Sentry** (errors/500s) → emails you a stack trace. Set `SENTRY_DSN` env var to enable.
- **UptimeRobot** (site down) → emails/texts you within ~1 min.
- **Render** (deploy failed) → email (turn on in the service's Notifications).

## Pre-merge-to-main checklist
- [ ] `python -m pytest tests/` green locally
- [ ] CI green on the `dev` push
- [ ] Change driven/verified (locally and/or on staging)
- [ ] SQL stays portable (no `INSERT OR REPLACE`; upserts use `ON CONFLICT`) — pg adapter gotchas
- [ ] No secrets committed; render.yaml not changed casually (a sync reverts manual dashboard changes)

## Staging DB note
Render allows one free Postgres per workspace (prod uses it). A true-to-prod staging DB is a
paid Postgres (~$7/mo) — worth it because pg-adapter bugs (e.g. `RETURNING id`, ambiguous columns)
only surface on Postgres, not local SQLite. Until then: local SQLite + CI + careful batched deploys
+ Sentry is the safety net.
