"""
Vendor SOURCE-POLICY scanner.

Most sellers state their captive-bred policy ONCE on their site ("we are a
breeder", "all our spiders are captive bred") rather than on every listing —
which is why ~72% of listings look "unknown" even though the seller has in fact
told us. This scans each vendor's homepage / about / FAQ / shipping pages for an
explicit policy statement and prints the evidence so a human can approve it.

The output feeds normalize/source_type.VENDOR_SOURCE_POLICY. We only ever record
a policy we can quote — never a guess.

    python tools/scan_source_policy.py
"""
import asyncio, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

PATHS = ["", "/pages/about", "/about", "/about-us", "/pages/about-us",
         "/faq", "/pages/faq", "/pages/faqs", "/pages/shipping",
         "/shipping", "/pages/our-story", "/policies"]

# Strong CB-policy claims (seller says everything they sell is captive bred)
CB_POLICY = [
    r"all (?:of )?our (?:\w+ ){0,3}(?:are|is) captive[\s-]?bred",
    r"(?:everything|all animals|all spiders|all tarantulas|all inverts)[^.]{0,40}captive[\s-]?bred",
    r"we (?:only )?(?:sell|offer|ship)[^.]{0,40}captive[\s-]?bred",
    r"100%\s*captive[\s-]?bred",
    r"we (?:are|'re) a (?:small )?(?:family )?(?:owned )?breeder",
    r"we breed (?:all|our|every)",
    r"captive[\s-]?bred (?:only|exclusively)",
    r"(?:no|never|do not sell|don't sell)[^.]{0,30}wild[\s-]?caught",
]
# Evidence they DO deal in wild-caught / imports (disqualifies a CB-only policy)
WC_SIGNAL = [
    r"wild[\s-]?caught", r"\bwc\b", r"freshly imported", r"we import",
    r"imported (?:specimens|animals|adults)",
]

CB_RE = [re.compile(p, re.I) for p in CB_POLICY]
WC_RE = [re.compile(p, re.I) for p in WC_SIGNAL]

TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"\s+")


def text_of(html: str) -> str:
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return WS.sub(" ", TAG.sub(" ", t))


async def scan(vk: str, base: str, client) -> dict:
    cb_hits, wc_hits = [], []
    for p in PATHS:
        url = base.rstrip("/") + p
        try:
            r = await client.get(url, timeout=12)
            if r.status_code != 200:
                continue
            txt = text_of(r.text)
            for rx in CB_RE:
                m = rx.search(txt)
                if m:
                    i = m.start()
                    cb_hits.append((url, txt[max(0, i - 60): i + 110].strip()))
                    break
            for rx in WC_RE:
                m = rx.search(txt)
                if m:
                    i = m.start()
                    wc_hits.append((url, txt[max(0, i - 50): i + 90].strip()))
                    break
        except Exception:
            continue
    return {"vendor": vk, "cb": cb_hits, "wc": wc_hits}


async def main():
    from vendors import REGISTRY
    import app as A
    targets = []
    for vk, cls in sorted(REGISTRY.items()):
        base = getattr(cls, "BASE_URL", None)
        if base:
            targets.append((vk, base))
    print(f"Scanning {len(targets)} vendor sites for a stated source policy…\n")
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True) as client:
        async def one(vk, base):
            async with sem:
                return await scan(vk, base, client)
        results = await asyncio.gather(*(one(vk, b) for vk, b in targets))

    cb_only, mixed, none = [], [], []
    for r in results:
        if r["cb"] and not r["wc"]:
            cb_only.append(r)
        elif r["cb"] and r["wc"]:
            mixed.append(r)
        else:
            none.append(r)

    print("=" * 78)
    print(f"CB-ONLY POLICY FOUND (quotable, no wild-caught signal): {len(cb_only)}")
    print("=" * 78)
    for r in cb_only:
        url, q = r["cb"][0]
        print(f"\n  {r['vendor']}")
        print(f"    “…{q[:150]}…”")
        print(f"    src: {url}")

    print("\n" + "=" * 78)
    print(f"MIXED — claims CB but ALSO mentions wild-caught/imports: {len(mixed)}")
    print("=" * 78)
    for r in mixed:
        print(f"\n  {r['vendor']}")
        print(f"    CB: “…{r['cb'][0][1][:110]}…”")
        print(f"    WC: “…{r['wc'][0][1][:110]}…”")

    print("\n" + "=" * 78)
    print(f"NO POLICY STATEMENT FOUND: {len(none)}")
    print("=" * 78)
    print("  " + ", ".join(r["vendor"] for r in none))

    print("\n\n--- paste-ready VENDOR_SOURCE_POLICY (CB-only vendors) ---")
    for r in cb_only:
        print(f'    "{r["vendor"]}": CB,')


if __name__ == "__main__":
    asyncio.run(main())
