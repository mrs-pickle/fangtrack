"""
Facts a seller states about a listing — sex, source (CB/WC), and whether the
animal can actually be shipped. Each test here is a bug a beta tester hit:
"wrong CB/WC statuses, sex missing when it's listed on the vendor's website",
and one animal appearing twice.
"""
from normalize.source_type import detect_source_type, detect_source_type_in_prose
from normalize.sex import sex_from_title, annotate_missing_sex
from normalize.livestock import is_pickup_only


# ── Source: a labelled spec field states the answer AFTER the label ──────────
# Regression: "CB/WC: WC" was read as CB, because the LABEL contains "CB" and
# the both-mentioned tie-break trusts CB — reporting wild-caught animals as
# captive-bred. Silent and wrong, which is the worst kind of data bug.
def test_labelled_spec_field_reads_the_value_not_the_label():
    assert detect_source_type('CB/WC: WC Adult Leg Span: 8"-12"') == "WC"
    assert detect_source_type('CB/WC: CB Adult Leg Span: 6"-7"') == "CB"
    assert detect_source_type("CB/WC: LTC established adult") == "LTC"
    assert detect_source_type("Source = WC") == "WC"


def test_unlabelled_source_detection_still_works():
    assert detect_source_type("these individuals are field-collected") == "WC"
    assert detect_source_type("captive bred here at the shop") == "CB"
    assert detect_source_type('Brachypelma hamorii 2"') == "unknown"


# ── Source in prose: only unambiguous signals, never marketing filler ────────
def test_prose_ignores_weak_incidental_words():
    # "breeder"/"F2"/bare "cb" turn up in copy that states nothing about THIS
    # animal — inventing a source from them is worse than an honest unknown.
    assert detect_source_type_in_prose("a favourite among breeders worldwide") == "unknown"
    assert detect_source_type_in_prose("one of the F2 generation lines out there") == "unknown"
    assert detect_source_type_in_prose("captive bred by us") == "CB"
    assert detect_source_type_in_prose("") == "unknown"


def test_prose_that_says_both_stays_unknown():
    assert detect_source_type_in_prose("we sell captive bred and wild caught stock") == "unknown"


# ── Sex stated in the TITLE (scrapers only read the variant) ─────────────────
def test_sex_recovered_from_title():
    assert sex_from_title("Aphonopelma chalchodes - Male - Arizona Blonde")[0] == "M"
    assert sex_from_title("Aphonopelma anax- Female")[0] == "F"
    assert sex_from_title("Aphonopelma anax - Unsexed- Texas giant tan")[0] == "U"
    assert sex_from_title("Grammostola pulchra Mature Male")[0] == "MM"


def test_sex_from_title_refuses_to_guess():
    # "male" must not match inside "female"; a pair is not one sexed animal;
    # a plain species title states nothing.
    assert sex_from_title('Caribena versicolor (Martinique Pink Toe) 0.5"')[0] == "Unknown"
    assert sex_from_title('Androctonus finitimus 1.5-2" PAIR M+F')[0] == "Unknown"
    assert sex_from_title("males and females available")[0] == "Unknown"
    assert sex_from_title("")[0] == "Unknown"


def test_annotate_missing_sex_is_fill_only():
    listings = [
        {"sex": "Unknown", "raw_title": "Aphonopelma anax- Female"},
        {"sex": "M", "raw_title": "Something - Female"},   # already known: keep it
        {"sex": "Unknown", "raw_title": 'Poecilotheria metallica 2"'},
    ]
    assert annotate_missing_sex(listings) == 1
    assert listings[0]["sex"] == "F"
    assert listings[0]["sex_display"] == "Female"
    assert listings[1]["sex"] == "M"          # variant-level fact wins
    assert listings[2]["sex"] == "Unknown"    # nothing stated -> stays honest


# ── Local-pickup duplicates ─────────────────────────────────────────────────
# Vendors list a pickup-only copy beside the shippable one, so a single animal
# showed up as two listings and inflated in-stock counts.
def test_pickup_only_listings_are_identified():
    assert is_pickup_only("[Vancouver Pick-up] Caribena versicolor")
    assert is_pickup_only("Brachypelma hamorii - local pickup only")
    assert is_pickup_only("Expo only - Grammostola pulchra")
    assert is_pickup_only("Avicularia avicularia (no shipping)")


def test_real_listings_are_not_mistaken_for_pickup():
    assert not is_pickup_only("Caribena versicolor (Martinique Pink Toe)")
    assert not is_pickup_only('Aphonopelma moderatum 2-3" Female')
    assert not is_pickup_only("")
