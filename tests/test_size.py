"""
Size parsing — shared by every crawler (normalize/size.py). Locks in the
mixed-number fix ("3 1/2\"" must be 3.5, not the "1/2" the old regex grabbed) and
guards the cases that already worked so a future tweak can't regress them.

Run:  python tests/test_size.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from normalize.size import (extract_size_from_title as ex, parse_size as ps,
                            extract_size_from_description as edesc)


def test_mixed_number_in_title():
    # The bug Mike caught: "3 1/2\"" was read as 1/2".
    assert ex('Caribena versicolor (Martinique Pink Toe) 3 1/2" FEMALE') == '3.5"'
    assert ps('3 1/2"') == (3.5, 3.5, 3.5)
    assert ex('Grammostola 2 3/4"') == '2.75"'


def test_mixed_number_range_in_title():
    # Fear Not: "1 - 1 1/2\"" was read as 1/2".
    assert ex('Fear Not sling 1 - 1 1/2"') == '1.0-1.5"'
    assert ps('1.0-1.5"') == (1.0, 1.5, 1.25)


def test_existing_cases_unregressed():
    assert ex('Grammostola 0.5"') == '0.5"'          # decimal
    assert ex('Poec metallica 1/2"') == '1/2"'        # bare fraction
    assert ps('1/2"') == (0.5, 0.5, 0.5)
    assert ex('EarthTiger (3 – 4″)') == '3.0-4.0"'    # plain range, unicode inch
    assert ex('Blue Fang 3/4-1"') == '0.75-1.0"'      # fraction range endpoint
    assert ex('Darth Maul (.5 – .75”)') == '0.5-0.75"'  # leading-dot decimals


def test_non_sizes_ignored():
    # A stray number in a name must NOT be read as a size (needs a unit).
    assert ex("Pamphobeteus sp 2") is None
    assert ps("adult") == (None, None, None)


def test_description_never_grabs_adult_grow_size():
    # The bug Mike caught: Great Basin's $8 T. vagans sling showed size 5-6",
    # mined from "grow to be a moderate size of about 5-6 inches" (the ADULT
    # grow-size). With no per-specimen size in the body, the honest answer is
    # None (Unknown), not the species' adult leg span.
    assert edesc("Tliltocatl vagans grow to be a moderate size of about 5-6 inches.") is None
    assert edesc('CB/WC: CB Adult Leg Span: 5"-6" Origin: Mexico') is None
    assert edesc("They can grow up to a solid 6.5 inch leg span.") is None
    assert edesc("This species reaches 7 inches as an adult.") is None


def test_description_current_size_still_extracted():
    # A labelled current size must still win — even when a full-grown size
    # follows it inside the same capture window (take the FIRST token, not last).
    assert edesc('Current Size: Approximately 3/4" Full Grown Size: 5-6"') == '3/4"'
    assert edesc('Current Size: Approximately 3/4". Full Grown Size: 5-6".') == '3/4"'
    assert edesc("Care easy. Size: 1.5\" Diet: crickets.") == '1.5"'
    # No adult-size phrasing anywhere → a bare current-size token is safe to take.
    assert edesc("Wild caught. Field Collected Approximately 3 - 4 Inches.") == '3.0-4.0"'


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    passed = 0
    for name, fn in fns:
        try:
            fn(); print(f"  ok   {name}"); passed += 1
        except AssertionError as e:
            print(f"  FAIL {name}: {e}")
    print(f"{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
