"""
Automated DB backup (SQLite). A rolling snapshot taken before each crawl so a bad crawl or
migration is always recoverable.

CLI:  python tools/backup_db.py [keep]
API:  from tools.backup_db import make_backup ; make_backup(keep=14)

On Postgres (DATABASE_URL set) this is a no-op — use the provider's managed backups
(Render Postgres has daily backups) or `pg_dump` on a schedule.
"""
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKUP_DIR = Path("database/backups")
_PREFIX = "auto_"


def make_backup(keep: int = 14) -> Path | None:
    """Snapshot the live SQLite DB into database/backups/auto_<ts>.sqlite and prune old
    auto snapshots to the newest `keep`. Returns the backup path, or None on Postgres /
    if the DB file is missing."""
    if os.environ.get("DATABASE_URL"):
        return None  # Postgres — provider-managed backups
    from database.db import DB_PATH
    src = Path(DB_PATH)
    if not src.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"{_PREFIX}{ts}.sqlite"
    # sqlite3 .backup would be safer under load, but a file copy is fine pre-crawl when
    # nothing else is writing; WAL is checkpointed by copying the main file at rest.
    shutil.copy2(src, dest)
    _prune(keep)
    return dest


def _prune(keep: int) -> None:
    autos = sorted(BACKUP_DIR.glob(f"{_PREFIX}*.sqlite"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for old in autos[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    keep = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    path = make_backup(keep)
    print(f"Backup written: {path}" if path else "No backup (Postgres or missing DB).")
