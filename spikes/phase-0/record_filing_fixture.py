#!/usr/bin/env python3
"""Record one real SEC filing as a replay fixture.

Run this once from a network EDGAR accepts. Everything afterwards replays the
fixture, which is what runtime-architecture.md § Local development specifies and
what unblocks spike 4 permanently.

Uses only the sanctioned path: the `data.sec.gov` submissions API to resolve the
filing, then the Archives document itself. No crawling, no search-page scraping.

SEC asks automated clients to declare a reachable contact. This refuses to run
without `SEC_CONTACT` rather than inventing one — an unreachable contact is a
quieter version of not declaring at all. Use a project address, never a personal
or commit identity.

    SEC_CONTACT="Company Intelligence Desk <your-project-contact>" \
        ./.venv/bin/python record_filing_fixture.py AAPL

Redistribution: SEC states its content is public information that may be copied
and further distributed without permission, so committing the result is
consistent with its terms. The SEC seal and EDGAR trademarks are not.
"""
import gzip
import hashlib
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

# RFC 2606 reserves these for documentation; they reach nobody.
RESERVED = ("example.com", "example.org", "example.net", "example.edu",
            "localhost", "invalid", "test")

CONTACT = os.environ.get("SEC_CONTACT", "").strip()
_domain = CONTACT.rsplit("@", 1)[-1].lower() if "@" in CONTACT else ""
if not CONTACT or "@" not in CONTACT or "." not in _domain:
    sys.exit("refusing to run: set SEC_CONTACT to 'Project Name contact@domain'.\n"
             "SEC asks automated clients to declare a reachable contact; a fake "
             "one is not a declaration.")
if _domain in RESERVED or _domain.endswith(tuple("." + r for r in RESERVED)):
    sys.exit(f"refusing to run: {_domain!r} is a reserved documentation domain and "
             "reaches nobody.\nDeclaring it to SEC is not a declaration. Use a real "
             "project address.")

TICKER = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").upper()
OUT = pathlib.Path("fixtures")
MIN_INTERVAL = 0.15          # well under SEC's 10 req/s aggregate guidance
_last = [0.0]


def get(url, accept="application/json"):
    wait = MIN_INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    req = urllib.request.Request(url, headers={
        "User-Agent": CONTACT,
        "Accept-Encoding": "gzip, deflate",
        "Accept": accept,
        "Host": url.split("/")[2],
    })
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read()
            return gzip.decompress(raw) if r.headers.get("Content-Encoding") == "gzip" else raw
    except urllib.error.HTTPError as e:
        if e.code == 403:
            sys.exit(f"403 from {url.split('/')[2]}.\n"
                     "EDGAR is refusing this egress address, not this request shape — "
                     "a plain page such as /developer returns 403 too. Try another "
                     "network, or webmaster@sec.gov per SEC's documented route.")
        raise


tickers = json.loads(get("https://www.sec.gov/files/company_tickers.json"))
cik = next((f"{v['cik_str']:010d}" for v in tickers.values()
            if v["ticker"].upper() == TICKER), None)
if not cik:
    sys.exit(f"ticker {TICKER} not found in SEC's ticker map")

sub = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
rec = sub["filings"]["recent"]
idx = next((i for i, f in enumerate(rec["form"]) if f in ("10-K", "10-Q")), None)
if idx is None:
    sys.exit(f"no 10-K or 10-Q found for {TICKER}")

acc_raw, acc = rec["accessionNumber"][idx], rec["accessionNumber"][idx].replace("-", "")
doc, form, filed = rec["primaryDocument"][idx], rec["form"][idx], rec["filingDate"][idx]
url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
body = get(url, accept="text/html")

digest = hashlib.sha256(body).hexdigest()
OUT.mkdir(exist_ok=True)
(OUT / f"{digest}.html").write_bytes(body)
manifest = {
    "content_sha256": digest,
    "bytes": len(body),
    "entity": sub.get("name"),
    "cik": cik,
    "ticker": TICKER,
    "form": form,
    "filing_date": filed,
    "accession": acc_raw,
    "source_url": url,
    "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    # The declared contact is deliberately NOT recorded. It is supplied at
    # runtime via SEC_CONTACT and should not persist in repository history.
}
(OUT / f"{digest}.json").write_text(json.dumps(manifest, indent=2) + "\n")

print(f"recorded {form} for {sub.get('name')} ({TICKER}), filed {filed}")
print(f"  {len(body):,} bytes  sha256 {digest[:16]}…")
print(f"  fixtures/{digest}.html  +  .json manifest")
