"""
Tests for the ops/robustness paths added for launch: crawl lock, DB backup, and the
collection spreadsheet parser.

Run:  python tests/test_ops.py
"""
import os
import sys
import time
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Isolate from the real DB before importing app.
os.environ.pop("DATABASE_URL", None)
os.environ["FANGTRACK_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "ops_test.sqlite")

import crawl_lock
import app  # import once now (on a clean temp DB) before the backup test rewrites the file
from tools.backup_db import make_backup, BACKUP_DIR


# ── crawl lock ───────────────────────────────────────────────────────────────
def test_crawl_lock_acquire_release():
    crawl_lock.release()
    assert not crawl_lock.is_active()
    crawl_lock.acquire("test")
    assert crawl_lock.is_active()
    assert crawl_lock.status()["origin"] == "test"
    crawl_lock.release()
    assert not crawl_lock.is_active()


def test_crawl_lock_stale_expiry():
    import json
    crawl_lock.acquire("test")
    # backdate the lock past the stale threshold
    data = json.loads(crawl_lock.LOCK_FILE.read_text())
    data["ts"] = time.time() - (crawl_lock.STALE_SECONDS + 10)
    crawl_lock.LOCK_FILE.write_text(json.dumps(data))
    assert not crawl_lock.is_active(), "stale lock should read as free"
    crawl_lock.release()


# ── backups ──────────────────────────────────────────────────────────────────
def test_backup_creates_and_prunes():
    # seed a dummy DB at the temp path
    from database.db import DB_PATH
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.write_bytes(b"SQLite format 3\x00 dummy")
    made = [make_backup(keep=3) for _ in range(5)]
    made = [m for m in made if m]
    assert made, "backups should be created on SQLite"
    autos = sorted(BACKUP_DIR.glob("auto_*.sqlite"))
    assert len(autos) <= 3, f"prune should keep <=3, found {len(autos)}"
    for p in autos:
        p.unlink()


def test_backup_noop_on_postgres(monkeypatch=None):
    os.environ["DATABASE_URL"] = "postgres://x"
    try:
        assert make_backup() is None, "backup must no-op on Postgres"
    finally:
        os.environ.pop("DATABASE_URL", None)


# ── collection upload parser ─────────────────────────────────────────────────
def test_parse_collection_csv():
    import io
    csv = (
        "Scientific Name,Common Name,Sex,Cost,Date,Vendor,Notes\n"
        "Grammostola pulchra,Brazilian Black,Female,77,2026-04-26,Fear Not,beginner pack\n"
        "Augacephalus rufus,Red Baboon,,30,2026-07-01,Justin Arras,1-inch\n"
        ",,,,,,\n"                       # junk empty row → must be skipped
        "TOTALS,,,1539,,,\n"             # junk non-species row (letters but no genus binomial)
    )
    rows = app.parse_collection_file(io.BytesIO(csv.encode()), "c.csv")
    keys = {r["species_key"] for r in rows}
    assert "grammostola pulchra" in keys
    # canonicalizer alias fix: Augacephalus stays Augacephalus (not aspinochilus)
    assert "augacephalus rufus" in keys
    # blank row dropped; sex normalized; price parsed
    gp = next(r for r in rows if r["species_key"] == "grammostola pulchra")
    assert gp["sex"] == "F" and gp["price_paid"] == 77.0
    assert gp["acquired_date"] == "2026-04-26"


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
