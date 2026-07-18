"""
Cross-process crawl lock.

The doubling bug on 2026-07-17 happened because the web app's "Run Crawl" guard only
checked its own in-process ``_crawl_state`` — it had no idea a CLI (``main.py``) or the
scheduled job was already crawling, so a second crawl started and wrote the same day twice.

This module is the single source of truth for "is a crawl running right now, no matter who
started it." Every entrypoint (app.py, main.py, scheduled_crawl.py) acquires the lock at the
start of a crawl and releases it at the end; the UI polls ``status()`` and greys the button.
"""
import json
import os
import time
from pathlib import Path

LOCK_FILE = Path("logs/crawl.lock")
# A crawl whose lock is older than this is presumed dead (process killed without releasing),
# so the lock is treated as free. Full parallel crawls finish in ~3 min; a slow sequential
# CLI run is ~8 min. 45 min is a safe ceiling that still auto-recovers from a crash.
STALE_SECONDS = 45 * 60


def acquire(origin: str) -> None:
    """Mark a crawl as running. `origin` is a short label (app / cli / scheduled)."""
    LOCK_FILE.parent.mkdir(exist_ok=True)
    LOCK_FILE.write_text(json.dumps(
        {"pid": os.getpid(), "origin": origin, "ts": time.time()}))


def release() -> None:
    """Clear the lock. Safe to call even if the lock was never acquired."""
    try:
        LOCK_FILE.unlink()
    except FileNotFoundError:
        pass


def status() -> dict:
    """Cross-process crawl state: {active, origin, age_seconds}.

    Returns active=False when no lock exists or the lock is stale (crashed crawl)."""
    try:
        d = json.loads(LOCK_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return {"active": False, "origin": None, "age_seconds": None}
    age = time.time() - float(d.get("ts", 0))
    if age > STALE_SECONDS:
        return {"active": False, "origin": d.get("origin"), "age_seconds": age, "stale": True}
    return {"active": True, "origin": d.get("origin"), "age_seconds": age}


def is_active() -> bool:
    return status()["active"]
