"""
Crawl write-guard: a scan that suddenly collapses for a vendor must NOT dump that
vendor's data from the site. Instead the run is rejected and the last good data is
kept — until a genuinely low count is confirmed on a second crawl.

Run:  python tests/test_write_guard.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("DATABASE_URL", None)
os.environ["FANGTRACK_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "guard_test.sqlite")

from pathlib import Path
import pipeline
from database.db import get_all_active_listings, get_connection, DB_PATH

_XLSX = Path(tempfile.mkdtemp()) / "out.xlsx"

SPECIES = [
    "Grammostola pulchra", "Brachypelma hamorii", "Aphonopelma chalcodes",
    "Caribena versicolor", "Tliltocatl albopilosus", "Chromatopelma cyaneopubescens",
    "Psalmopoeus irminia", "Poecilotheria metallica", "Lasiodora parahybana",
    "Acanthoscurria geniculata", "Pterinochilus murinus", "Grammostola rosea",
    "Avicularia avicularia", "Theraphosa blondi", "Nhandu chromatus",
    "Ephebopus cyanognathus", "Cyriocosmus elegans", "Hapalopus formosus",
    "Monocentropus balfouri", "Phormictopus cancerides", "Xenesthis immanis",
    "Brachypelma auratum",
]


def _listings(vk, n):
    out = []
    for i in range(n):
        sp = SPECIES[i % len(SPECIES)]
        out.append({"vendor_key": vk, "vendor": vk.title(),
                    "scientific_name": sp, "raw_title": sp, "common_name": "",
                    "price_usd": 50 + i, "availability": "in_stock", "sex": "unsexed",
                    "size_text": "2\"", "product_url": f"https://x.test/{vk}/{sp}/{i}"})
    return out


def _run(vk, n, truncated=False):
    row = (vk, vk.title(), _listings(vk, n), None, None, truncated)
    pipeline.run_multi_vendor_pipeline([row], DB_PATH, _XLSX)


def _snap_count(vk):
    return sum(1 for r in get_all_active_listings(DB_PATH) if r.get("vendor_key") == vk)


def _last_status(vk):
    conn = get_connection(DB_PATH)
    r = conn.execute("SELECT status FROM crawl_runs WHERE vendor_key=? ORDER BY id DESC LIMIT 1",
                     (vk,)).fetchone()
    conn.close()
    return r["status"] if r else None


def test_guard_keeps_last_good_then_accepts_confirmed_low():
    # Baseline healthy run.
    _run("acme", 20)
    assert _snap_count("acme") == 20, "baseline should store all 20"
    assert _last_status("acme") == "complete"

    # Scanner "breaks" → returns 2. Guard rejects; site keeps the 20.
    _run("acme", 2)
    assert _last_status("acme") == "rejected", "sharp collapse must be rejected"
    assert _snap_count("acme") == 20, "snapshot must KEEP last good data, not drop to 2"

    # Low count confirmed on the next crawl → accepted (never gets stuck).
    _run("acme", 2)
    assert _last_status("acme") == "complete", "confirmed low must be accepted"
    assert _snap_count("acme") == 2, "snapshot now reflects the real 2"


def test_new_vendor_no_baseline_is_never_guarded():
    _run("fresh", 3)
    assert _last_status("fresh") == "complete"
    assert _snap_count("fresh") == 3


def test_truncated_run_is_not_guard_rejected():
    _run("trunc", 30)
    _run("trunc", 4, truncated=True)   # truncation has its own handling
    assert _last_status("trunc") == "partial", "truncated stays partial, not rejected"


def test_normal_churn_passes_through():
    _run("churn", 20)
    _run("churn", 14)   # 30% drop — real inventory churn, must NOT be guarded
    assert _last_status("churn") == "complete"
    assert _snap_count("churn") == 14


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    passed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  ok   {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {name}: {e}")
        except Exception as e:
            print(f"  ERR  {name}: {e!r}")
    print(f"{passed}/{len(fns)} passed")
    sys.exit(0 if passed == len(fns) else 1)
