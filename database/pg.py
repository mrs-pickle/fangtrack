"""
Opt-in PostgreSQL backend for FangTrack.

Active ONLY when DATABASE_URL is set (see database.db.get_connection). When it is not,
FangTrack uses SQLite exactly as before — this module is never imported, so the working
SQLite path is untouched.

The rest of the codebase is raw sqlite3: `?` placeholders, `conn.executescript(...)`,
`cur.lastrowid`, `PRAGMA table_info(...)`, and `sqlite3.Row`-style row access (by name AND
by position). Rather than rewrite hundreds of queries, this adapter wraps psycopg3 to
present that same surface, translating the small, bounded set of SQLite-isms FangTrack
uses to their Postgres equivalents at runtime.

The translation functions at the top are PURE and unit-tested (tests/test_pg_translate.py)
so the risky part is verifiable without a live Postgres. The thin psycopg wiring below
still needs a real Postgres to validate end-to-end (see DEPLOY.md).
"""
import re

# ─────────────────────────────────────────────────────────────────────────────
# Pure SQL translation (unit-tested)
# ─────────────────────────────────────────────────────────────────────────────

def qmark_to_pct(sql: str) -> str:
    """Convert `?` placeholders to psycopg's `%s` (only outside string literals), and
    double every literal `%` — including inside `LIKE '%x%'` — since psycopg's client-side
    parser treats a bare `%` as the start of a placeholder no matter where it appears."""
    out = []
    in_str = False
    quote = ""
    for ch in sql:
        if ch == "%":
            out.append("%%")            # escape literal % everywhere (strings included)
            continue
        if in_str:
            out.append(ch)
            if ch == quote:
                in_str = False
        else:
            if ch in ("'", '"'):
                in_str = True
                quote = ch
                out.append(ch)
            elif ch == "?":
                out.append("%s")
            else:
                out.append(ch)
    return "".join(out)


_NOW_TEXT = "(to_char(now() AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS'))"


def _translate_date_calls(s: str) -> str:
    """SQLite `date(x)` has no Postgres equivalent. Our timestamps are stored as ISO
    text ('YYYY-MM-DD HH:MM:SS'), so `date(col)` == the first 10 chars → substr(col,1,10),
    which matches SQLite's output and works in COUNT(DISTINCT …)/GROUP BY/MAX. `date('now')`
    → today's date as text. Scans with balanced parens so nested calls (COALESCE) survive."""
    res, i, n = [], 0, len(s)
    while i < n:
        if (s[i:i + 5].lower() == "date(" and
                (i == 0 or not (s[i - 1].isalnum() or s[i - 1] == "_"))):
            depth, j = 1, i + 5
            while j < n and depth:
                if s[j] == "(":
                    depth += 1
                elif s[j] == ")":
                    depth -= 1
                j += 1
            inner = s[i + 5:j - 1]
            if inner.strip().lower() == "'now'":
                res.append("to_char((now() AT TIME ZONE 'UTC'),'YYYY-MM-DD')")
            else:
                res.append(f"substr({inner},1,10)")
            i = j
        else:
            res.append(s[i])
            i += 1
    return "".join(res)


def translate(sql: str) -> str:
    """SQLite → Postgres translation for the constructs FangTrack actually uses.
    Applied to DML and DDL. `?`→`%s` is handled separately (after this)."""
    s = sql
    # Auto-increment integer PK → Postgres BIGSERIAL.
    s = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
               "BIGSERIAL PRIMARY KEY", s, flags=re.I)
    # datetime('now') — both as a column DEFAULT and inline in queries. Kept as TEXT to
    # match code that string-slices timestamps (row["observed_at"][:10]).
    s = re.sub(r"DEFAULT\s*\(\s*datetime\(\s*'now'\s*\)\s*\)", f"DEFAULT {_NOW_TEXT}", s, flags=re.I)
    # datetime('now', '-N days'/'+N hours'/…) → Postgres interval arithmetic (text),
    # matching SQLite's 'YYYY-MM-DD HH:MM:SS' output. Must run before the plain
    # datetime('now') rule below (that one only matches the no-argument form).
    s = re.sub(
        r"datetime\(\s*'now'\s*,\s*'([+-]?\d+)\s+(day|days|hour|hours|minute|minutes|month|months|year|years)'\s*\)",
        lambda m: ("to_char((now() AT TIME ZONE 'UTC') + interval "
                   f"'{m.group(1)} {m.group(2)}','YYYY-MM-DD HH24:MI:SS')"),
        s, flags=re.I)
    s = re.sub(r"datetime\(\s*'now'\s*\)", _NOW_TEXT, s, flags=re.I)
    # SQLite date(x) → Postgres (no date(text) function exists there).
    s = _translate_date_calls(s)
    # INSERT OR IGNORE → INSERT ... ON CONFLICT DO NOTHING.
    if re.search(r"\bINSERT\s+OR\s+IGNORE\b", s, flags=re.I):
        s = re.sub(r"\bINSERT\s+OR\s+IGNORE\b", "INSERT", s, flags=re.I)
        s = s.rstrip().rstrip(";")
        if "on conflict" not in s.lower():
            s += " ON CONFLICT DO NOTHING"
    # GROUP_CONCAT(...) → string_agg(..., ',').
    s = re.sub(r"GROUP_CONCAT\(\s*DISTINCT\s+(.+?)\)",
               r"string_agg(DISTINCT (\1)::text, ',')", s, flags=re.I)
    s = re.sub(r"GROUP_CONCAT\(\s*(.+?)\)",
               r"string_agg((\1)::text, ',')", s, flags=re.I)
    # SQLite LIKE is case-insensitive; preserve that on Postgres with ILIKE.
    s = re.sub(r"\bLIKE\b", "ILIKE", s, flags=re.I)
    return s


def split_script(script: str) -> list[str]:
    """Split a multi-statement script on top-level `;` (ignoring `;` inside string
    literals). FangTrack's DDL has no semicolons inside strings, so this is sufficient."""
    stmts, buf = [], []
    in_str = False
    quote = ""
    for ch in script:
        if in_str:
            buf.append(ch)
            if ch == quote:
                in_str = False
        else:
            if ch in ("'", '"'):
                in_str = True
                quote = ch
                buf.append(ch)
            elif ch == ";":
                stmt = "".join(buf).strip()
                if stmt:
                    stmts.append(stmt)
                buf = []
            else:
                buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


_PRAGMA_TABLE_INFO = re.compile(r"PRAGMA\s+table_info\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", re.I)


def rewrite_pragma(sql: str):
    """Translate the PRAGMAs FangTrack uses. Returns (sql_or_None). None means 'no-op'
    (e.g. journal_mode / foreign_keys), handled by the caller."""
    m = _PRAGMA_TABLE_INFO.search(sql)
    if m:
        table = m.group(1)
        # Mirror SQLite's PRAGMA table_info row shape: (cid, name, type, notnull,
        # dflt_value, pk). Callers access the column name BOTH by index 1 (r[1])
        # and by key (r["name"]), so the name must sit at position 1 AND be aliased.
        return ("SELECT (ordinal_position - 1) AS cid, column_name AS name, "
                "data_type AS type, "
                "CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull, "
                "column_default AS dflt_value, 0 AS pk "
                "FROM information_schema.columns "
                "WHERE table_name = %s AND table_schema = current_schema() "
                "ORDER BY ordinal_position"), (table,)
    if re.match(r"\s*PRAGMA\b", sql, flags=re.I):
        return None, None
    return sql, ...   # ... sentinel: not a pragma


# ─────────────────────────────────────────────────────────────────────────────
# psycopg wiring (needs a live Postgres to validate — see DEPLOY.md)
# ─────────────────────────────────────────────────────────────────────────────

class _Row:
    """sqlite3.Row-compatible: supports row[0], row['col'], dict(row), 'col' in row,
    row.get('col'), and iteration over values."""
    __slots__ = ("_cols", "_vals", "_idx")

    def __init__(self, cols, vals):
        self._cols = cols
        self._vals = vals
        self._idx = {c: i for i, c in enumerate(cols)}

    def __getitem__(self, k):
        if isinstance(k, int):
            return self._vals[k]
        return self._vals[self._idx[k]]

    def get(self, k, default=None):
        i = self._idx.get(k)
        return self._vals[i] if i is not None else default

    def keys(self):
        return list(self._cols)

    def __contains__(self, k):
        return k in self._idx

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)


def _row_factory(cursor):
    cols = [d.name for d in cursor.description] if cursor.description else []
    def make(values):
        return _Row(cols, values)
    return make


_INSERT_RE = re.compile(r"^\s*INSERT\s+INTO\b", re.I)
_RETURNING_RE = re.compile(r"\bRETURNING\b", re.I)


class PgCursor:
    """Thin sqlite3.Cursor-like wrapper over a psycopg cursor."""

    def __init__(self, pgcur):
        self._c = pgcur
        self.lastrowid = None

    def execute(self, sql, params=()):
        # PRAGMA handling first.
        pg_sql, extra = rewrite_pragma(sql)
        if pg_sql is None:                    # no-op pragma (journal_mode / foreign_keys)
            return self
        if extra is not ...:                  # PRAGMA table_info → information_schema
            self._c.execute(pg_sql, extra)
            return self

        s = qmark_to_pct(translate(sql))
        # Auto-RETURNING id so `cur.lastrowid` works after a single-row INSERT.
        # Skip ANY upsert (ON CONFLICT …): the target may be a table whose PK is
        # not `id` (e.g. vendor_source_policy keyed on vendor_key), and appending
        # RETURNING id there raises `column "id" does not exist` on Postgres.
        want_id = (_INSERT_RE.search(s) and not _RETURNING_RE.search(s)
                   and "on conflict" not in s.lower())
        if want_id:
            s = s.rstrip().rstrip(";") + " RETURNING id"
        self._c.execute(s, tuple(params) if params else None)
        if want_id:
            try:
                row = self._c.fetchone()
                self.lastrowid = row[0] if row else None
            except Exception:
                self.lastrowid = None
        return self

    def executemany(self, sql, seq):
        s = qmark_to_pct(translate(sql))
        self._c.executemany(s, [tuple(p) for p in seq])
        return self

    def executescript(self, script):
        for stmt in split_script(script):
            self.execute(stmt)
        return self

    def fetchone(self):
        return self._c.fetchone()

    def fetchall(self):
        return self._c.fetchall()

    def fetchmany(self, n=1):
        return self._c.fetchmany(n)

    def __iter__(self):
        return iter(self._c)

    @property
    def rowcount(self):
        return self._c.rowcount

    def close(self):
        self._c.close()


class PgConnection:
    """sqlite3.Connection-like wrapper so existing code (conn.execute / executescript /
    cursor / commit / close) works unchanged on Postgres."""

    def __init__(self, dsn):
        import psycopg
        self._conn = psycopg.connect(dsn, autocommit=False, row_factory=_row_factory)

    def cursor(self):
        return PgCursor(self._conn.cursor())

    def execute(self, sql, params=()):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def executescript(self, script):
        cur = self.cursor()
        cur.executescript(script)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def connect(dsn: str) -> PgConnection:
    return PgConnection(dsn)
