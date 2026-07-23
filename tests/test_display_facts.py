"""
Showing the user what we actually know.

Both bugs here were found by beta tester 1 on 2026-07-23, and both had the same
shape: FangTrack had the right data and displayed it wrong.

Run:  python -m pytest tests/test_display_facts.py
"""
import inspect
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("FANGTRACK_DB_PATH",
                      os.path.join(tempfile.mkdtemp(), "display_test.sqlite"))

import wsgi
app = wsgi.app


def _render(sex):
    """Render the shared sex badge for one code."""
    tpl = app.jinja_env.from_string(
        '{% from "_sex.html" import sex_badge %}{{ sex_badge(s) }}')
    return tpl.render(s=sex)


# ── "?" must mean "nobody told us", not "we didn't handle this code" ────────
def test_mature_male_is_not_shown_as_unknown():
    """The reported bug: a vendor's 'Mature Male' variant parsed correctly to
    MM, then rendered as '?' because the template only knew F and M."""
    out = _render("MM")
    assert "?" not in out
    assert "Mature male" in out          # title attribute
    assert "&#9794;" in out              # the male glyph, as an HTML entity


def test_unsexed_is_not_shown_as_unknown():
    """'Unsexed' is a fact the seller stated — distinct from no data."""
    for code in ("U", "PF"):
        out = _render(code)
        assert "?" not in out, f"{code} rendered as unknown"
        assert "unsexed" in out.lower()


def test_female_and_male_still_render():
    assert "&#9792;" in _render("F")     # female glyph entity
    assert "&#9794;" in _render("M")     # male glyph entity


def test_only_a_genuinely_missing_sex_shows_a_question_mark():
    for code in ("Unknown", "", None, "garbage"):
        assert "?" in _render(code)


# ── the alias healing has to run where every crawl path converges ───────────
def test_key_alias_healing_lives_in_the_pipeline():
    """Regression guard for the real defect.

    The healing was wired into app.run_crawl_thread (the ADMIN in-process crawl)
    only, so it never ran on the prod cron — and a shipped alias sat unapplied
    for days while the site showed two cards for one species. It now lives in
    run_multi_vendor_pipeline, which the cron AND the admin crawl both call.
    """
    import pipeline
    assert hasattr(pipeline, "apply_key_aliases")
    src = inspect.getsource(pipeline.run_multi_vendor_pipeline)
    assert "apply_key_aliases" in src, \
        "the crawl pipeline must heal fragmented species keys"


def test_app_delegates_to_the_single_implementation():
    """Two copies is how the paths drifted apart in the first place."""
    import app as fangtrack
    src = inspect.getsource(fangtrack._apply_key_aliases)
    assert "from pipeline import apply_key_aliases" in src


def test_the_tester_reported_misspelling_canonicalizes():
    """A. seemani (one n) and A. seemanni must be ONE species."""
    from normalize.key_aliases import canonicalize_key
    assert canonicalize_key("aphonopelma seemani") == "aphonopelma seemanni"
    assert canonicalize_key("aphonopelma seemanni") == "aphonopelma seemanni"
