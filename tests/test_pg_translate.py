"""
Unit tests for the SQLite→Postgres translation layer (database/pg.py).

These are pure-function tests — they need neither psycopg nor a live Postgres, so they
validate the riskiest part of the migration (the SQL rewriting) here. The end-to-end
adapter still needs a real Postgres to fully verify; see tests/test_pg_live.py.

Run:  python tests/test_pg_translate.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.pg import qmark_to_pct, translate, split_script, rewrite_pragma


def test_qmark_basic():
    assert qmark_to_pct("SELECT * FROM t WHERE a=? AND b=?") == \
        "SELECT * FROM t WHERE a=%s AND b=%s"


def test_qmark_ignores_question_in_string():
    assert qmark_to_pct("SELECT '? literal' , ?") == "SELECT '? literal' , %s"


def test_qmark_escapes_percent_including_in_like():
    # LIKE patterns and bare % must be doubled for psycopg's parser.
    assert qmark_to_pct("WHERE x LIKE '%foo%' AND y=?") == "WHERE x LIKE '%%foo%%' AND y=%s"


def test_translate_autoincrement():
    ddl = "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    assert "BIGSERIAL PRIMARY KEY" in translate(ddl)
    assert "AUTOINCREMENT" not in translate(ddl)


def test_translate_datetime_default():
    ddl = "created_at TEXT DEFAULT (datetime('now'))"
    out = translate(ddl)
    assert "datetime(" not in out
    assert "now()" in out.lower()


def test_translate_datetime_inline():
    out = translate("SELECT datetime('now')")
    assert "datetime(" not in out and "now()" in out.lower()


def test_translate_insert_or_ignore():
    out = translate("INSERT OR IGNORE INTO vendors (vendor_key) VALUES (?)")
    assert "INSERT INTO vendors" in out
    assert out.rstrip().lower().endswith("on conflict do nothing")
    assert "OR IGNORE" not in out


def test_translate_group_concat():
    out = translate("SELECT GROUP_CONCAT(DISTINCT common_name) AS c FROM t")
    assert "string_agg" in out and "GROUP_CONCAT" not in out


def test_translate_like_to_ilike():
    out = translate("WHERE observed_at LIKE ?")
    assert "ILIKE" in out and " LIKE " not in out.upper().replace("ILIKE", "")


def test_split_script():
    script = "CREATE TABLE a (id INT); CREATE TABLE b (v TEXT DEFAULT 'x;y');"
    stmts = split_script(script)
    assert len(stmts) == 2
    assert stmts[1].startswith("CREATE TABLE b")
    assert "'x;y'" in stmts[1]          # semicolon inside a string literal is preserved


def test_rewrite_pragma_table_info():
    sql, params = rewrite_pragma("PRAGMA table_info(collection)")
    assert "information_schema.columns" in sql
    assert params == ("collection",)


def test_rewrite_pragma_noop():
    sql, params = rewrite_pragma("PRAGMA journal_mode=WAL")
    assert sql is None                  # signals a no-op to the adapter


def test_rewrite_non_pragma_passthrough():
    sql, extra = rewrite_pragma("SELECT 1")
    assert sql == "SELECT 1" and extra is ...


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


def test_pragma_table_info_shape():
    """PRAGMA table_info must translate to a row where the column name is BOTH at
    index 1 (SQLite shape: cid,name,type,...) and aliased 'name' — db.py uses r[1],
    watchlist/auth use r['name']. Regression for the Postgres first-boot crash."""
    from database.pg import rewrite_pragma
    sql, params = rewrite_pragma("PRAGMA table_info(price_history)")
    assert params == ("price_history",)
    assert "column_name AS name" in sql
    assert sql.strip().startswith("SELECT (ordinal_position - 1) AS cid, column_name AS name")
    # no-op pragmas still no-op
    assert rewrite_pragma("PRAGMA journal_mode=WAL") == (None, None)
    assert rewrite_pragma("PRAGMA foreign_keys=ON") == (None, None)
