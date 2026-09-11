# SEC EDGAR access policy — fact check

> Discipline: primary-source fact check (SEC.gov published policy)

Commissioned 2026-09-11 after Phase 0 spike 4 was blocked by HTTP 403, to settle
whether sending a browser user agent to get past that block is acceptable, and
what the sanctioned route actually is.

## The question that prompted this

Common practice in LLM/data tooling is to send a Chrome user agent when SEC
returns *"Your Request Originates from an Undeclared Automated Tool"*. The
question is whether that is permitted.

## What SEC requires

The declaration is published as sample headers:

```
User-Agent: Sample Company Name AdminContact@<sample company domain>.com
Accept-Encoding: gzip, deflate
Host: www.sec.gov
```

The instruction is *"Please declare your user agent in request headers."* The
block page itself reads: *"The SEC reserves the right to limit requests from
undeclared automated tools… declare your traffic by updating your user agent to
include company specific information."*

**Rate limit:** *"no more than 10 requests per second, regardless of the number
of machines used to submit requests."* The obligation is per user and aggregate
across machines; the sanction is applied per IP and clears after *"10 minutes"*
below the threshold.

## Is browser-UA spoofing prohibited?

**Precisely: not explicitly prohibited, and it defeats a stated policy.** Both
halves matter, and both are commonly over-stated in opposite directions.

What SEC actually says:

- *"The SEC does not allow 'unclassified' bots or automated tools to crawl the
  site."*
- *"Any request that has been identified as part of a botnet or an automated
  tool outside of the acceptable policy will be managed to ensure fair access
  for all users."*
- The Internet Security Policy's Computer Fraud and Abuse Act language is scoped
  to *"unauthorized attempts to **upload information and/or change
  information**"* — not to read access with a false user agent.

There is **no** SEC text about disguising, spoofing, misrepresenting, or
circumventing. So:

- Claiming "spoofing violates SEC's terms of service" **over-reads** the
  published material. No such term was found; there is no distinct Terms of Use
  page for EDGAR.
- Claiming "it is therefore fine" **ignores the plain purpose** of the rule. A
  browser user agent sent by a script is, by construction, an undeclared
  automated tool — the exact thing SEC says it does not allow.

18 U.S.C. § 1001 (false statements to a federal agency) is cited on SEC's
security page, but no SEC guidance or case law was found applying it to a user
agent header. **Do not lean on it in either direction.**

### This project's decision: declare honestly, do not spoof

Recorded 2026-09-11. A reference implementation whose purpose is to demonstrate
*governed* agent behaviour cannot ship a deliberate circumvention of a publisher's
stated access policy as its data-acquisition path. The cost of complying is a
recorded fixture; the cost of not complying is that every pattern this repository
teaches is read in the light of the one place it took a shortcut.

## The contact address this project declares

SEC's format is a name plus a reachable contact. This project declares a
project-owned address supplied at runtime through the `SEC_CONTACT` environment
variable — **never a maintainer's personal or commit identity**, which should not
be handed to third-party services as a side effect of a fetch.

The fetch path refuses to run without it rather than substituting a placeholder:
an unreachable contact in a declaration SEC asks to be genuine is a quieter form
of the same dishonesty this document declines above.

## The sanctioned route — batch, not web

This is the part that matters most, and it reframes the rate limit. SEC does not
merely tolerate programmatic consumers; it publishes a path built for them and
recommends it over crawling (`https://www.sec.gov/developer`).

**Bulk archives**, refreshed nightly around 03:00 ET. One request replaces
hundreds of thousands:

| Archive | Contains |
| --- | --- |
| `Archives/edgar/daily-index/bulkdata/submissions.zip` | Every filer's submission history |
| `Archives/edgar/daily-index/xbrl/companyfacts.zip` | Every XBRL fact for every filer |

**Index files** for incremental discovery: `/edgar/daily-index/` and
`/edgar/full-index/` (quarterly), plus `/edgar/Feed/` and `/edgar/Oldloads/`
daily archives of filings themselves.

**`data.sec.gov` REST APIs** for targeted lookups, no key and no auth —
`submissions/CIK##########.json`, `api/xbrl/companyconcept/…`,
`api/xbrl/companyfacts/…`, `api/xbrl/frames/…`

Guidance: *"download only… necessary data and moderate requests to minimize
server load."* Feature requests go to `opendata@sec.gov`; SEC *"does not offer
technical support for developing or debugging scripted processes."*

**The rate limit is a symptom, not the constraint.** A design that discovers
filings by walking the site will meet 10 req/s quickly — as this project did
within about a minute of probing. A design that pulls one nightly archive and
then fetches only the specific documents it needs will not approach it. The
limit is what SEC uses to push consumers onto the path it already built.

## Redistribution — favourable, and it settles the fixture question

SEC states that information on SEC.gov *"is considered public information and may
be copied or further distributed by users of the web site without the SEC's
permission"*, and that EDGAR public filing content is *"free to access and
reuse"*. No attribution obligation is published, and no research/commercial
distinction is drawn.

**So committing recorded filings as replay fixtures is consistent with SEC's
terms.** One caveat: the **SEC seal and EDGAR trademarks** may not be used
without authorisation, so they must not appear in branding.

## What we observed, and what it means

Every `sec.gov` path tested returned 403 from this network, including
`/developer` — a plain HTML page involving no automation at all:

| Path | Status |
| --- | --- |
| `data.sec.gov/submissions/CIK….json` | 403 |
| `www.sec.gov/cgi-bin/browse-edgar?…` | 403 |
| `www.sec.gov/Archives/edgar/data/…` | 403 |
| `www.sec.gov/files/company_tickers.json` | 403 |
| `www.sec.gov/developer` | 403 |

All five were issued within roughly a minute of each other, after several
earlier user-agent probes. That density is the cause, not the coincidence.

A blanket block including static pages is **not** explained by our request shape.
Several correctly-formed user agents were tried, and `/developer` involves no
automation at all.

**The block then cleared on its own, and that resolves the cause.** A subsequent
request from the same address, same network, with a correctly-formed user agent,
succeeded and returned a full 10-Q. So this was never IP reputation or a
permanent range block.

The explanation that fits is the documented one: rapid successive probing —
several user-agent variants and five endpoints in quick succession — tripped
SEC's rate control, which blocks the **address** rather than the request, which
is why a static page like `/developer` was refused too. SEC documents that
access resumes *"once the rate of requests has dropped below the threshold for
10 minutes"*.

An earlier revision of this document inferred a shared multi-dwelling ISP
address and a neighbour exhausting the budget. That was over-reading: the
simpler and correct explanation is self-inflicted. Recorded because the wrong
inference is the tempting one — it attributes the failure outward.

**Documented appeals route:** contact `webmaster@sec.gov` *"with a screenshot or
the text of the error message. Include your IP address so we can attempt to
better assist you."*

## What "classified" means — SEC does not say

SEC's rule that it *"does not allow 'unclassified' bots or automated tools to
crawl the site"* uses the word **once, in scare quotes, undefined**. Its two
canonical statements of the policy are not even verbally consistent: the
Accessing EDGAR Data page states the same rule while **omitting the word
entirely**. Neither page defines *classified*, *unclassified*, *botnet*, or
*acceptable policy*.

The only operational hook anywhere in the corpus is the User-Agent declaration,
and the error page is titled *"**Undeclared** Automated Tool"* with the remedy
*"updating your user agent to include company specific information"*. So in
practice *classified* almost certainly means *declares a conforming user agent* —
but **that equivalence is an inference from the error text, not a published
definition**, and nothing suggests it means known to or registered with SEC.

**There is no registration, allowlist, API-key, or high-volume programme.** The
APIs *"do not require any authentication or API keys"*. The entire mechanism for
telling SEC who you are is the contact in the user-agent string.

## robots.txt and the access policy disagree

`sec.gov/robots.txt` is a stock Drupal file with an appended SEC block. It
contains a single `User-agent: *` group, **names no specific crawler**, and has
**no `Crawl-delay` directive at all**. It explicitly `Allow`s
`/Archives/edgar/data`.

So a crawler in perfect robots.txt compliance — allowed path, no delay specified
— is still capped at 10 req/s by a policy robots.txt never mentions, and is
still blockable as an "unclassified bot". **SEC never references robots.txt in
any access-policy prose.** The two regimes are disjoint and can disagree, which
is the clearest gap in the published material.

## Consequence for the architecture

Three, in order of weight.

1. **Discovery belongs in batch.** The fetch path should acquire the nightly
   bulk archive or a daily index, and reach for individual documents only when a
   specific filing is needed. That is the difference between a design that meets
   the rate limit constantly and one that never approaches it.
2. **The rate limit must be enforced centrally in the application.** SEC's cap is
   *"regardless of the number of machines used to submit requests"* — an
   aggregate obligation on the user. A per-worker limiter cannot satisfy it, and
   no network topology enforces it. See
   [`aws-egress-addressing.md`](aws-egress-addressing.md).
3. **A compliant user agent is necessary and not sufficient.** § Trust boundaries
   specifies one; compliance alone did not obtain access while the address was
   rate-blocked. The declared contact is what lets a publisher attribute traffic
   and contact a client rather than blanket-block it.

## Known unknowns

- Whether the contact address's domain affects acceptance. SEC publishes no
  guidance on contact-domain acceptability, and this is untestable while the
  address itself is blocked.
- Whether the undeclared-tool block clears on the same 10-minute schedule as the
  rate-limit block. SEC documents the latter only.
- Whether an AWS egress address in the production region is accepted. Testable,
  and worth testing before the production fetch path is relied upon — a NAT
  gateway address is as shared as a residential one, just shared with different
  neighbours.
- Whether a sustained, rate-respecting client is ever blocked. Only bursty
  probing was observed to trigger it here.
