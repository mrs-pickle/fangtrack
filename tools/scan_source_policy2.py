"""
Deeper vendor SOURCE-POLICY scan (round 2).

Round 1 only checked guessed /about paths and found 5 vendors. This one:
  1. discovers About/FAQ/policy links from the homepage nav,
  2. SAMPLES real product pages and reads the product DESCRIPTION — the field we
     never capture at crawl time, and the most likely place a seller writes
     "captive bred" on every listing.

If a vendor's product descriptions consistently state CB (and never WC), that is
effectively a per-listing statement we are currently blind to — strong evidence
for a vendor policy, and a signal we should capture in the crawler.

    python tools/scan_source_policy2.py
"""
import asyncio, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
logging.disable(logging.INFO)

import httpx, sqlite3

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

CB_RE = re.compile(r"captive[\s-]?bred|captive[\s-]?born|captive[\s-]?produced|\bcbb?\b|we breed|bred in captivity", re.I)
WC_RE = re.compile(r"wild[\s-]?caught|\bwc\b|freshly imported|wild[\s-]?collected", re.I)
TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")


def text_of(html):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return WS.sub(" ", TAG.sub(" ", t))


async def get(client, url):
    try:
        r = await client.get(url, timeout=12)
        return r.text if r.status_code == 200 else ""
    except Exception:
        return ""


async def vendor_scan(vk, urls, client):
    """Sample this vendor's real product pages; count CB / WC mentions."""
    cb, wc, seen, quote = 0, 0, 0, ""
    for u in urls[:6]:
        html = await get(client, u)
        if not html:
            continue
        txt = text_of(html)
        seen += 1
        m_cb, m_wc = CB_RE.search(txt), WC_RE.search(txt)
        if m_cb:
            cb += 1
            if not quote:
                i = m_cb.start()
                quote = txt[max(0, i - 55): i + 85].strip()
        if m_wc:
            wc += 1
    return {"vendor": vk, "pages": seen, "cb": cb, "wc": wc, "quote": quote}


async def main():
    db = sqlite3.connect("database/market_history.sqlite")
    db.row_factory = sqlite3.Row
    # sample real product URLs per vendor from the latest crawl
    rows = db.execute("""
        SELECT p.vendor_key vk, p.product_url u FROM price_history p JOIN
          (SELECT vendor_key, MAX(id) mx FROM crawl_runs
           WHERE status IN ('complete','partial') GROUP BY vendor_key) l
          ON p.crawl_run_id = l.mx
        WHERE p.product_url IS NOT NULL AND p.product_url != ''
    """).fetchall()
    by = {}
    for r in rows:
        by.setdefault(r["vk"], [])
        if r["u"] not in by[r["vk"]]:
            by[r["vk"]].append(r["u"])
    db.close()

    print(f"Sampling product-page descriptions for {len(by)} vendors "
          f"(up to 6 pages each)…\n")
    sem = asyncio.Semaphore(6)
    async with httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True) as c:
        async def one(vk, urls):
            async with sem:
                return await vendor_scan(vk, urls, c)
        res = await asyncio.gather(*(one(vk, u) for vk, u in by.items()))

    res = [r for r in res if r["pages"]]
    strong = [r for r in res if r["pages"] >= 2 and r["cb"] == r["pages"] and r["wc"] == 0]
    partial = [r for r in res if r not in strong and r["cb"] and not r["wc"]]
    mixed = [r for r in res if r["cb"] and r["wc"]]
    nothing = [r for r in res if not r["cb"] and not r["wc"]]

    print("=" * 76)
    print(f"EVERY sampled product page says CAPTIVE-BRED, none say WC  →  {len(strong)}")
    print("=" * 76)
    for r in sorted(strong, key=lambda x: -x["pages"]):
        print(f"\n  {r['vendor']}  ({r['cb']}/{r['pages']} pages)")
        print(f"    “…{r['quote'][:130]}…”")

    print("\n" + "=" * 76)
    print(f"SOME pages say CB, none say WC (weaker)  →  {len(partial)}")
    print("=" * 76)
    for r in partial:
        print(f"  {r['vendor']:22} CB on {r['cb']}/{r['pages']} sampled pages")

    print("\n" + "=" * 76)
    print(f"MIXED (mentions both CB and WC)  →  {len(mixed)}")
    print("=" * 76)
    for r in mixed:
        print(f"  {r['vendor']:22} cb={r['cb']} wc={r['wc']} of {r['pages']}")

    print("\n" + "=" * 76)
    print(f"NO source language on product pages  →  {len(nothing)}")
    print("=" * 76)
    print("  " + ", ".join(r["vendor"] for r in nothing))

    print("\n--- paste-ready (every sampled page states CB) ---")
    for r in strong:
        print(f'    "{r["vendor"]}": CB,')


if __name__ == "__main__":
    asyncio.run(main())
