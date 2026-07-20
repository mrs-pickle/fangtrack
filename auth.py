"""
Hand-rolled authentication for FangTrack (no flask-login / flask-wtf dependency).

Provides: a `users` table, register / login / logout routes, a `g.user` loaded per
request, `@login_required` / `@admin_required` decorators, and session-based CSRF
protection on all state-changing requests.

Model: the market data (Dashboard, Deals, Species, Vendors, About) stays PUBLIC — that's
the shared product that draws people in. Personal features (Collection, Watchlist, Alerts,
Settings) and admin tools (Crawler, discount/vendor admin) require an account. The FIRST
user to register becomes the admin and inherits any pre-existing collection/watchlist rows.

When accounts land in production, set SESSION_COOKIE_SECURE=True (HTTPS only).
"""
import functools
import hashlib
import logging
import os
import secrets
import time
from datetime import datetime, timedelta

from flask import (session, g, request, redirect, url_for, flash,
                   render_template, abort)
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_connection, DB_PATH

# ── Simple in-process rate limiter (brute-force guard on auth) ───────────────
# Good enough for a beta on a single instance. For multi-instance, move to Redis.
_RATE_HITS: dict[str, list] = {}


def _client_ip() -> str:
    # X-Forwarded-For is client-appendable, so the FIRST entry is attacker-controlled
    # (a fresh value per request would defeat the rate limiter). A trusted reverse
    # proxy (Render, nginx) appends the real client IP as the LAST entry, so trust
    # that one. FANGTRACK_PROXY_HOPS lets a deeper proxy chain pick a further-back hop.
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        parts = [p.strip() for p in fwd.split(",") if p.strip()]
        if parts:
            hops = 1
            try:
                hops = max(1, int(os.environ.get("FANGTRACK_PROXY_HOPS", "1")))
            except ValueError:
                hops = 1
            return parts[-hops] if len(parts) >= hops else parts[0]
    return request.remote_addr or "?"


def _rate_limited(bucket: str, limit: int, window_sec: int) -> bool:
    """Record a hit for `bucket`; return True if it now exceeds `limit` in the window."""
    now = time.time()
    hits = [t for t in _RATE_HITS.get(bucket, []) if now - t < window_sec]
    hits.append(now)
    _RATE_HITS[bucket] = hits
    return len(hits) > limit

# Per-user tables that get a user_id column + row-level scoping.
_USER_TABLES = ("collection", "watchlist")


def init_auth_tables(db_path=DB_PATH):
    conn = get_connection(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name  TEXT,
            notify_email  TEXT,
            is_admin      INTEGER DEFAULT 0,
            created_at    TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS password_resets (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used       INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    for tbl in _USER_TABLES:
        cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({tbl})")]
        if cols and "user_id" not in cols:
            conn.execute(f"ALTER TABLE {tbl} ADD COLUMN user_id INTEGER")
    # Public-profile columns (shareable collections + leaderboard).
    ucols = [r["name"] for r in conn.execute("PRAGMA table_info(users)")]
    if "is_public" not in ucols:
        conn.execute("ALTER TABLE users ADD COLUMN is_public INTEGER DEFAULT 0")
    if "handle" not in ucols:
        conn.execute("ALTER TABLE users ADD COLUMN handle TEXT")
    # Real name — PRIVATE (added in Settings, not at signup; never shown publicly).
    if "first_name" not in ucols:
        conn.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
    if "last_name" not in ucols:
        conn.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
    # Declarative admin allowlist: FANGTRACK_ADMIN_EMAILS (comma-separated) promotes
    # those accounts to admin at startup. Promotes EXISTING users only — never demotes,
    # never creates. Lets us grant admin without direct DB access. Idempotent.
    for _ae in [e.strip().lower() for e in os.environ.get("FANGTRACK_ADMIN_EMAILS", "").split(",") if e.strip()]:
        conn.execute("UPDATE users SET is_admin=1 WHERE lower(email)=? AND is_admin=0", (_ae,))
    # One-time migration: legacy private sellers (imported before per-user isolation,
    # user_id IS NULL) belonged to the admin who curated them — assign them to the
    # first admin so they become that account's private sellers. Idempotent (only
    # touches unowned rows). With no admin yet, they stay hidden from everyone (safe).
    try:
        _admin = conn.execute("SELECT id FROM users WHERE is_admin=1 ORDER BY id LIMIT 1").fetchone()
        if _admin:
            conn.execute("UPDATE vendors SET user_id=? "
                         "WHERE platform='private_seller' AND user_id IS NULL", (_admin["id"],))
    except Exception:
        pass
    conn.commit()
    conn.close()


def current_user():
    """The logged-in user row (sqlite3.Row) or None."""
    return getattr(g, "user", None)


def current_user_id():
    u = current_user()
    return u["id"] if u else None


def _load_logged_in_user():
    uid = session.get("user_id")
    g.user = None
    if uid is not None:
        conn = get_connection(DB_PATH)
        g.user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        conn.close()
        if g.user is None:          # stale session (user deleted)
            session.pop("user_id", None)


def login_required(view):
    @functools.wraps(view)
    def wrapped(*a, **k):
        if current_user() is None:
            flash("Please sign in to use that.", "error")
            return redirect(url_for("login", next=request.full_path))
        return view(*a, **k)
    return wrapped


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*a, **k):
        u = current_user()
        if u is None:
            return redirect(url_for("login", next=request.full_path))
        if not u["is_admin"]:
            abort(403)
        return view(*a, **k)
    return wrapped


def _valid_email(e):
    return "@" in e and "." in e.split("@")[-1] and len(e) <= 200


log = logging.getLogger("auth")


def _abs_url(path: str) -> str:
    """Build an absolute URL for links that leave the app (emails). Prefer the
    configured public base URL; fall back to the request's own host."""
    base = os.environ.get("FANGTRACK_BASE_URL", "").rstrip("/")
    if base:
        return base + path
    return request.url_root.rstrip("/") + path


def _deliver_reset_email(to_addr: str, name: str, link: str) -> None:
    """Send the reset link. If SMTP isn't configured (local dev), log the link so
    it's still testable. Never raises — a failed send must not reveal account state."""
    body = (f"Hi {name or 'there'},\n\n"
            f"Someone requested a password reset for your FangTrack account. "
            f"Click the link below to choose a new password (it expires in 1 hour):\n\n"
            f"{link}\n\n"
            f"If you didn't request this, you can safely ignore this email — your "
            f"password won't change.\n\n— FangTrack")
    try:
        import app as _app
        _app.send_email(to_addr, "Reset your FangTrack password", body)
        log.info(f"Password-reset email sent to {to_addr}")
    except Exception as e:
        # Local/dev without SMTP, or a transient send failure: log the link so the
        # flow is still usable, but don't surface anything to the requester.
        log.warning(f"Reset email not sent ({e}); link for {to_addr}: {link}")


def _deliver_welcome_email(to_addr: str, name: str) -> None:
    """Send the branded multipart welcome email on signup (copy approved by
    Mike 2026-07-19). Best-effort — a failed send must never break
    registration; without SMTP (local dev) it just logs."""
    try:
        import app as _app
        html, text = _app.render_email(
            "welcome", display_name=name,
            cta_url=f"{_app.SITE_URL}/deals", cta_label="Browse today's deals")
        _app.send_email(to_addr, "Welcome to FangTrack 🕷️", text, html=html)
        log.info(f"Welcome email sent to {to_addr}")
    except Exception as e:
        log.warning(f"Welcome email not sent to {to_addr}: {e}")


def init_auth(app):
    """Wire CSRF, the per-request user loader, and auth routes onto the app."""
    init_auth_tables()

    @app.before_request
    def _auth_before():
        # Static assets (/static, /tokens) are public, GET-only, and never mutate
        # state. Skip the user-load + CSRF-token write so no `session` cookie rides
        # on them: a Set-Cookie makes Cloudflare (and any CDN) refuse to cache the
        # response. Sessions aren't permanent, so with no session write these
        # responses carry neither Set-Cookie nor Vary: Cookie → edge-cacheable.
        #
        # /healthz is Render's liveness probe: hit every few seconds with no cookie.
        # Keep it a pure in-memory 200 with zero per-request work (no user-load, no
        # session/CSRF write) so a slow Postgres can never delay the probe and flap
        # the instance — the 2026-07-20 outage was health-check timeouts, not a crash.
        p = request.path
        if p in ("/healthz", "/robots.txt") or p.startswith("/static/") or p.startswith("/tokens/"):
            return
        _load_logged_in_user()
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = request.form.get("_csrf") or request.headers.get("X-CSRFToken")
            if not sent or not secrets.compare_digest(str(sent), session["_csrf"]):
                abort(400, "CSRF token missing or invalid — reload the page and retry.")

    @app.context_processor
    def _auth_context():
        return {"current_user": current_user(), "csrf_token": session.get("_csrf", "")}

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user():
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            if _rate_limited(f"register:{_client_ip()}", limit=5, window_sec=600):
                flash("Too many sign-up attempts. Wait a few minutes.", "error")
                return render_template("register.html")
            email = (request.form.get("email") or "").strip().lower()
            pw = request.form.get("password") or ""
            name = (request.form.get("display_name") or "").strip() or email.split("@")[0]
            if not _valid_email(email):
                flash("Enter a valid email address.", "error")
            elif len(pw) < 8:
                flash("Password must be at least 8 characters.", "error")
            else:
                conn = get_connection(DB_PATH)
                exists = conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone()
                if exists:
                    conn.close()
                    flash("That email is already registered — sign in instead.", "error")
                    return render_template("register.html")
                is_first = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0
                # Registration NEVER grants admin (a public signup on a fresh/empty DB
                # would otherwise hand admin to a stranger). Admin comes only from the
                # FANGTRACK_ADMIN_EMAILS allowlist (see init_auth_tables).
                cur = conn.execute(
                    "INSERT INTO users (email, password_hash, display_name, notify_email, is_admin) "
                    "VALUES (?,?,?,?,0)",
                    (email, generate_password_hash(pw), name, email))
                uid = cur.lastrowid
                if is_first:
                    # First account still inherits any pre-existing single-user data.
                    for tbl in _USER_TABLES:
                        conn.execute(f"UPDATE {tbl} SET user_id=? WHERE user_id IS NULL", (uid,))
                conn.commit()
                conn.close()
                session.clear()
                session["user_id"] = uid
                _deliver_welcome_email(email, name)
                flash("Welcome to FangTrack!" + (" You're the admin." if is_first else ""), "success")
                return redirect(url_for("dashboard"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user():
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            if _rate_limited(f"login:{_client_ip()}", limit=8, window_sec=300):
                flash("Too many attempts. Wait a few minutes and try again.", "error")
                return render_template("login.html")
            email = (request.form.get("email") or "").strip().lower()
            pw = request.form.get("password") or ""
            conn = get_connection(DB_PATH)
            u = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            conn.close()
            if u and check_password_hash(u["password_hash"], pw):
                session.clear()
                session["user_id"] = u["id"]
                nxt = request.args.get("next") or request.form.get("next")
                # only allow local redirects; reject "//" and "/\" — browsers
                # normalize backslashes to "/", so "/\evil.com" is protocol-relative.
                if (nxt and nxt.startswith("/") and not nxt.startswith("//")
                        and not nxt.startswith("/\\")):
                    return redirect(nxt)
                return redirect(url_for("dashboard"))
            flash("Wrong email or password.", "error")
        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    def logout():
        # POST-only so a cross-site <img src="/logout"> can't force a sign-out;
        # the before_request CSRF guard covers the POST.
        session.clear()
        flash("Signed out.", "success")
        return redirect(url_for("dashboard"))

    @app.route("/settings/password", methods=["POST"])
    @login_required
    def change_password():
        u = current_user()
        current = request.form.get("current_password") or ""
        new = request.form.get("new_password") or ""
        if not check_password_hash(u["password_hash"], current):
            flash("Current password is incorrect.", "error")
        elif len(new) < 8:
            flash("New password must be at least 8 characters.", "error")
        elif new == current:
            flash("New password must be different from the current one.", "error")
        else:
            conn = get_connection(DB_PATH)
            conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                         (generate_password_hash(new), u["id"]))
            conn.commit()
            conn.close()
            flash("Password updated.", "success")
        return redirect(url_for("settings"))

    # ── Password reset ────────────────────────────────────────────────────────
    @app.route("/forgot", methods=["GET", "POST"])
    def forgot_password():
        if current_user():
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            email = (request.form.get("email") or "").strip().lower()
            # Rate-limit by IP so this can't be used to blast reset emails.
            if _rate_limited(f"forgot:{_client_ip()}", limit=5, window_sec=600):
                flash("Too many requests. Wait a few minutes and try again.", "error")
                return render_template("forgot.html")
            conn = get_connection(DB_PATH)
            u = conn.execute("SELECT id, email, display_name FROM users WHERE email=?",
                             (email,)).fetchone()
            if u:
                token = secrets.token_urlsafe(32)
                th = hashlib.sha256(token.encode()).hexdigest()
                expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
                # Invalidate any earlier outstanding tokens for this user, then issue one.
                conn.execute("UPDATE password_resets SET used=1 WHERE user_id=? AND used=0",
                             (u["id"],))
                conn.execute("INSERT INTO password_resets (user_id, token_hash, expires_at) "
                             "VALUES (?,?,?)", (u["id"], th, expires))
                conn.commit()
                link = _abs_url(url_for("reset_password", token=token))
                _deliver_reset_email(u["email"], u["display_name"], link)
            conn.close()
            # Always the same response, whether or not the email exists (no enumeration).
            flash("If that email has an account, a reset link is on its way. "
                  "Check your inbox (and spam).", "success")
            return redirect(url_for("login"))
        return render_template("forgot.html")

    @app.route("/reset/<token>", methods=["GET", "POST"])
    def reset_password(token):
        if current_user():
            return redirect(url_for("dashboard"))
        th = hashlib.sha256(token.encode()).hexdigest()
        conn = get_connection(DB_PATH)
        row = conn.execute(
            "SELECT id, user_id, expires_at, used FROM password_resets WHERE token_hash=?",
            (th,)).fetchone()
        valid = bool(row) and not row["used"] and row["expires_at"] > datetime.utcnow().isoformat()
        if not valid:
            conn.close()
            flash("That reset link is invalid or has expired. Request a new one.", "error")
            return redirect(url_for("forgot_password"))
        if request.method == "POST":
            pw = request.form.get("password") or ""
            if len(pw) < 8:
                conn.close()
                flash("Password must be at least 8 characters.", "error")
                return render_template("reset.html", token=token)
            conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                         (generate_password_hash(pw), row["user_id"]))
            conn.execute("UPDATE password_resets SET used=1 WHERE id=?", (row["id"],))
            conn.commit()
            conn.close()
            flash("Password updated — you can sign in now.", "success")
            return redirect(url_for("login"))
        conn.close()
        return render_template("reset.html", token=token)
