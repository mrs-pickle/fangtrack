# FangTrack — Gap & Error Review

_Full-app scan, July 2026. Grouped by priority. Items marked ✅ were fixed during this review._

---

## Fixed during this review
- ✅ **Livestock filter rewritten** — genus-anchored, two-tier deny. Top Deals no longer show postcards/vials/bark/feeders. 2,154 junk rows purged.
- ✅ **Watchlist over-matching** — empty species keys matched every target (433 bogus hits → 25 real). Now a precise binomial match.
- ✅ **Exotics Unlimited undercount** — systemic Shopify filter bug dropped whole genera; now captures the full catalog (56 → 236 products).
- ✅ **Vendor "Buy/Shop" links** — 16 vendors had no homepage; now derived from each scraper's BASE_URL.
- ✅ **Crawl hang guard** — a per-vendor 30-min timeout so one stuck site can't leave the app "running" forever.
- ✅ **Sex-probability column** — removed (heuristic wasn't defensible).

---

## HIGH — worth doing next

1. **Automated / scheduled crawls.** Everything depends on someone clicking *Run All Crawls*. Without a scheduler the data goes stale and email alerts can never fire on their own. Add an in-app scheduler (APScheduler) or a documented Windows Task Scheduler job that hits the crawl on a daily cadence.

2. **Email delivery is not wired.** Settings collects an address and the digest is built, but nothing sends. Connect a mail provider (SendGrid/Mailgun/SES) and send the fire-deals + watchlist-hits digest. Until then the "get alerts" promise is unmet.

3. **Crawls run fully serially (~30 vendors, one at a time).** A full crawl takes 15–25 min, dominated by the two big sites (pnw 613 pages, juices 117). Crawl etiquette is *per-vendor*, so different vendors can run concurrently — a small worker pool (e.g. 4–6) would cut wall-clock ~4–5×. Biggest single UX win.

4. **"Free Ship" and "Discount" columns on Deals are dead placeholders** (`—`) even though the data exists (shipping rates for 26 vendors, 7 discount codes in the DB). Wire them to the `vendor_shipping` and `discount_codes` tables — low effort, and right now they read as broken.

## MEDIUM

5. **Rarity score methodology** deserves the same scrutiny the sex-probability column just got. Document how it's computed and confirm it's data-derived, not hand-tuned — the app's credibility rests on defensible numbers.

6. **Size parsing gaps → deals hidden.** Many listings have no parsed size, so they're capped at 👍 Fair (can't confirm a discount). Better size extraction from variant titles/ranges would surface more genuine deals. Highest-leverage data-quality work.

7. **CB/WC and common-name coverage is thin** — lots of `?` and blank common names. Expanding the source-type inference and common-name dictionary improves filtering and search.

8. **Deals table renders all 6,000+ rows and sorts them client-side.** Fine now, but it'll get sluggish as history grows. Add server-side pagination or lazy rendering before it becomes a problem.

9. **Dead code / cleanup:** `vendors/stubs.py` is fully superseded and unused — delete it to avoid confusion. `annotate_sex_probability` is still computed in `get_snapshot` though the column is gone — drop the call. The two vendor registries (`main.py` + `vendors/__init__.py`) are duplicated and must be kept in sync by hand — unify them.

10. **Vendor health signal.** Closed/dead vendors (e.g. Jamie's password wall) silently contribute nothing. A "last successful crawl / listing count" health badge on the Sellers page would make it obvious when a scraper has silently broken.

## SECURITY — before any hosted/Phase-2 launch

11. **No authentication.** The app is wide open. Anyone who can reach it can trigger crawls, import lists, and see everyone's private-seller data. User accounts + auth are a hard prerequisite for hosting.

12. **Hardcoded Flask `secret_key`** (`"tmt-local-secret-2026"`). Move to an env var and rotate before exposure.

13. **No CSRF protection** on POST forms (crawl, import, watchlist, submit). Add Flask-WTF/CSRF tokens once there are real users.

14. **If ever bound to `0.0.0.0`**, it's exposed on the LAN with no auth. Keep it on `127.0.0.1` until auth exists.

15. **Private-seller multi-user model.** Uploaded lists currently live in one shared table with no owner. For the hosted product, scope them to the uploading user and decide the sharing policy explicitly (the About page frames this as Phase 2/3).

## LOW / polish

16. **Windows console encoding** is patched in `main.py`/`app.py`, but any new entrypoint (scheduler, worker) needs the same `reconfigure(encoding="utf-8")` guard.
17. **Submissions** (new) are stored but there's no admin view — add a simple authenticated list when auth lands.
18. **`config.yaml` says `engine: playwright`** but the crawlers use httpx; the field is misleading — align or remove it.
19. **No automated tests.** A handful of unit tests around `normalize.livestock`, the deal scorer, and each scraper's parser would catch regressions (the livestock filter alone went through ~6 iterations this session).
