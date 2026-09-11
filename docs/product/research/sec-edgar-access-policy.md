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

## The sanctioned route

SEC publishes a programmatic path and recommends it over crawling
(`https://www.sec.gov/developer`):

- **`data.sec.gov` REST APIs**, no key and no auth — `submissions/CIK##########.json`,
  `api/xbrl/companyconcept/…`, `api/xbrl/companyfacts/…`, `api/xbrl/frames/…`
- **Bulk archives**, refreshed nightly around 03:00 ET —
  `Archives/edgar/daily-index/bulkdata/submissions.zip` and
  `…/xbrl/companyfacts.zip`. One request replaces hundreds of thousands.
- Daily and quarterly index files.

Guidance: *"download only… necessary data and moderate requests to minimize
server load."* Feature requests go to `opendata@sec.gov`; SEC *"does not offer
technical support for developing or debugging scripted processes."*

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

A blanket block including static pages is **not** explained by our request shape.
Several correctly-formed user agents were tried, and `/developer` involves no
automation at all.

The remaining explanation is the caller's egress address. The tests ran from a
**residential ISP that allocates addresses across multi-dwelling buildings**, so
the SEC rate budget — *"10 requests per second regardless of the number of
machines"* — is shared with everyone behind the same address. One neighbour's
scraper is sufficient to block the address for everybody on it. The edge is
Akamai-served, which also makes IP-reputation handling plausible. **SEC
publishes nothing on either mechanism, so this is inference, not fact** — but it
is consistent with a block that covers static pages and ignores user agent
entirely.

**Documented appeals route:** contact `webmaster@sec.gov` *"with a screenshot or
the text of the error message. Include your IP address so we can attempt to
better assist you."*

## Consequence for the architecture

`runtime-architecture.md` § Trust boundaries specifies the worker reaching EDGAR
with a *"SEC-compliant user agent"*. That is necessary and **not sufficient**:
compliance did not obtain access here. Whatever address the production task
egresses from carries its own reputation, so this boundary can pass in
development and fail in production, or the reverse.

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
- Whether the block is specific to this address or to its range. Testable from
  any second network.
