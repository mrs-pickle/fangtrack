#!/usr/bin/env python3
"""
Standalone full crawl — parallel scrape + discount scan + pipeline + digest.

Runs independently of the Flask app (used by the OS scheduler for the nightly
crawl). Mirrors app.run_crawl_thread but with no web state.

    python scheduled_crawl.py
"""
import sys, os, asyncio, logging, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Create logs/ BEFORE configuring the FileHandler below — on a fresh cron
# filesystem the dir doesn't exist yet, and the handler is built at import time
# (before main()'s makedirs), so without this the whole cron crashes on startup.
os.makedirs("logs", exist_ok=True)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout),
              logging.FileHandler("logs/scheduled_crawl.log", mode="a", encoding="utf-8")],
)
log = logging.getLogger("scheduled_crawl")

CONCURRENCY = 5
PER_VENDOR_TIMEOUT = 1800
RECOVERY_COOLDOWN = 120     # seconds to let a rate-limit bucket refill before re-scan
RECOVERY_DELAY = 3.0        # gentler per-request pacing during the recovery pass


async def crawl_all():
    from vendors import REGISTRY
    keys = list(REGISTRY.keys())
    sem = asyncio.Semaphore(CONCURRENCY)
    results = []

    async def one(vk):
        async with sem:
            try:
                scraper = REGISTRY[vk]()
                res = await asyncio.wait_for(scraper.scrape(), timeout=PER_VENDOR_TIMEOUT)
                if res.listings:
                    log.info(f"[{vk}] {len(res.listings)} listings"
                             + (" (TRUNCATED)" if getattr(res, "truncated", False) else ""))
                    st = res.started_at.isoformat() if getattr(res, "started_at", None) else None
                    fin = res.finished_at.isoformat() if getattr(res, "finished_at", None) else None
                    return (vk, scraper.VENDOR_NAME, res.listings, st, fin,
                            getattr(res, "truncated", False))
            except asyncio.TimeoutError:
                log.error(f"[{vk}] timed out")
            except Exception as e:
                log.error(f"[{vk}] error: {e}")
            return None

    for coro in asyncio.as_completed([one(vk) for vk in keys]):
        r = await coro
        if r:
            results.append(r)
    return results


async def rescan_vendors(vks):
    """Re-scan a short list of vendors ONE AT A TIME with gentler pacing. Used to
    recover vendors whose first pass truncated on a 429 — sequential + slower means
    no self-competition for our IP's rate-limit budget, so they usually complete."""
    from vendors import REGISTRY
    results = []
    for vk in vks:
        try:
            scraper = REGISTRY[vk]()
            # Gentler than the vendor's default so we don't re-trip the limiter.
            scraper.REQUEST_DELAY = max(getattr(scraper, "REQUEST_DELAY", 1.0), RECOVERY_DELAY)
            res = await asyncio.wait_for(scraper.scrape(), timeout=PER_VENDOR_TIMEOUT)
            if res.listings:
                trunc = getattr(res, "truncated", False)
                log.info(f"[{vk}] re-scan: {len(res.listings)} listings"
                         + (" (still truncated)" if trunc else " (recovered)"))
                st = res.started_at.isoformat() if getattr(res, "started_at", None) else None
                fin = res.finished_at.isoformat() if getattr(res, "finished_at", None) else None
                results.append((vk, scraper.VENDOR_NAME, res.listings, st, fin, trunc))
        except asyncio.TimeoutError:
            log.error(f"[{vk}] re-scan timed out")
        except Exception as e:
            log.error(f"[{vk}] re-scan error: {e}")
    return results


def main():
    os.makedirs("logs", exist_ok=True)
    from database.db import DB_PATH
    from pipeline import run_multi_vendor_pipeline
    from scoring.watchlist import init_watchlist_tables, check_watchlist

    import crawl_lock
    if crawl_lock.is_active():
        origin = crawl_lock.status().get("origin") or "another process"
        log.warning(f"A crawl is already running ({origin}); skipping this scheduled run "
                    f"to avoid double-writing.")
        return
    crawl_lock.acquire("scheduled")
    try:
        from tools.backup_db import make_backup
        b = make_backup()
        if b:
            log.info(f"Pre-crawl backup: {b}")
    except Exception as e:
        log.warning(f"Pre-crawl backup skipped: {e}")

    t0 = time.time()
    log.info("=== Scheduled full crawl start ===")

    try:
        results = asyncio.run(crawl_all())
        log.info(f"Scraped {len(results)} vendors with listings in {time.time()-t0:.0f}s")
        _run_pipeline_and_followups(results, t0)

        # Recovery pass: any vendor that truncated (429 mid-pagination) gets one
        # gentle, sequential re-scan after a cooldown. Cheap (a few vendors) and
        # usually enough to capture the full catalog the busy first pass missed.
        truncated_vks = [r[0] for r in results if len(r) > 5 and r[5]]
        if truncated_vks:
            log.info(f"{len(truncated_vks)} vendor(s) truncated ({', '.join(truncated_vks)}); "
                     f"cooling down {RECOVERY_COOLDOWN}s then re-scanning gently")
            time.sleep(RECOVERY_COOLDOWN)
            recovered = asyncio.run(rescan_vendors(truncated_vks))
            if recovered:
                from pipeline import run_multi_vendor_pipeline
                run_multi_vendor_pipeline(recovered, db_path=DB_PATH)
                n_ok = sum(1 for r in recovered if not r[5])
                log.info(f"Recovery pass: {n_ok}/{len(truncated_vks)} vendor(s) recovered "
                         f"({len(truncated_vks) - n_ok} still truncated → snapshot keeps last good run)")
    finally:
        crawl_lock.release()
        try:
            from crawl_report import get_speed_report, format_speed_report
            log.info("\n" + format_speed_report(get_speed_report(DB_PATH)))
        except Exception as e:
            log.warning(f"Speed report skipped: {e}")


def _run_pipeline_and_followups(results, t0):
    from database.db import DB_PATH
    from pipeline import run_multi_vendor_pipeline
    from scoring.watchlist import init_watchlist_tables, check_watchlist

    # Refresh discount codes (seed known + scan sites for promos/sales)
    try:
        from vendors.discount_scraper import scan_all, seed_known_codes
        seed_known_codes(DB_PATH)
        asyncio.run(scan_all(DB_PATH))
        log.info("Discount codes refreshed")
    except Exception as e:
        log.warning(f"Discount scan skipped: {e}")

    # Shipping rates change slowly — deep-scan every 2 weeks, not every night.
    try:
        import datetime
        marker = "logs/.last_shipping_scan"
        due = True
        if os.path.exists(marker):
            last = datetime.datetime.fromtimestamp(os.path.getmtime(marker))
            due = (datetime.datetime.now() - last).days >= 14
        if due:
            from vendors.shipping_scraper import seed_known_shipping, scrape_shipping_pages
            seed_known_shipping(DB_PATH)
            asyncio.run(scrape_shipping_pages(DB_PATH))
            open(marker, "w").write(datetime.datetime.now().isoformat())
            log.info("Shipping rates deep-scanned (biweekly)")
        else:
            log.info("Shipping scan skipped (scanned within 14 days)")
    except Exception as e:
        log.warning(f"Shipping scan skipped: {e}")

    if results:
        run_multi_vendor_pipeline(results, db_path=DB_PATH)
        log.info("Pipeline complete (saved + workbook rebuilt)")

    # Watchlist check (for the morning digest)
    try:
        from database.db import get_connection
        conn = get_connection(DB_PATH)
        cur = conn.execute("""SELECT vendor_key, MAX(id) mx FROM crawl_runs
                              WHERE status IN ('complete','partial') GROUP BY vendor_key""")
        runs = [r["mx"] for r in cur.fetchall()]
        ph = ",".join("?" * len(runs))
        snap = [dict(r) for r in conn.execute(
            f"SELECT * FROM price_history WHERE crawl_run_id IN ({ph}) "
            f"AND availability!='out_of_stock'", runs).fetchall()]
        conn.close()
        init_watchlist_tables(DB_PATH)
        hits = check_watchlist(snap, DB_PATH)
        log.info(f"Watchlist: {len(hits)} hits this crawl")

        # Alerts: price drops / back-in-stock / fire / saved searches.
        # Needs the fully-annotated snapshot, so build it via the app helper.
        try:
            import json as _json
            from pathlib import Path as _Path
            import app as _app
            annotated = _app.get_snapshot(force=True)
            settings = {}
            sp = _Path("tracker_settings.json")
            if sp.exists():
                settings = _json.loads(sp.read_text())
            from analytics.alerts import evaluate_and_record
            new_alerts = evaluate_and_record(annotated, DB_PATH, settings)
            log.info(f"Alerts: {len(new_alerts)} new this crawl")
        except Exception as e:
            log.warning(f"Alert evaluation skipped: {e}")
    except Exception as e:
        log.warning(f"Watchlist check skipped: {e}")

    # Build + persist the dashboard/species caches so the (read-only) web can load
    # them without ever doing the heavy build on a request. This is what keeps the
    # hosted web instance from restart-looping under real traffic.
    try:
        import app as _app
        _app.warm_and_persist()
        log.info("Dashboard caches built + persisted for the web")
    except Exception as e:
        log.warning(f"warm_and_persist skipped: {e}")

    log.info(f"=== Scheduled full crawl done in {(time.time()-t0)/60:.1f} min ===")


if __name__ == "__main__":
    main()
