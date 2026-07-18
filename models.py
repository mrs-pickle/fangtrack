"""
Core data models for the Tarantula Market Tracker.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Sex constants
# ---------------------------------------------------------------------------
class Sex:
    FEMALE = "F"
    PROBABLE_FEMALE = "PF"
    MALE = "M"
    MATURE_MALE = "MM"
    UNSEXED = "U"
    UNKNOWN = "Unknown"


SEX_DISPLAY = {
    Sex.FEMALE: "Female",
    Sex.PROBABLE_FEMALE: "Probable Female",
    Sex.MALE: "Male",
    Sex.MATURE_MALE: "Mature Male",
    Sex.UNSEXED: "Unsexed",
    Sex.UNKNOWN: "Unknown",
}


# ---------------------------------------------------------------------------
# Availability constants
# ---------------------------------------------------------------------------
class Availability:
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PREORDER = "preorder"
    LIMITED = "limited"
    UNKNOWN = "unknown"


AVAILABILITY_DISPLAY = {
    Availability.IN_STOCK: "In Stock",
    Availability.OUT_OF_STOCK: "Out of Stock",
    Availability.PREORDER: "Preorder",
    Availability.LIMITED: "Limited",
    Availability.UNKNOWN: "Unknown",
}


# ---------------------------------------------------------------------------
# Deal rating constants
# ---------------------------------------------------------------------------
class DealRating:
    EXCEPTIONAL = "💎💎"
    STRONG = "💎"
    FAIR = "👍"
    ABOVE_MARKET = "👎"


DEAL_SORT_ORDER = {
    DealRating.EXCEPTIONAL: 0,
    DealRating.STRONG: 1,
    DealRating.FAIR: 2,
    DealRating.ABOVE_MARKET: 3,
    None: 4,
}


# ---------------------------------------------------------------------------
# Verification levels
# ---------------------------------------------------------------------------
class VerificationLevel:
    DIRECT = "direct"           # Crawled directly from vendor product page
    AGGREGATOR = "aggregator"   # Found via TarantulaList or similar aggregator
    ESTIMATED = "estimated"     # Inferred from "from $X" or similar
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Core Listing dataclass
# ---------------------------------------------------------------------------
@dataclass
class Listing:
    # --- Identity ---
    vendor: str
    vendor_key: str                              # config key, e.g. "jamies"

    # --- Species ---
    scientific_name: str                         # Exact seller text
    common_name: Optional[str] = None

    # --- Sex ---
    sex: str = Sex.UNKNOWN                       # Normalized code: F, PF, M, MM, U, Unknown
    sex_display: str = "Unknown"

    # --- Size ---
    size_text: Optional[str] = None              # Exact seller text
    size_min_inches: Optional[float] = None
    size_max_inches: Optional[float] = None
    size_midpoint: Optional[float] = None        # (min+max)/2 or just min if no max

    # --- Pricing ---
    price_usd: float = 0.0                       # Current selling price
    regular_price_usd: Optional[float] = None    # Pre-sale / regular price
    sale_price_usd: Optional[float] = None       # Explicit sale price if seller marks it

    # Bulk pricing
    bulk_quantity: Optional[int] = None
    bulk_package_price: Optional[float] = None
    bulk_per_animal_price: Optional[float] = None

    # --- Availability ---
    availability: str = Availability.UNKNOWN
    quantity: Optional[int] = None

    # --- URLs ---
    product_url: str = ""
    image_url: Optional[str] = None

    # --- Variant ---
    variant_name: Optional[str] = None          # e.g. "1\" Female"

    # --- Metadata ---
    notes: Optional[str] = None
    date_checked: datetime = field(default_factory=datetime.utcnow)
    verification_level: str = VerificationLevel.UNKNOWN

    # Raw text from vendor page (for auditing)
    raw_title: Optional[str] = None
    raw_variant: Optional[str] = None
    raw_price: Optional[str] = None
    # Cleaned+truncated product description captured at crawl time — feeds source
    # (CB/WC) and size detection, which were previously blind to it.
    description: Optional[str] = None

    # --- Computed fields (filled after crawl by scoring module) ---
    scientific_name_key: Optional[str] = None   # Normalized comparison key
    deal_rating: Optional[str] = None
    deal_reason: Optional[str] = None
    current_lowest_price: Optional[float] = None
    market_average: Optional[float] = None
    historical_low: Optional[float] = None
    price_per_inch: Optional[float] = None

    # --- Change flags (set by DB comparison) ---
    is_new: bool = False
    is_price_drop: bool = False
    is_new_historical_low: bool = False
    is_returned_to_stock: bool = False
    is_sold_out: bool = False
    is_price_increase: bool = False
    previous_price: Optional[float] = None

    def discount_pct(self) -> Optional[float]:
        """Percentage discount vs regular price, if known."""
        if self.regular_price_usd and self.regular_price_usd > 0:
            return (self.regular_price_usd - self.price_usd) / self.regular_price_usd * 100
        return None

    def effective_price(self) -> float:
        """Best current price for comparison purposes."""
        return self.price_usd

    def sex_group(self) -> str:
        """Group for deal comparison: confirmed vs unconfirmed."""
        if self.sex == Sex.FEMALE:
            return "female"
        if self.sex == Sex.PROBABLE_FEMALE:
            return "probable_female"
        if self.sex in (Sex.MALE, Sex.MATURE_MALE):
            return "male"
        return "unsexed"

    def __repr__(self) -> str:
        return (
            f"Listing({self.vendor!r}, {self.scientific_name!r}, "
            f"sex={self.sex}, size={self.size_text!r}, price=${self.price_usd:.2f})"
        )


@dataclass
class CrawlResult:
    """Result object returned by each vendor crawler."""
    vendor_key: str
    vendor_name: str
    listings: list[Listing] = field(default_factory=list)
    pages_crawled: int = 0
    products_found: int = 0
    variants_found: int = 0
    failures: list[str] = field(default_factory=list)
    status: str = "pending"   # pending, running, complete, failed, partial
    truncated: bool = False    # pagination cut short by a fetch failure (429/timeout)
                               # → the run under-counts, so the snapshot skips it
                               # in favour of the vendor's last good run.
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    notes: Optional[str] = None

    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None
