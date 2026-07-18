# FangTrack — Deployment Runbook

Everything to take FangTrack live on **Render** at **fangtrack.com**, with a
populated Postgres database. Steps you (Mike) perform in a browser/terminal are
marked **👉 YOU**. Everything else is already done in the repo.

---

## 0. What's already done (in the repo)
- Clean git repo, initial commits, **no secrets or databases committed** (`.gitignore` blocks all `*.sqlite`, `.env`, `tracker_settings.json`, `backups/`).
- `render.yaml` blueprint: Postgres + web service (gunicorn) + nightly crawl cron.
- Playwright/Chromium removed from the build (unused → fast, reliable Render builds).
- `wsgi.py` gunicorn entry, `/healthz` health check, Postgres adapter (`database/pg.py`).
- In-app **Change Password** (Settings) so you can secure the admin after migration.
- 35/35 tests passing.

---

## 1. 👉 Create the GitHub repo & push
The repo `github.com/mrs-pickle/fangtrack` doesn't exist yet (push failed "not found").

1. GitHub → **New repository** → name **`fangtrack`** → **do NOT** initialize with README/.gitignore/license → **Create repository**.
2. Back here, I'll run the push (it's staged and ready on branch `main`). If you'd rather run it yourself:
   ```bash
   cd D:\fangtrack\fangtrack_v2
   git push -u origin main
   ```
   (First push will prompt you to authenticate to GitHub in a browser — that's expected.)

> The three commits contain only code/templates/assets — verified zero DBs or secrets.

---

## 2. 👉 Create the Render services (Blueprint)
1. Render dashboard → **New +** → **Blueprint**.
2. Connect your GitHub and select the **`fangtrack`** repo. Render reads `render.yaml`.
3. It will provision **three things**: a Postgres DB (`fangtrack-db`), the web service (`fangtrack`), and the nightly cron (`fangtrack-crawl`).
4. Render will **prompt for the `sync:false` env vars** (SMTP — see §4). You can leave them blank for now and add later; the app launches fine without email.
5. Click **Apply**. First build takes ~2–3 min (no Chromium now).

---

## 3. Environment variables — complete reference

### Web service `fangtrack`
| Variable | Value | Set by | Purpose |
|---|---|---|---|
| `FANGTRACK_SECRET_KEY` | *(auto-generated)* | render.yaml (`generateValue`) | Signs session cookies |
| `FANGTRACK_HTTPS` | `1` | render.yaml | Secure-only cookies (Render is HTTPS) |
| `PYTHON_VERSION` | `3.12.7` | render.yaml | Runtime |
| `DATABASE_URL` | *(from Postgres)* | render.yaml | Activates Postgres backend |
| `FANGTRACK_BASE_URL` | `https://fangtrack.com` | render.yaml | Absolute links in reset emails |
| `FANGTRACK_PROXY_HOPS` | `1` | render.yaml | Real client IP behind Render's proxy (rate limiter) |
| `SMTP_HOST` | e.g. `smtp.gmail.com` | 👉 you (prompted) | Password-reset + digest email |
| `SMTP_PORT` | `587` | 👉 you (prompted) | " |
| `SMTP_USER` | your sending address | 👉 you (prompted) | " |
| `SMTP_PASS` | app password (see §4) | 👉 you (prompted) | " |
| `NOTIFY_EMAIL` | your address | 👉 you (prompted) | Default digest recipient |
| `SENTRY_DSN` | *(optional)* | 👉 you | Error tracking, off unless set |

### Cron service `fangtrack-crawl`
`DATABASE_URL` (auto) + the same `SMTP_*` / `NOTIFY_EMAIL` (prompted) if you want the nightly digest emailed.

> If you ever need `FANGTRACK_SECRET_KEY` manually, here's a fresh one you can paste:
> `8ea6071e5e2718a23669bed935c336d018f4fb92e2cf0e1f52d394b69f8154a8`
> (Render already auto-generates one, so you normally don't need this.)

---

## 4. 👉 SMTP (for password reset + digests) — optional but recommended
Without SMTP, password-reset **links are only written to the server log** (users can't self-reset). To enable real email:
- **Gmail:** Google Account → Security → 2-Step Verification → **App Passwords** → generate one for "Mail". Use `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER=you@gmail.com`, `SMTP_PASS=<the app password>`.
- Or any provider (SendGrid, Mailgun, Fastmail) with its SMTP host/port/user/pass.
- Ideally use a **fangtrack.com address** once your domain email is set up.

---

## 5. 👉 Migrate the market data into Postgres
Populates the live site with the full catalog (~3k listings, species, rarity, deals) so testers see a working product on day one.

1. In Render → `fangtrack-db` → **Connect** → copy the **External Database URL** (starts `postgres://…`). This is a secret — keep it private.
2. On your PC:
   ```powershell
   cd D:\fangtrack\fangtrack_v2
   $env:DATABASE_URL = "<paste the External Database URL>"
   python tools/migrate_to_postgres.py
   ```
   It creates the schema on Postgres and copies every table (idempotent — safe to re-run). Expect a couple of minutes.
3. Unset it so you don't accidentally point local dev at prod:
   ```powershell
   Remove-Item Env:\DATABASE_URL
   ```

> This brings your existing admin login (`mrs2200@proton.me` / `12345`) and your personal collection. Your collection stays **private to your account**. Fix the password in the next step.

---

## 6. 👉 Secure the admin account (do this immediately after migration)
1. Visit `https://<your-render-url>` (or fangtrack.com once DNS is live) → **Sign in** with `mrs2200@proton.me` / `12345`.
2. **Settings → 🔒 Change Password** → set a strong password.
3. (Optional) If you want a fangtrack-branded admin email, register a **new** account with that email — the **first** account is admin, but since migration already created one, use the existing admin and just change its email in the DB, or ask me to add an email-change field. Simplest for launch: keep the proton address as the admin login with the new strong password.

---

## 7. 👉 Custom domain fangtrack.com
1. Render → `fangtrack` web service → **Settings → Custom Domains** → **Add** `fangtrack.com` and `www.fangtrack.com`.
2. Render shows the DNS records to add. At your **domain registrar**:
   - `fangtrack.com` → the ALIAS/ANAME (or A record) Render gives, **or** a `CNAME` for `www` → `<your-app>.onrender.com`.
   - Follow Render's exact values (they differ for apex vs www).
3. Wait for DNS propagation (minutes to a few hours). Render auto-issues the SSL cert.

---

## 8. 👉 First crawl on the live site
The nightly cron runs at **09:00 UTC**. To populate/refresh immediately without waiting:
- Render → `fangtrack-crawl` cron → **Trigger Run** (manual run), **or**
- Sign in as admin → **Crawler** tab → **Run Crawl**.

Watch the cron logs — you'll see `(TRUNCATED)` / `(recovered)` markers. If the big Shopify vendors throttle from Render's IP too, the snapshot keeps their last-good data (see the throttling notes we discussed).

---

## 9. ✅ Verification checklist
- [ ] `https://<render-url>/healthz` returns `{"status":"ok"}`
- [ ] Home page loads with data (after migration), shows vendor + listing counts
- [ ] Register a throwaway account → it's a normal (non-admin) user
- [ ] Deals / Species / a species card render; trait filters work
- [ ] Sign in as admin → Settings → change password succeeds
- [ ] (If SMTP set) `/forgot` sends a reset email
- [ ] Custom domain resolves with a valid padlock (HTTPS)

---

## 10. Notes & caveats
- **Render free Postgres** expires ~90 days and has size/connection limits — fine for beta; upgrade before it lapses or export/reimport.
- **Free/starter web** may cold-start (spin down when idle) — first hit after idle is slow. Upgrade the web plan if testers notice.
- The **crawler throttling** on the 5 big Shopify catalogs may or may not persist from Render's datacenter IP. If it does, ping me — I have a staggered slow-lane ready to add.
- Don't commit the SQLite DB or `.env` — `.gitignore` already blocks them, but don't force-add.
