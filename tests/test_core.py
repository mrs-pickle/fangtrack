"""
Core behaviour tests — livestock filter, species canonicalization, deal scorer.
Run:  python -m pytest tests/ -q     (or: python tests/test_core.py)
These lock in the rules that went through many iterations so they don't regress.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from normalize.livestock import is_livestock
from normalize.species_canonical import canonical_species
from scoring.deals import _size_bucket, _comparison_key
from normalize.genus_meta import origin, care_level, price_band
from analytics.market import _trimmed_median, _TIER_BANDS


def test_livestock_keeps_animals():
    for name in ["Theraphosa blondi", "Grammostola pulchra sling",
                 "Female Pamphobeteus sp. 'Mascara'", "Chromatopelma cyaneopubescens- Green Bottle Blue",
                 "Centruroides sculpturatus (Bark Scorpion)", "dairy cow isopods",
                 "Scarlet Millipede (Trigoniulus coralinus)"]:
        assert is_livestock(name), name


def test_livestock_drops_supplies():
    for name in ["Frozen Rodents", "Fine Fir Bark", "Plastic Vial with Snap Lid",
                 "arboreal sling kits", "disposable tarantula water dish",
                 "Unisex aphonopelma classic tee", "Alaska shipping", "Abalone shell",
                 "Mealworms x 20 For feeding spiderlings", "Tillandsia ionantha"]:
        assert not is_livestock(name), name


def test_canonical_collapses_variants():
    keys = {canonical_species(n)[0] for n in [
        "Theraphosa blondi",
        'Theraphosa blondi - Goliath Bird Eater - 2"-2.5"',
        "Theraphosa blondi (Goliath Birdeater) about 2 1/2\"",
        "Goliath Birdeater Tarantula - Theraphosa blondi",
    ]}
    assert keys == {"theraphosa blondi"}


def test_canonical_common_name():
    k, d, c = canonical_species("Grammostola pulchra 2\"")
    assert k == "grammostola pulchra"
    assert d == "Grammostola pulchra"
    assert c == "Brazilian Black"


def test_canonical_rejects_junk():
    for junk in ["Alaska shipping", "Abalone shell", "A walk in the park", "Plant Pots"]:
        assert canonical_species(junk)[0] == "", junk


def test_size_buckets():
    assert _size_bucket(0.5) == "sling"
    assert _size_bucket(1.0) == "juvenile"
    assert _size_bucket(2.5) == "subadult"
    assert _size_bucket(4.0) == "adult"
    assert _size_bucket(6.0) == "large"
    assert _size_bucket(None) == "unknown"
    assert _size_bucket(56.5) == "unknown"   # parse-error guard


def test_comparison_key_ignores_source_type():
    a = _comparison_key({"scientific_name_key": "grammostola pulchra", "sex": "F",
                         "size_midpoint": 4.0, "source_type": "CB"})
    b = _comparison_key({"scientific_name_key": "grammostola pulchra", "sex": "F",
                         "size_midpoint": 4.0, "source_type": "WC"})
    assert a == b   # CB/WC no longer splits the comparison pool


def test_genus_meta_origin_and_care():
    assert origin("poecilotheria") == "Old World"
    assert origin("grammostola") == "New World"
    assert origin("nonsensegenus") == ""
    assert care_level("poecilotheria") == "Advanced"   # Old World → advanced
    assert care_level("grammostola") == "Beginner"
    assert care_level("psalmopoeus") == "Advanced"     # fast NW arboreal
    assert care_level("someunknown") == "Intermediate"


def test_price_bands():
    assert price_band(10) == "Under $25"
    assert price_band(40) == "$25–50"
    assert price_band(80) == "$50–100"
    assert price_band(500) == "$250+"
    assert price_band(None) == ""


def test_trimmed_median_drops_outliers():
    # one lowball + one gouger should not swing the market price
    assert _trimmed_median([10, 48, 50, 52, 500]) == 50
    # small samples fall back to plain median
    assert _trimmed_median([40, 60]) == 50
    assert _trimmed_median([]) == 0.0


def test_tier_bands_form_pyramid():
    # cumulative thresholds strictly increase and top tier is the smallest slice
    ths = [b[0] for b in _TIER_BANDS]
    assert ths == sorted(ths)
    assert _TIER_BANDS[0][1] == "Mythic" and _TIER_BANDS[0][0] <= 0.10
    assert _TIER_BANDS[-1][1] == "Ubiquitous"


def test_rarity_tiers_are_one_source_of_truth():
    """Locks in the Option-B rarity ladder and the collision that caused it.

    Rare and Legendary once shared #7c3aed because tier colours were duplicated
    across templates; violet-600 now belongs exclusively to the Exceptional
    deal badge. These asserts make that regression impossible.
    """
    from theme import RARITY_TIERS, DEAL_BADGES, TIER_ORDER, RANGE_BAR_GRADIENT

    # (a) exactly six tiers
    assert len(RARITY_TIERS) == 6, f"expected 6 tiers, got {len(RARITY_TIERS)}"

    # (b) every background is distinct
    bgs = [t["bg"] for t in RARITY_TIERS.values()]
    assert len(set(bgs)) == 6, f"rarity backgrounds collide: {bgs}"

    # (c) NO rarity background may equal ANY deal-badge background. The two
    # systems are read in different columns and must never share a colour. This
    # is now a hard zero — the three historical overlaps (Uncommon/Strong,
    # Common/Fair, Ubiquitous/Above) were resolved by the TCG-ramp recolour.
    deal_bgs = {d["bg"] for d in DEAL_BADGES.values()}
    collisions = {name: t["bg"] for name, t in RARITY_TIERS.items()
                  if t["bg"] in deal_bgs}
    assert not collisions, f"rarity bg collides with a deal badge: {collisions}"

    # The regression that started all this: violet-600 belongs EXCLUSIVELY to the
    # Exceptional deal badge and must never be a rarity colour again.
    assert "#7c3aed" not in bgs, "violet-600 leaked back into the rarity ladder"
    assert DEAL_BADGES["exceptional"]["bg"] == "#7c3aed"

    # (d) the specific final (TCG-ramp) values
    assert RARITY_TIERS["Ubiquitous"]["bg"] == "#475569"   # slate-600
    assert RARITY_TIERS["Common"]["bg"] == "#15803d"       # green-700
    assert RARITY_TIERS["Uncommon"]["bg"] == "#0369a1"     # sky-700
    assert RARITY_TIERS["Rare"]["bg"] == "#4338ca"         # indigo-700
    assert RARITY_TIERS["Legendary"]["bg"] == "#a21caf"    # fuchsia-700
    assert RARITY_TIERS["Mythic"]["bg"] == "#c2410c"       # orange-700

    # ladder order + range bar carries the green/sky/fuchsia stops
    assert TIER_ORDER[0] == "Mythic" and TIER_ORDER[-1] == "Ubiquitous"
    for stop in ("#15803d", "#0369a1", "#a21caf"):
        assert stop in RANGE_BAR_GRADIENT, f"{stop} missing from range bar"
    assert "#7c3aed" not in RANGE_BAR_GRADIENT


def test_rarity_colors_not_duplicated_outside_theme():
    """No rarity hex may be hard-coded anywhere but theme.py."""
    import os, re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    from theme import RARITY_TIERS
    # hexes unique to rarity (exclude ones shared with the deal-badge system)
    shared = {"#374151", "#065f46", "#1d4ed8"}   # also deal-badge backgrounds
    rarity_only = {t["bg"] for t in RARITY_TIERS.values()} - shared
    offenders = []
    for sub in ("templates", "analytics", "scoring", "normalize"):
        d = os.path.join(root, sub)
        for dirpath, _, files in os.walk(d):
            for f in files:
                if not f.endswith((".html", ".py")):
                    continue
                p = os.path.join(dirpath, f)
                with open(p, encoding="utf-8", errors="replace") as fh:
                    txt = fh.read()
                for hx in rarity_only:
                    if hx.lower() in txt.lower():
                        offenders.append(f"{os.path.relpath(p, root)} -> {hx}")
    assert not offenders, "rarity hex hard-coded outside theme.py: " + "; ".join(offenders)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn(); passed += 1; print(f"  ok   {fn.__name__}")
        except AssertionError as e:
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:
            print(f"  ERR  {fn.__name__}: {e}")
    print(f"{passed}/{len(fns)} passed")
