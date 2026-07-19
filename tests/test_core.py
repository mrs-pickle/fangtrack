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
    """Locks in the 2026-07-19 rebrand ladder (Mike-approved) and the
    distinguishability rules that survived it.

    Rare and Legendary once shared #7c3aed because tier colours were duplicated
    across templates; violet-600 belongs exclusively to the Exceptional deal
    badge — the Design draft put Legendary AND Exceptional on #a855f7, and
    Exceptional keeps violet precisely so the two can never be confused.
    """
    from theme import RARITY_TIERS, DEAL_BADGES, TIER_ORDER, RANGE_BAR_GRADIENT

    # (a) exactly six tiers
    assert len(RARITY_TIERS) == 6, f"expected 6 tiers, got {len(RARITY_TIERS)}"

    # (b) every core is distinct, and the derived pill bg/border exist
    cores = [t["core"] for t in RARITY_TIERS.values()]
    assert len(set(cores)) == 6, f"rarity cores collide: {cores}"
    for t in RARITY_TIERS.values():
        assert t["bg"].startswith("rgba(") and t["border"].startswith("rgba(")

    # (c) rarity pills are TRANSLUCENT, deal chips are FILLED — no rendered
    # rarity background may equal a deal background, and the one hue the two
    # systems must never share at all is Legendary purple vs Exceptional.
    deal_bgs = {d["bg"] for d in DEAL_BADGES.values()}
    assert not any(t["bg"] in deal_bgs for t in RARITY_TIERS.values())
    assert DEAL_BADGES["exceptional"]["bg"] == "#7c3aed"
    assert "#7c3aed" not in cores, "violet-600 leaked back into the rarity ladder"
    assert RARITY_TIERS["Legendary"]["core"] != DEAL_BADGES["exceptional"]["bg"], \
        "Legendary and Exceptional must stay distinguishable"

    # (d) the specific rebrand cores — oklch(0.66 0.20 H) ladder
    assert RARITY_TIERS["Mythic"]["core"] == "#e93d82"       # H 340 pink
    assert RARITY_TIERS["Legendary"]["core"] == "#a855f7"    # H 300 purple
    assert RARITY_TIERS["Rare"]["core"] == "#3b82f6"         # H 260 blue
    assert RARITY_TIERS["Uncommon"]["core"] == "#14b8a6"     # H 200 teal
    assert RARITY_TIERS["Common"]["core"] == "#22c55e"       # H 150 green
    assert RARITY_TIERS["Ubiquitous"]["core"] == "#9ba1a6"   # neutral

    # ladder order + range bar carries the green/teal/purple stops
    assert TIER_ORDER[0] == "Mythic" and TIER_ORDER[-1] == "Ubiquitous"
    for stop in ("#22c55e", "#14b8a6", "#a855f7"):
        assert stop in RANGE_BAR_GRADIENT, f"{stop} missing from range bar"
    assert "#9ba1a6" not in RANGE_BAR_GRADIENT   # gray tier omitted from the ramp


def test_rarity_colors_not_duplicated_outside_theme():
    """No rarity-exclusive hex may be hard-coded anywhere but theme.py."""
    import os, re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    from theme import RARITY_TIERS
    # Cores unique to rarity. The rebrand shares hues across systems by design:
    # #a855f7 (accent/gem), #3b82f6 (link/Strong), #22c55e (down/Fair/CB) are
    # legitimately everywhere — only the exclusive cores are policed.
    shared = {"#a855f7", "#3b82f6", "#22c55e"}
    rarity_only = {t["core"] for t in RARITY_TIERS.values()} - shared
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
