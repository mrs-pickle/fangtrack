"""
WSGI entry point for production servers.

    gunicorn wsgi:app            # Linux / Render
    waitress-serve --port=5000 wsgi:app   # Windows

Runs the one-time table initialization that app.py's __main__ block does for local dev,
so the schema exists before the first request when served under gunicorn/waitress.
"""
import os

import app as _appmod
from app import app
from database.db import get_connection, init_db, init_discount_tables, DB_PATH
from scoring.watchlist import init_watchlist_tables

# Hosted web process: never build the heavy dashboard caches on a request (it jams
# the health check → restart loop). Serve the cron-built blobs instead.
_appmod._WEB_READONLY = True


def _init_schema():
    os.makedirs("output", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    # If a persistent-disk DB path is set, make sure its directory exists.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_db(DB_PATH)
    init_discount_tables(DB_PATH)
    init_watchlist_tables(DB_PATH)
    conn = get_connection(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS collection (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            species_key TEXT NOT NULL,
            species_display TEXT NOT NULL,
            sex TEXT,
            quantity INTEGER DEFAULT 1,
            size_notes TEXT,
            notes TEXT,
            added_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()
    # Re-run auth table init AFTER collection/watchlist exist, so the user_id columns
    # get added on a fresh deploy (init_auth ran at import, before these tables existed).
    import auth
    auth.init_auth_tables()


_init_schema()

# Load the cron-built cache blobs into memory so the first request is instant.
# Safe + cheap (one SELECT + json.loads); no heavy build happens in the web.
try:
    _appmod.hydrate_caches(force=True)
except Exception as _e:
    pass

# NOTE: we deliberately do NOT warm the caches in a background thread at boot.
# On Render's 0.5-CPU box that build saturates the CPU during startup, so Render's
# port-open detection and health check time out and the instance restart-loops.
# Instead the first request after a boot/crawl builds the cache (one slow load,
# ~30-60s, which the instance survives because boot is already complete), and the
# 1h TTL keeps every subsequent load instant. See warm_caches() in app.py.

if __name__ == "__main__":
    # Fallback: waitress if invoked directly (e.g. on Windows without gunicorn).
    from waitress import serve
    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
