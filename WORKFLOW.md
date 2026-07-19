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

## The daily loop
1. `git switch dev && git pull` — start from the latest dev.
2. Make changes. **Test locally**: `python -m pytest tests/` (must pass) + drive the affected page.
3. `git push origin dev` → **CI runs** (`.github/workflows/ci.yml`). Wait for green.
4. *(If staging exists)* it auto-deploys from `dev` → verify there (Postgres + email path).
5. When a batch is solid, **promote**: `git switch main && git merge dev && git push origin main`
   → prod deploys once, already-verified.
6. Watch the deploy go **Live**; sanity-check fangtrack.com.

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
