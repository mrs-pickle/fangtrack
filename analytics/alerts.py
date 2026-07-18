"""
Alerts engine — the Keepa retention loop (price-drop / back-in-stock / saved
search hits), delivered to an in-app inbox and (optionally) by email.

Storage is JSON files under data/ (no SQLite schema change):
  data/saved_searches.json   user-defined recurring queries
  data/alerts_feed.json      the inbox (most recent first, capped)
  data/alerts_emitted.json   signatures already alerted on (dedup)

evaluate_and_record() is called after every crawl (web UI thread and the 5 AM
scheduled crawl). It never fabricates: a "price drop" means the same vendor's
same listing is cheaper than its previous crawl; "back in stock" means it was
out and is now in; a saved-search hit is a live listing matching the query.

Email delivery is gard-railed: it only sends if the user configured SMTP in
Settings. With no SMTP set it silently no-ops (alerts still hit the inbox), so
this ships enabled without any secret baked in.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("data")
SEARCHES_FILE = DATA_DIR / "saved_searches.json"
FEED_FILE = DATA_DIR / "alerts_feed.json"
EMITTED_FILE = DATA_DIR / "alerts_emitted.json"

FEED_CAP = 500
EMITTED_CAP = 5000


def _read(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _write(path: Path, data):
    try:
        DATA_DIR.mkdir(exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


# ── Saved searches ──────────────────────────────────────────────────────────

def load_saved_searches() -> list:
    return _read(SEARCHES_FILE, [])


def add_saved_search(name: str, criteria: dict, notify: bool = True,
                     now: str | None = None) -> dict:
    searches = load_saved_searches()
    sid = (max([s.get("id", 0) for s in searches]) + 1) if searches else 1
    entry = {"id": sid, "name": name or f"Search {sid}",
             "criteria": criteria, "notify": bool(notify),
             "created_at": now or datetime.now().isoformat()}
    searches.append(entry)
    _write(SEARCHES_FILE, searches)
    return entry


def remove_saved_search(sid: int) -> None:
    searches = [s for s in load_saved_searches() if s.get("id") != sid]
    _write(SEARCHES_FILE, searches)


# ── Matching ────────────────────────────────────────────────────────────────

def _matches(listing: dict, c: dict) -> bool:
    """Does a live listing satisfy a saved-search criteria dict?"""
    sp = (c.get("species") or "").strip().lower()
    if sp:
        hay = (listing.get("scientific_name_key") or "") + " " + \
              (listing.get("scientific_name") or "").lower() + " " + \
              (listing.get("common_name") or "").lower()
        if sp not in hay:
            return False
    genus = (c.get("genus") or "").strip().lower()
    if genus:
        key = listing.get("scientific_name_key") or ""
        if not key.startswith(genus):
            return False
    if c.get("sex") and listing.get("sex") != c["sex"]:
        return False
    mp = c.get("max_price")
    if mp and (listing.get("price_usd") or 0) > float(mp):
        return False
    mr = c.get("min_rarity")
    if mr and (listing.get("size_class_rarity_score") or listing.get("rarity_score") or 0) < int(mr):
        return False
    deal = c.get("deal")
    if deal == "fire" and not listing.get("is_fire_deal"):
        return False
    if deal == "gem" and listing.get("deal_rating") not in ("💎💎", "💎") and not listing.get("is_fire_deal"):
        return False
    if c.get("females_only") and listing.get("sex") != "F":
        return False
    return True


# ── Evaluation ──────────────────────────────────────────────────────────────

def evaluate_and_record(snapshot: list, db_path=None, settings: dict | None = None,
                        now: str | None = None) -> list:
    """Compute new alert events since the last crawl, append them to the inbox,
    optionally email them, and return the list of NEW events."""
    now = now or datetime.now().isoformat()
    emitted = set(_read(EMITTED_FILE, []))
    new_events: list[dict] = []

    def _emit(ev: dict, sig: str):
        if sig in emitted:
            return
        emitted.add(sig)
        ev["ts"] = now
        new_events.append(ev)

    # Movers (fire / drops / back-in-stock) sourced from the analytics layer.
    try:
        from analytics.market import market_movers
        mv = market_movers(snapshot, db_path, limit=50)
    except Exception:
        mv = {"fire": [], "drops": [], "back_in_stock": []}

    for l in mv.get("fire", []):
        sig = f"fire|{l.get('scientific_name_key')}|{l.get('vendor_key')}|{l.get('price_usd')}"
        _emit({"type": "fire", "icon": "🔥",
               "title": f"All-time-low: {l.get('scientific_name','')[:40]}",
               "detail": f"${l.get('price_usd',0):.0f} at {l.get('vendor_key')}"
                         + (f" (${l.get('landed_cost'):.0f} shipped)" if l.get('landed_cost') else ""),
               "species_key": l.get("scientific_name_key"),
               "url": l.get("product_url") or ""}, sig)

    for d in mv.get("drops", []):
        sig = f"drop|{d.get('scientific_name_key')}|{d.get('vendor_key')}|{d.get('new_price')}"
        _emit({"type": "price_drop", "icon": "▼",
               "title": f"Price drop: {d.get('scientific_name','')[:40]}",
               "detail": f"${d.get('prev_price',0):.0f} → ${d.get('new_price',0):.0f} "
                         f"(−{int(d.get('pct',0))}%) at {d.get('vendor_key')}",
               "species_key": d.get("scientific_name_key"),
               "url": d.get("product_url") or ""}, sig)

    for l in mv.get("back_in_stock", []):
        sig = f"back|{l.get('scientific_name_key')}|{l.get('vendor_key')}"
        _emit({"type": "back_in_stock", "icon": "↺",
               "title": f"Back in stock: {l.get('scientific_name','')[:40]}",
               "detail": f"${l.get('price_usd',0):.0f} at {l.get('vendor_key')}",
               "species_key": l.get("scientific_name_key"),
               "url": l.get("product_url") or ""}, sig)

    # Saved-search hits
    for s in load_saved_searches():
        if not s.get("notify", True):
            continue
        c = s.get("criteria") or {}
        for l in snapshot:
            if not _matches(l, c):
                continue
            sig = (f"ss{s['id']}|{l.get('scientific_name_key')}|{l.get('vendor_key')}"
                   f"|{l.get('size_text') or ''}|{l.get('price_usd')}")
            _emit({"type": "saved_search", "icon": "🎯",
                   "title": f"'{s['name']}' → {l.get('scientific_name','')[:36]}",
                   "detail": f"${l.get('price_usd',0):.0f} · {l.get('size_text') or '?'} · {l.get('vendor_key')}",
                   "species_key": l.get("scientific_name_key"),
                   "url": l.get("product_url") or ""}, sig)

    if new_events:
        feed = _read(FEED_FILE, [])
        feed = new_events + feed
        _write(FEED_FILE, feed[:FEED_CAP])
        # cap emitted set
        em = list(emitted)[-EMITTED_CAP:]
        _write(EMITTED_FILE, em)
        if settings:
            try:
                _maybe_email(settings, new_events)
            except Exception:
                pass

    return new_events


def load_feed(limit: int = 200) -> list:
    return _read(FEED_FILE, [])[:limit]


def mark_all_read() -> None:
    feed = _read(FEED_FILE, [])
    for ev in feed:
        ev["read"] = True
    _write(FEED_FILE, feed)


def unread_count() -> int:
    return sum(1 for ev in _read(FEED_FILE, []) if not ev.get("read"))


def _maybe_email(settings: dict, events: list) -> None:
    """Email the batch of new alerts, only if SMTP is configured."""
    if not (settings.get("notify_email") and settings.get("smtp_user")
            and settings.get("smtp_pass")):
        return
    import smtplib
    lines = [f"{e.get('icon','')} {e.get('title','')}\n    {e.get('detail','')}"
             + (f"\n    {e.get('url')}" if e.get('url') else "")
             for e in events[:50]]
    body = ("FangTrack Pro — %d new alert(s)\n\n" % len(events)) + "\n\n".join(lines)
    subject = f"🕷 FangTrack — {len(events)} new alert(s)"
    msg = (f"From: {settings['smtp_user']}\r\nTo: {settings['notify_email']}\r\n"
           f"Subject: {subject}\r\n\r\n{body}")
    with smtplib.SMTP(settings["smtp_host"], settings["smtp_port"]) as srv:
        srv.starttls()
        srv.login(settings["smtp_user"], settings["smtp_pass"])
        srv.sendmail(settings["smtp_user"], [settings["notify_email"]], msg.encode("utf-8"))
