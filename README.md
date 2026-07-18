# Tarantula Market Tracker

A reusable pricing crawler and market tracker for U.S. tarantula vendors.
Crawls vendor product pages, normalizes listings, scores deals vs. market, and exports a master Excel workbook.

## Requirements

Python 3.11+

```bash
pip install -r requirements.txt
playwright install chromium    # needed for JS-rendered vendor sites
```

## Quick Start

```bash
# Crawl a single vendor
python main.py --vendor jamies

# Crawl multiple vendors
python main.py --vendor jamies,arachnoeden,fear_not

# Crawl all enabled vendors (one at a time)
python main.py --all

# List all available vendor keys
python main.py --list-vendors

# Re-export Excel from existing database (no crawl)
python main.py --export-only

# Debug mode (verbose logging)
python main.py --vendor jamies --debug
```

## Output

- `output/tarantula_market_tracker.xlsx` — Master workbook (9 sheets)
- `database/market_history.sqlite` — Full price history (append-only)
- `logs/` — Per-run crawl logs

## Workbook Sheets

| Sheet | Contents |
|-------|----------|
| All Listings | Every current listing with deal rating, prices, size, availability |
| Best Deals | Sorted by deal rating then % below market |
| Females | Confirmed female listings only |
| Unsexed & Juveniles | U/Unknown listings |
| Vendor Summary | Per-vendor stats: count, avg price, deal distribution |
| Species Summary | Per-taxon stats: lowest price, lowest female price, best vendor |
| Price History | All historical observations |
| Crawl Status | Per-vendor crawl success/failure log |
| Methodology | Deal rating definitions, normalization rules, data notes |

## Deal Ratings

| Rating | Meaning | Threshold |
|--------|---------|-----------|
| 💎💎 | Exceptional | 20%+ below market median or historical low |
| 💎 | Strong Deal | 10-20% below market median |
| 👍 | Fair Market | Within ~10% of median |
| 👎 | Above Market | 10%+ above median |

Comparisons are strictly market-based. Female vs. unsexed listings are never compared.
Size buckets prevent slings and adults from being compared against each other.

## Vendor Keys

| Key | Vendor | Platform |
|-----|--------|----------|
| `tarantulalist` | TarantulaList (aggregator) | Custom |
| `jamies` | Jamie's Tarantulas | Shopify |
| `fear_not` | Fear Not Tarantulas | Custom |
| `arachnoeden` | ArachnoEden | Custom |
| `spidershoppe` | Spider Shoppe | Custom |
| `exotics_unlimited` | Exotics Unlimited USA | Custom |
| `plumbs_exotics` | Plumb's Exotics | Shopify |
| `hardcore_arachnids` | Hardcore Arachnids | Shopify |
| `buddha_bugs` | Buddha Bugs | Custom |
| `natures_exquisite` | Nature's Exquisite Creatures | Custom |
| `tydye` | TyDye Exotics | Shopify |
| `marshall_arachnids` | Marshall Arachnids | Shopify |
| `micro_wilderness` | Micro Wilderness | Custom |
| `fanghub` | FangHub | Shopify |
| `wonderland_exotics` | Wonderland Exotics | Shopify |
| `big_zs` | Big Z's | Custom |
| `pacific_northwest` | Pacific Northwest Arachnids | Custom |
| `ghostys` | Ghosty's Tarantulas | Shopify |
| `eight_deadly_sins` | Eight Deadly Sins | Shopify |
| `swifts_inverts` | Swift's Inverts | Shopify |
| `fangztv` | FangzTV | Custom |
| `spider_room` | The Spider Room | Custom |

## Adding a New Vendor

**Shopify vendor** (recommended, most reliable):
```python
# vendors/new_vendor.py
from vendors.shopify_base import ShopifyScraper
class NewVendorScraper(ShopifyScraper):
    VENDOR_KEY = "new_vendor"
    VENDOR_NAME = "New Vendor Name"
    BASE_URL = "https://newvendor.com"
```

**Custom HTML vendor**:
```python
from vendors.generic_custom import GenericCustomScraper
class NewVendorScraper(GenericCustomScraper):
    VENDOR_KEY = "new_vendor"
    VENDOR_NAME = "New Vendor Name"
    BASE_URL = "https://newvendor.com"
    SHOP_PATHS = ["/shop/", "/tarantulas/"]
```

Then add the import to `get_vendor_registry()` in `main.py` and add the entry to `config.yaml`.

## Troubleshooting

**"No products found" on a Shopify vendor**: Try visiting `https://vendor.com/products.json` in a browser to verify the Shopify API is public.

**"Could not find shop page" on a custom vendor**: The site structure may have changed. Inspect the vendor's URL manually and update `SHOP_PATHS` in the vendor file.

**Slow crawls**: Increase `REQUEST_DELAY` in the vendor class or `config.yaml`. The default 2-second delay is respectful; don't lower it.

**JavaScript-rendered pages**: If a custom vendor returns empty data, it likely requires JS. Inherit from `BaseScraper` and use Playwright's `browser.new_page()` for that vendor.

## Architecture

```
tarantula_market_tracker/
├── main.py              # CLI + orchestration
├── models.py            # Listing + CrawlResult dataclasses
├── config.yaml          # Vendor URLs + settings
├── database/db.py       # SQLite schema + queries
├── vendors/
│   ├── base.py          # Abstract BaseScraper (HTTP + retry)
│   ├── shopify_base.py  # Shopify /products.json implementation
│   ├── generic_custom.py# Generic HTML scraper template
│   └── [vendor].py      # One file per vendor
├── normalize/
│   ├── species.py       # Scientific name normalization + synonyms
│   ├── size.py          # Size parsing (all formats -> min/max/midpoint)
│   ├── sex.py           # Sex normalization -> F/PF/M/MM/U/Unknown
│   └── price.py         # Price parsing + bulk pricing
├── scoring/deals.py     # Deal rating engine (💎💎/💎/👍/👎)
└── export/excel.py      # Full 9-sheet Excel workbook
```
