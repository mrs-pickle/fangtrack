"""
Design-token integrity + branded-email tests.

The token files (tokens/fangtrack.tokens.json + tokens/fangtrack.css) MIRROR
theme.py's rarity/deal colours for tooling and emails. theme.py stays the
single source of truth — these tests fail the suite the moment the mirror
drifts. Also guards the welcome email's content rules (links present, no
competitor names) and that send_email() goes multipart when HTML is passed.

Run:  python -m pytest tests/test_tokens.py
"""
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _tokens() -> dict:
    with open(os.path.join(ROOT, "tokens", "fangtrack.tokens.json"), encoding="utf-8") as f:
        return json.load(f)


def _tokens_css() -> str:
    with open(os.path.join(ROOT, "tokens", "fangtrack.css"), encoding="utf-8") as f:
        return f.read()


def test_tokens_rarity_mirrors_theme():
    """tokens.json rarity/deal sections must equal theme.py exactly."""
    from theme import RARITY_TIERS, DEAL_BADGES
    tok = _tokens()
    for name, t in RARITY_TIERS.items():
        assert tok["rarity"][name]["core"] == t["core"], f"{name} core drifted from theme.py"
        assert tok["rarity"][name]["text"] == t["text"], f"{name} text drifted from theme.py"
    for name, d in DEAL_BADGES.items():
        assert tok["deal"][name]["bg"] == d["bg"], f"deal {name} bg drifted from theme.py"
        assert tok["deal"][name]["text"] == d["text"], f"deal {name} text drifted from theme.py"


def test_tokens_css_matches_json_core():
    """The CSS custom properties must carry the same core values as the JSON
    (dark/:root block only — the light block deliberately overrides some)."""
    tok, css = _tokens(), _tokens_css()
    # Split on the light-theme SELECTOR (with brace) — the phrase also appears
    # in the file's header comment.
    root = css.split('[data-theme="light"] {')[0]

    def css_var(name):
        m = re.search(rf"--{re.escape(name)}:\s*(#[0-9a-fA-F]{{6}})", root)
        assert m, f"--{name} missing from tokens/fangtrack.css :root"
        return m.group(1).lower()

    expected = {
        "ft-bg": tok["color"]["surface"]["base"],
        "ft-surface": tok["color"]["surface"]["raised"],
        "ft-surface-2": tok["color"]["surface"]["card"],
        "ft-border": tok["color"]["surface"]["border"],
        "ft-text": tok["color"]["text"]["primary"],
        "ft-text-2": tok["color"]["text"]["muted"],
        "ft-text-3": tok["color"]["text"]["dim"],
        "ft-primary": tok["color"]["accent"]["primary"],
        "ft-primary-strong": tok["color"]["accent"]["primary_hover"],
        "ft-link": tok["color"]["accent"]["link"],
        "ft-accent": tok["color"]["accent"]["accent"],
        "ft-grade-fire": tok["color"]["accent"]["fire"],
        "ft-down": tok["color"]["semantic"]["down_good"],
        "ft-up": tok["color"]["semantic"]["up_bad"],
    }
    for var, want in expected.items():
        assert css_var(var) == want.lower(), f"--{var} disagrees with tokens.json"


def test_tokens_css_rarity_cores_match_theme():
    """The --ft-rarity-* vars in the copy-pasteable CSS must equal theme.py's
    cores (theme.py stays the source of truth and generates the pill CSS)."""
    from theme import RARITY_TIERS
    css = _tokens_css().lower()
    for name, t in RARITY_TIERS.items():
        m = re.search(rf"--ft-rarity-{name.lower()}:\s*(#[0-9a-f]{{6}})", css)
        assert m, f"--ft-rarity-{name.lower()} missing from tokens/fangtrack.css"
        assert m.group(1) == t["core"].lower(), \
            f"--ft-rarity-{name.lower()} drifted from theme.py"


def test_base_html_links_tokens_css():
    with open(os.path.join(ROOT, "templates", "base.html"), encoding="utf-8") as f:
        html = f.read()
    assert "/tokens/fangtrack.css" in html, "base.html no longer links the token stylesheet"
    assert "--accent-blue:#1a73e8" not in html.replace(" ", ""), \
        "base.html regrew an inline :root token block — tokens/fangtrack.css owns these now"


# ── App-dependent tests (Flask test client on a throwaway DB) ────────────────

os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("FANGTRACK_DB_PATH",
                      os.path.join(tempfile.mkdtemp(), "tokens_test.sqlite"))

import wsgi  # noqa: E402  (schema init on the temp DB)
app_module = sys.modules["app"]
flask_app = wsgi.app
flask_app.config["TESTING"] = True


def test_tokens_css_route_serves_stylesheet():
    with flask_app.test_client() as c:
        r = c.get("/tokens/fangtrack.css")
        assert r.status_code == 200
        assert "text/css" in r.content_type
        assert "--accent-blue" in r.get_data(as_text=True)


def test_welcome_email_renders_on_brand():
    """Content rules: transparency + submit links, signed Mike, plain-text
    twin exists, and no competitor names anywhere in either part."""
    html, text = app_module.render_email("welcome", display_name="Test Keeper")
    for part in (html, text):
        assert "/transparency" in part
        assert "/submit" in part
        assert "Mike" in part
        for banned in ("Keepa", "StockX", "TCG", "MorphMarket"):
            assert banned.lower() not in part.lower(), f"competitor name {banned!r} in welcome email"
    assert "Test Keeper" in html and "Test Keeper" in text
    # Branded HTML uses the token accent, and the text part is real prose.
    assert app_module._design_tokens()["color"]["accent"]["primary"] in html
    assert "<" not in text.split("--")[0].replace("<br", "")  # no stray HTML in the text part


def test_render_email_rejects_unknown_template():
    try:
        app_module.render_email("../../etc/passwd")
        assert False, "render_email accepted a non-allowlisted name"
    except ValueError:
        pass


def test_send_email_multipart(monkeypatch):
    """html=... must produce multipart/alternative with the text part intact;
    omitting html keeps plain text. SMTP is faked — nothing is sent."""
    sent = []

    class FakeSMTP:
        def __init__(self, host, port): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, u, p): pass
        def send_message(self, msg, from_addr=None, to_addrs=None):
            sent.append((msg, from_addr, to_addrs))

    monkeypatch.setattr(app_module.smtplib, "SMTP", FakeSMTP)
    settings = {"smtp_user": "resend", "smtp_pass": "x", "smtp_host": "h",
                "smtp_port": 587, "mail_from": "FangTrack <noreply@fangtrack.com>"}

    app_module.send_email("k@example.com", "Hi", "plain body", settings,
                          html="<p>html body</p>")
    msg, from_addr, to_addrs = sent[-1]
    assert msg.get_content_type() == "multipart/alternative"
    parts = {p.get_content_type(): p for p in msg.iter_parts()}
    assert "plain body" in parts["text/plain"].get_content()
    assert "html body" in parts["text/html"].get_content()
    # From stays the verified-domain address, never the SMTP username.
    assert from_addr == "noreply@fangtrack.com" and to_addrs == ["k@example.com"]

    app_module.send_email("k@example.com", "Hi", "plain only", settings)
    assert sent[-1][0].get_content_type() == "text/plain"
