"""
Seed (or reset) a non-admin tester account for click-through QA.

Login: tester   Password: 12345   is_admin: 0  (sees exactly what a normal user sees)

The login form doesn't re-validate email format, so a bare "tester" works as the login
identifier. The register form would reject this (needs an @ and 8+ char password), so we
insert it directly here — idempotent: safe to run repeatedly, resets the password each time.

Runs against whatever DB the environment points at:
  - local  → SQLite (default)
  - prod   → Postgres, if DATABASE_URL is set (uses the pg-aware get_connection)

Usage:  python tools/seed_test_user.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from werkzeug.security import generate_password_hash
from database.db import get_connection

LOGIN = "tester"
PASSWORD = "12345"
DISPLAY = "Tester"


def main():
    pw_hash = generate_password_hash(PASSWORD)
    conn = get_connection()
    row = conn.execute("SELECT id, is_admin FROM users WHERE email=?", (LOGIN,)).fetchone()
    if row:
        conn.execute(
            "UPDATE users SET password_hash=?, display_name=?, is_admin=0 WHERE email=?",
            (pw_hash, DISPLAY, LOGIN))
        action = "reset (already existed)"
    else:
        conn.execute(
            "INSERT INTO users (email, password_hash, display_name, notify_email, is_admin) "
            "VALUES (?, ?, ?, ?, 0)",
            (LOGIN, pw_hash, DISPLAY, None))
        action = "created"
    conn.commit()
    backend = "Postgres" if os.environ.get("DATABASE_URL") else "SQLite"
    print(f"Tester account {action} on {backend}: login='{LOGIN}' pw='{PASSWORD}' (non-admin).")
    conn.close()


if __name__ == "__main__":
    main()
