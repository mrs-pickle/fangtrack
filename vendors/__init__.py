"""Vendor registry. Maps CLI/app slug -> vendor scraper class.

This REGISTRY is what the web app (app.py "Run All Crawls") iterates over, so
it must map to the *real* BaseScraper subclasses that implement scrape() — the
same set main.py crawls. Imports are fault tolerant: a broken/unfinished
vendor module is skipped with a warning instead of taking down the whole app.

(The legacy vendors/stubs.py engine is intentionally NOT wired in here; it
targets a different, incompatible Listing/BaseVendor API and is superseded by
the per-vendor modules below.)
"""
import importlib
import logging

logger = logging.getLogger(__name__)

# (slug, module path, class name)
_SPECS = [
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
]

REGISTRY = {}
for _slug, _mod, _cls in _SPECS:
    try:
        REGISTRY[_slug] = getattr(importlib.import_module(_mod), _cls)
    except Exception as _e:  # pragma: no cover - defensive
        logger.warning(f"Skipping vendor '{_slug}': {_e}")


def get_vendor(slug: str):
    if slug not in REGISTRY:
        raise KeyError(f"unknown vendor '{slug}'. known: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[slug]
