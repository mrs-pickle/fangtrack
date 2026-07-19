"""
Size parsing — shared by every crawler (normalize/size.py). Locks in the
mixed-number fix ("3 1/2\"" must be 3.5, not the "1/2" the old regex grabbed) and
guards the cases that already worked so a future tweak can't regress them.

Run:  python tests/test_size.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from normalize.size import extract_size_from_title as ex, parse_size as ps


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
