#!/usr/bin/env python3
"""
Hit every major page against whatever DB get_connection resolves (set DATABASE_URL
to test Postgres). Prints status per route and, for any 500, the app-code frames +
the underlying DB error — so all Postgres-vs-SQLite gaps surface in ONE run.

    $env:DATABASE_URL = '<render external url>'
    python tools/pg_smoke.py
    Remove-Item Env:DATABASE_URL
"""
import os, sys, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

import wsgi
app = wsgi.app
app.config["PROPAGATE_EXCEPTIONS"] = True
c = app.test_client()

ROUTES = ["/", "/deals", "/species", "/leaderboard", "/sellers",
          "/species/grammostola%20pulchra", "/family/grammostola",
          "/transparency", "/healthz"]

for r in ROUTES:
    try:
        resp = c.get(r)
        print(f"{r:34} -> {resp.status_code}")
    except Exception as e:
        print(f"{r:34} -> ERROR  {type(e).__name__}: {str(e)[:120]}")
        tb = traceback.format_exc().splitlines()
        for line in tb:
            s = line.strip()
            if ("fangtrack_v2" in s and ".py" in s) or "psycopg" in s.lower():
                print("        " + s)
        print()
