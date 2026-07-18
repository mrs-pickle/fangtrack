"""
Tarantula Market Tracker - Main Entry Point

Usage:
  python main.py --vendor jamies
  python main.py --vendor all
  python main.py --all
  python main.py --vendor tarantulalist,jamies,arachnoeden
  python main.py --list-vendors
  python main.py --export-only
"""
import asyncio
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import yaml
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from models import CrawlResult, Listing
from database.db import init_db, upsert_vendor, insert_crawl_run, save_listings, get_historical_low, get_previous_price, get_all_active_listings
from scoring.deals import score_all_listings
from export.excel import export_workbook

# On Windows the default console codec is cp1252, which cannot encode the ″/″
# prime marks and deal emoji that appear in listing/size text — rich's table
# printer then raises UnicodeEncodeError at the very end of a run. Force UTF-8
# (replace on the rare unmappable glyph) so a full crawl never crashes on output.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

console = Console()

# ---------------------------------------------------------------------------
# Vendor registry
# ---------------------------------------------------------------------------
def get_vendor_registry() -> dict:
    """
    Returns a mapping of vendor_key -> scraper class.
    Imports each vendor independently; broken or unfinished vendor
    modules are skipped with a warning instead of crashing the CLI.
    """
    specs = [
        ("jamies",             "vendors.jamies",             "JamiesTarantulasScraper"),
        ("fear_not",           "vendors.fear_not",           "FearNotTarantulasScraper"),
        ("arachnoeden",        "vendors.arachnoeden",        "ArachnoEdenScraper"),
        ("spidershoppe",       "vendors.spidershoppe",       "SpiderShoppeScraper"),
        ("exotics_unlimited",  "vendors.exotics_unlimited",  "ExoticsUnlimitedScraper"),
        ("plumbs_exotics",     "vendors.plumbs_exotics",     "PlumbsExoticsScraper"),
        ("hardcore_arachnids", "vendors.hardcore_arachnids", "HardcoreArachnidsScraper"),
        ("buddha_bugs",        "vendors.buddha_bugs",        "BuddhaBugsScraper"),
        ("natures_exquisite",  "vendors.natures_exquisite",  "NaturesExquisiteScraper"),
        ("tydye",              "vendors.tydye",              "TyDyeExoticsScraper"),
        ("marshall_arachnids", "vendors.marshall_arachnids", "MarshallArachnidsScraper"),
        ("micro_wilderness",   "vendors.micro_wilderness",   "MicroWildernessScraper"),
        ("fanghub",            "vendors.fanghub",            "FangHubScraper"),
        ("wonderland_exotics", "vendors.wonderland_exotics", "WonderlandExoticsScraper"),
        ("big_zs",             "vendors.big_zs",             "BigZsScraper"),
        ("pacific_northwest",  "vendors.pacific_northwest",  "PacificNorthwestScraper"),
        ("ghostys",            "vendors.ghostys",            "GhostysTarantulasScraper"),
        ("eight_deadly_sins",  "vendors.eight_deadly_sins",  "EightDeadlySinsScraper"),
        ("fangztv",            "vendors.fangztv",            "FangzTVScraper"),
        ("spider_room",        "vendors.spider_room",        "TheSpiderRoomScraper"),
        ("urban_tarantulas",   "vendors.urban_tarantulas",   "UrbanTarantulasScraper"),
        ("juices_arthropods",  "vendors.juices_arthropods",  "JuicesArthropodsScraper"),
        ("arachnid_rarities",  "vendors.arachnid_rarities",  "ArachnidRaritiesScraper"),
        ("joshsfrogs",         "vendors.joshsfrogs",         "JoshsFrogsScraper"),
        ("eight_paws",         "vendors.eight_paws",         "EightPawsScraper"),
        ("vexotic",            "vendors.vexotic",            "VExoticScraper"),
        ("feared_fascinated",  "vendors.feared_fascinated",  "FearedToFascinatedScraper"),
        ("great_basin",        "vendors.great_basin",        "GreatBasinScraper"),
        ("underground_reptiles","vendors.underground_reptiles","UndergroundReptilesScraper"),
        # v2 additions
    ]
    import importlib
    registry = {}
    for key, module_path, class_name in specs:
        try:
            mod = importlib.import_module(module_path)
            registry[key] = getattr(mod, class_name)
        except Exception as e:
            console.print(f"[yellow]Skipping vendor '{key}': {e}[/yellow]")
    return registry


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Tarantula Market Tracker -- crawl vendor sites and track prices"
    )
    parser.add_argument(
        "--vendor", "-v",
        help='Vendor key(s) to crawl. Use "all" or comma-separated keys. '
             'Example: --vendor jamies or --vendor jamies,arachnoeden',
        default=None,
    )
    parser.add_argument("--all", "-a", action="store_true", help="Crawl all enabled vendors")
    parser.add_argument("--list-vendors", action="store_true", help="List available vendor keys and exit")
    parser.add_argument("--export-only", action="store_true",
                        help="Skip crawling; just re-export Excel from existing DB data")
    parser.add_argument("--output", "-o", default="output/tarantula_market_tracker.xlsx",
                        help="Output Excel file path")
    parser.add_argument("--db", default="database/market_history.sqlite",
                        help="SQLite database path")
    parser.add_argument("--no-excel", action="store_true", help="Skip Excel export")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Core crawl orchestration
# ---------------------------------------------------------------------------
async def run_crawl(vendor_keys: list[str], config: dict, db_path: Path) -> tuple[list[CrawlResult], list[Listing]]:
    """Run crawls for specified vendors, one at a time."""
    registry = get_vendor_registry()
    vendor_config = config.get("vendors", {})

    all_results: list[CrawlResult] = []
    all_listings: list[Listing] = []

    for key in vendor_keys:
        if key not in registry:
            console.print(f"[yellow]Unknown vendor key: {key}[/yellow]")
            continue

        vc = vendor_config.get(key, {})
        if not vc.get("enabled", True):
            console.print(f"[dim]Skipping disabled vendor: {key}[/dim]")
            continue

        scraper_class = registry[key]
        scraper = scraper_class(config=vc)

        console.rule(f"[bold blue]Crawling: {scraper.VENDOR_NAME}[/bold blue]")
        console.print(f"  URL: {scraper.BASE_URL}")
        console.print(f"  Platform: {scraper.PLATFORM}")

        try:
            result = await scraper.scrape()
        except Exception as e:
            console.print(f"[red]FATAL ERROR crawling {key}: {e}[/red]")
            result = CrawlResult(
                vendor_key=key,
                vendor_name=scraper.VENDOR_NAME,
                status="failed",
                notes=str(e),
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
            )

        # Enrich listings: historical lows, previous prices, change flags
        for listing in result.listings:
            hist = get_historical_low(
                listing.scientific_name_key or "",
                listing.sex,
                db_path
            )
            if hist:
                listing.historical_low = hist
                if listing.price_usd <= hist:
                    listing.is_new_historical_low = True

            prev = get_previous_price(
                listing.vendor_key,
                listing.scientific_name_key or "",
                listing.sex,
                listing.size_text,
                db_path
            )
            if prev is None:
                listing.is_new = True
            elif prev != listing.price_usd:
                listing.is_price_drop = listing.price_usd < prev
                listing.is_price_increase = listing.price_usd > prev
                listing.previous_price = prev

        # Save to DB
        run_id = insert_crawl_run(result, db_path)
        save_listings(result.listings, run_id, db_path)

        all_results.append(result)
        all_listings.extend(result.listings)

        # Print summary
        _print_crawl_summary(result)

    # Post-crawl clean-up passes: canonicalize keys and purge non-livestock, so
    # the DB is always spotless without a manual step.
    finalize_crawl(db_path)

    return all_results, all_listings


def finalize_crawl(db_path: Path) -> None:
    """Standing clean-up run after every crawl (like name standardization):
    1. collapse misspelled / truncated species keys onto their canonical form,
    2. purge any non-livestock rows (enclosures, substrate, decor, merch).
    Both reuse the same modules the crawler filters with, so behaviour never
    diverges. Safe/idempotent."""
    try:
        from tools.migrate_key_aliases import migrate
        migrate(dry=False)
    except Exception as e:
        console.print(f"[yellow]key-alias pass skipped: {e}[/yellow]")
    try:
        from tools.purge_nonlivestock import purge_db
        n = purge_db(db_path, dry=False, verbose=False)
        if n:
            console.print(f"[dim]Purged {n} non-livestock rows.[/dim]")
    except Exception as e:
        console.print(f"[yellow]livestock purge skipped: {e}[/yellow]")


# ---------------------------------------------------------------------------
# Output and display
# ---------------------------------------------------------------------------
def _print_crawl_summary(result: CrawlResult):
    status_color = {"complete": "green", "partial": "yellow", "failed": "red"}.get(result.status, "white")
    console.print(f"\n  Status: [{status_color}]{result.status.upper()}[/{status_color}]")
    console.print(f"  Pages crawled: {result.pages_crawled}")
    console.print(f"  Products found: {result.products_found}")
    console.print(f"  Variants found: {result.variants_found}")
    if result.failures:
        console.print(f"  [yellow]Failures: {len(result.failures)}[/yellow]")
        for f in result.failures[:5]:
            console.print(f"    [dim]{f}[/dim]")
    if result.duration_seconds():
        console.print(f"  Duration: {result.duration_seconds():.1f}s")


def print_listings_table(listings: list[Listing]):
    """Print a rich table of listings sorted by deal rating."""
    from models import DealRating
    SORT = {DealRating.EXCEPTIONAL: 0, DealRating.STRONG: 1,
            DealRating.FAIR: 2, DealRating.ABOVE_MARKET: 3, None: 4}

    available = [l for l in listings if l.availability != "out_of_stock"]
    sorted_l = sorted(available, key=lambda l: (SORT.get(l.deal_rating, 4), l.price_usd))

    table = Table(title="Tarantula Market Results", show_header=True, header_style="bold blue")
    table.add_column("Deal", width=5)
    table.add_column("Scientific Name", width=30)
    table.add_column("Common Name", width=20)
    table.add_column("Vendor", width=22)
    table.add_column("Sex", width=12)
    table.add_column("Size", width=8)
    table.add_column("Price", width=9)

    for l in sorted_l[:50]:  # Cap at 50 for terminal display
        table.add_row(
            l.deal_rating or "--",
            l.scientific_name[:28] if l.scientific_name else "",
            (l.common_name or "")[:18],
            l.vendor[:20],
            l.sex_display,
            l.size_text or "--",
            f"${l.price_usd:.2f}",
        )
    console.print(table)
    if len(available) > 50:
        console.print(f"[dim]... and {len(available) - 50} more listings in the Excel workbook[/dim]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    args = parse_args()

    # Logging
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(f"logs/crawler_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.log", mode="a", encoding="utf-8"),
        ]
    )
    Path("logs").mkdir(exist_ok=True)

    # Load config
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    db_path = Path(args.db)
    output_path = Path(args.output)

    # Init database
    init_db(db_path)

    registry = get_vendor_registry()
    vendor_config = config.get("vendors", {})

    # Register all vendors in DB
    for key, vc in vendor_config.items():
        if key in registry:
            upsert_vendor(
                key,
                vc.get("name", key),
                vc.get("url", ""),
                vc.get("platform", "unknown"),
                db_path
            )

    # List vendors
    if args.list_vendors:
        table = Table(title="Available Vendors", header_style="bold blue")
        table.add_column("Key")
        table.add_column("Name")
        table.add_column("Platform")
        table.add_column("URL")
        table.add_column("Enabled")
        for key in sorted(registry.keys()):
            vc = vendor_config.get(key, {})
            table.add_row(
                key,
                vc.get("name", key),
                vc.get("platform", "?"),
                vc.get("url", ""),
                "Yes" if vc.get("enabled", True) else "No",
            )
        console.print(table)
        return

    # Export only
    if args.export_only:
        console.print("[bold]Export only mode -- loading from database...[/bold]")
        db_listings = get_all_active_listings(db_path)
        listings = _db_rows_to_listings(db_listings)
        score_all_listings(listings)
        if not args.no_excel:
            export_workbook(listings, [], output_path)
        return

    # Determine which vendors to crawl
    if args.all or (args.vendor and args.vendor.lower() == "all"):
        vendor_keys = [k for k in registry.keys() if vendor_config.get(k, {}).get("enabled", True)]
    elif args.vendor:
        vendor_keys = [v.strip() for v in args.vendor.split(",")]
    else:
        console.print("[red]Specify --vendor KEY or --all[/red]")
        console.print("Run with --list-vendors to see available options.")
        return

    console.print(f"\n[bold green]Tarantula Market Tracker[/bold green]")
    console.print(f"Vendors to crawl: {', '.join(vendor_keys)}")
    console.print(f"Database: {db_path}")
    console.print(f"Output: {output_path}\n")

    # Cross-process crawl lock — refuse to start if the app or scheduled job is crawling,
    # so a manual CLI run can never double-write the day's data (the 2026-07-17 bug).
    import crawl_lock
    if crawl_lock.is_active():
        origin = crawl_lock.status().get("origin") or "another process"
        console.print(f"[red]A crawl is already running ({origin}). Aborting to avoid "
                      f"double-writing today's data.[/red]")
        return
    crawl_lock.acquire("cli")
    try:
        from tools.backup_db import make_backup
        b = make_backup()
        if b:
            console.print(f"[dim]Pre-crawl backup: {b}[/dim]")
    except Exception as e:
        console.print(f"[yellow]Pre-crawl backup skipped: {e}[/yellow]")

    # Run crawls
    try:
        results, listings = await run_crawl(vendor_keys, config, db_path)
    finally:
        crawl_lock.release()

    if not listings:
        console.print("[yellow]No listings collected. Check crawl failures above.[/yellow]")
        if not args.no_excel:
            export_workbook([], results, output_path)
        return

    # Score deals
    console.print(f"\n[bold]Scoring {len(listings)} listings...[/bold]")
    score_all_listings(listings)

    # Print terminal summary
    print_listings_table(listings)

    # Export Excel
    if not args.no_excel:
        console.print(f"\n[bold]Exporting to Excel: {output_path}[/bold]")
        export_workbook(listings, results, output_path)
        console.print(f"[green]Done. Open {output_path} for the full report.[/green]")

    # Final stats
    console.rule("[bold]Crawl Complete[/bold]")
    total_vendors = len(results)
    total_listings = len(listings)
    complete = sum(1 for r in results if r.status == "complete")
    failed = sum(1 for r in results if r.status == "failed")
    console.print(f"Vendors: {total_vendors} ({complete} complete, {failed} failed)")
    console.print(f"Total listings: {total_listings}")

    # Speed report — always printed after a crawl.
    try:
        from crawl_report import get_speed_report, format_speed_report
        console.print("\n" + format_speed_report(get_speed_report(db_path)))
    except Exception as e:
        console.print(f"[dim]Speed report skipped: {e}[/dim]")


def _db_rows_to_listings(rows: list[dict]) -> list[Listing]:
    """Convert DB rows back into Listing objects for re-export."""
    listings = []
    for r in rows:
        l = Listing(
            vendor=r.get("vendor_key", ""),
            vendor_key=r.get("vendor_key", ""),
            scientific_name=r.get("scientific_name", ""),
            scientific_name_key=r.get("scientific_name_key"),
            common_name=r.get("common_name"),
            sex=r.get("sex", "Unknown"),
            sex_display=r.get("sex_display", "Unknown"),
            size_text=r.get("size_text"),
            size_min_inches=r.get("size_min"),
            size_max_inches=r.get("size_max"),
            size_midpoint=r.get("size_midpoint"),
            price_usd=float(r.get("price_usd", 0)),
            regular_price_usd=r.get("regular_price_usd"),
            availability=r.get("availability", "unknown"),
            quantity=r.get("quantity"),
            product_url=r.get("product_url", ""),
            variant_name=r.get("variant_name"),
            notes=r.get("notes"),
            verification_level=r.get("verification_level", "unknown"),
        )
        listings.append(l)
    return listings


if __name__ == "__main__":
    asyncio.run(main())
