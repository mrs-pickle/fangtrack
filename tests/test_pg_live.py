"""
End-to-end integration test for the Postgres adapter against a REAL Postgres.

Skipped unless TEST_DATABASE_URL is set — it needs a live database (it creates and drops
a scratch table). Use this to validate the migration before switching production over.

Quickest way to get a throwaway Postgres:
    docker run --rm -e POSTGRES_PASSWORD=pw -p 5432:5432 postgres:16
    $env:TEST_DATABASE_URL = "postgres://postgres:pw@localhost:5432/postgres"
    python tests/test_pg_live.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        print("SKIP: set TEST_DATABASE_URL to a live Postgres to run this test.")
        return 0

    from database import pg
    conn = pg.connect(dsn)
    cur = conn.cursor()
    checks = []

    def ok(name, cond):
        checks.append((name, bool(cond)))
        print(f"  {'ok  ' if cond else 'FAIL'} {name}")

    try:
        cur.executescript("""
            DROP TABLE IF EXISTS _ft_test;
            CREATE TABLE _ft_test (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()

        # lastrowid via auto-RETURNING id
        cur.execute("INSERT INTO _ft_test (name) VALUES (?)", ("alpha",))
        ok("lastrowid populated on insert", cur.lastrowid == 1)

        cur.execute("INSERT INTO _ft_test (name) VALUES (?)", ("beta",))
        ok("lastrowid increments", cur.lastrowid == 2)

        # INSERT OR IGNORE → ON CONFLICT DO NOTHING (duplicate unique name)
        cur.execute("INSERT OR IGNORE INTO _ft_test (name) VALUES (?)", ("alpha",))
        conn.commit()
        n = conn.cursor().execute("SELECT COUNT(*) FROM _ft_test").fetchone()[0]
        ok("insert-or-ignore skipped duplicate", n == 2)

        # positional + named row access
        row = conn.cursor().execute("SELECT id, name FROM _ft_test WHERE name=?", ("beta",)).fetchone()
        ok("row positional access", row[0] == 2)
        ok("row named access", row["name"] == "beta")
        ok("dict(row) works", dict(row) == {"id": 2, "name": "beta"})

        # case-insensitive LIKE (translated to ILIKE)
        r = conn.cursor().execute("SELECT COUNT(*) FROM _ft_test WHERE name LIKE ?", ("ALPHA",)).fetchone()[0]
        ok("LIKE is case-insensitive (ILIKE)", r == 1)

        # datetime default populated
        r = conn.cursor().execute("SELECT created_at FROM _ft_test WHERE name=?", ("alpha",)).fetchone()[0]
        ok("datetime('now') default populated", bool(r) and str(r)[:2] == "20")

        # PRAGMA table_info → information_schema
        cols = {row["name"] for row in conn.cursor().execute("PRAGMA table_info(_ft_test)").fetchall()}
        ok("PRAGMA table_info lists columns", {"id", "name", "created_at"} <= cols)

        conn.cursor().executescript("DROP TABLE IF EXISTS _ft_test;")
        conn.commit()
    finally:
        conn.close()

    passed = sum(1 for _, c in checks if c)
    print(f"{passed}/{len(checks)} live checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
