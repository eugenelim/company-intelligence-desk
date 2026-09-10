# Fund and ETF source tier — fact check

> Discipline: primary-source fact check (SEC rule releases and form pages)

Commissioned 2026-09-10 to close the open source-tier question in
[`evidence-backed-fund-diligence.md`](../intents/evidence-backed-fund-diligence.md),
which recorded a working form set as **unverified**. Four of the five
assumptions held; the one that failed is the one the intent's governance route
depended on.

**Everything below is dated.** The N-PORT regime is actively unsettled — see
§ 2 — so any artifact restating a cadence should carry the date and name the
pending proposal rather than assert a stable rule.

## 1. The headline result

**The ratified constraint does not already cover funds.** The intent assumed
"domestic SEC periodic filings" might stretch to fund filings without
amendment. It does not, and the reason is statutory placement rather than
wording:

| Form family | Statutory hook | Reached by "periodic filings"? |
| --- | --- | --- |
| `N-CSR` / `N-CSRS` | Exchange Act § 13(a) / 15(d), via Rule 30d-1 — the same hook as `10-K` / `10-Q` | **Yes.** The SEC expressly designated these periodic reports. |
| `N-PORT`, `N-CEN` | Investment Company Act § 30, via Rules 30b1-9 and 30a-1 | **Ambiguous.** Periodic in ordinary language, distinct statutory regime. No SEC source found that either includes or excludes them from the label. |
| `485APOS`, `485BPOS`, `497`, `497K` | Securities Act registration statements and prospectus filings | **No.** These are not reports at all. |

The third row is the problem. **A fund's fees, strategy language, and objective
live in the registration-statement family** — precisely what this intent's
phase 1 proposes to analyse. So the constraint must be amended for funds, not
merely reinterpreted. That amendment is a separate act from the charter
amendment the intent already names.

The SEC designated N-CSR a periodic report in *Certification of Management
Investment Company Shareholder Reports and Designation of Certified Shareholder
Reports as Exchange Act Periodic Reporting Forms* (June 2003), adopting Rule
30d-1.

## 2. Portfolio holdings — `N-PORT`, and why it is unsettled

**Currently in force** (2019 interim final rule, IC-33384): a fund files a
report for **each month in the fiscal quarter, not later than 60 days after
quarter-end**; records must be maintained within 30 days of each month-end;
**only the third month of the quarter becomes public**. N-PORT replaced Form
N-Q and covers registered funds other than money market funds and SBICs.

So a fund's public holdings arrive **four times a year, roughly 60 days in
arrears**.

The August 2024 amendments (IC-35308) would have made filing monthly within 30
days and each month public after 60. **They are not in force.** Compliance dates
were extended in April 2025 to **17 Nov 2027** (fund groups ≥ $1bn) and
**18 May 2028** (< $1bn). On **18 February 2026** the SEC proposed (IC-35962,
S7-2026-05) to add 15 days to the monthly filing deadline and **restore
quarterly public availability** — substantially unwinding the 2024 change before
it ever binds. Comments closed April 2026; **no adopting release was located**.

The N-CEN portion of the 2024 release was *not* delayed and took effect
17 Nov 2025.

## 3. Shareholder reports — `N-CSR`, and where the detail moved

N-CSR is filed **within 10 days of transmission to shareholders** of a report
required under Rule 30e-1; EDGAR distinguishes `N-CSR` (annual) from `N-CSRS`
(semi-annual).

The **Tailored Shareholder Reports** rule was adopted **26 October 2022** —
not 2023, as the intent assumed — with a compliance date of **24 July 2024**. It
applies to funds registered on Form N-1A, so mutual funds and ETFs.

**The consequence is material for retrieval, not just for drafting.** The report
transmitted to shareholders is now deliberately thin and per share class per
series; the financial statements and schedule of investments moved into new
items on **Form N-CSR itself**. A pipeline that reads "the shareholder report"
gets the concise document; the financial detail is in the N-CSR filing body.
Reports transmitted on or after 24 July 2024 are tagged in Inline XBRL.

## 4. Annual census — `N-CEN`

Confirmed as assumed: census information annually, **within 75 days of fiscal
year-end** (75 days after calendar year-end for unit investment trusts). It
replaced the semi-annual Form N-SAR, which was rescinded concurrently;
compliance date 1 June 2018. From 17 Nov 2025 it also carries liquidity-risk
service-provider reporting.

## 5. Registration and prospectus — `N-1A`, `485APOS`, `485BPOS`, and `497`

Confirmed as assumed. N-1A is the registration form for open-end management
investment companies, covering mutual funds and ETFs organised as open-end
funds. Under 17 CFR 230.485:

- **485(a)** — material changes or a new series. Effective automatically on the
  **60th day** after filing (material changes) or the **75th day** (new series),
  subject to a registrant-designated later date.
- **485(b)** — effective **immediately on filing**, limited to enumerated
  purposes, the first being to bring financial statements up to date under
  § 10(a)(3) of the Securities Act. This is the annual update.

**Not in the intent's assumed set, and consequential:** `497` and `497K`
(definitive prospectus and summary prospectus filings, and supplements —
"stickers"). These are the highest-frequency prospectus-family filings. **A
system watching only 485BPOS will miss intra-year changes to fees and strategy.**

## 6. ETFs differ, and the difference is not on EDGAR

The EDGAR periodic form set is **identical** for ETFs and open-end mutual funds:
N-PORT, N-CSR/N-CSRS, N-CEN, N-1A/485BPOS.

The divergence is **Rule 6c-11** (the "ETF Rule", effective 23 Dec 2019,
compliance 22 Dec 2020). An ETF relying on it must post **daily portfolio
holdings on its website before market open**, plus NAV, market price,
premium/discount — with a one-year historical table and a disclosure trigger
where premium/discount exceeds 2% for more than seven consecutive trading days —
and median 30-day bid-ask spread. Rule 6c-11 also amended Form N-1A (trading
cost and bid-ask narrative; creation-unit size disclosure removed) and Form
N-CEN (an ETF indicates reliance on the rule).

**None of that daily disclosure is an SEC filing.** An EDGAR-only pipeline
systematically misses ETF daily holdings and sees them only at the quarterly
N-PORT lag. If the intent's phase 2 look-through is meant to be current rather
than 60 days stale, website disclosure is a second, non-EDGAR source with its
own trust and provenance problem — retrieved third-party content, which
[`docs/CHARTER.md`](../../CHARTER.md) principle 1 treats as adversarial input.

Rule 6c-11 excludes unit investment trusts, leveraged and inverse ETFs,
share-class ETFs, feeder funds, and non-transparent active ETFs.

## 7. Other recurring forms

- **`N-MFP`** — money market fund monthly report of fund and portfolio
  information, filed by the **fifth business day** of the month. MMFs are
  excluded from N-PORT. Amended by the 2023 MMF Reforms (33-11211), compliance
  11 June 2024.
- **`N-CR`** — money market fund *current* report. Event-driven, not periodic;
  same 2024 compliance date.
- **`24F-2NT`** — annual notice of securities sold under Rule 24f-2, filed by
  open-end funds and UITs to pay registration fees.
- **`N-23c-3`** — periodic repurchase by **closed-end interval funds**. *Not*
  applicable to open-end mutual funds or ETFs; relevant only if scope extends
  to interval funds.

## Known unknowns

Answerable, and not answered in this pass. Each must be closed before anything
ratifies on it:

- **The 120-day annual registration-statement update.** Derives from Rule 8b-16
  under the Investment Company Act; not retrieved from a primary source here.
  Verify 17 CFR 270.8b-16 before relying on the figure.
- **The `24F-2NT` deadline.** Form type and annual cadence are confirmed from
  EDGAR filings; the commonly cited "90 days after fiscal year-end" was not
  grounded in an SEC rule page.
- **Whether S7-2026-05 has since been adopted.** No adopting release was found,
  but the SEC's 2026 final-rule releases were not searched exhaustively. One
  confirmatory check is warranted before the N-PORT cadence above is relied on.
- **Whether IC-35963** (Investment Company Names / Form N-PORT Reporting,
  Feb 2026) changes anything beyond the Names Rule compliance dates. It appeared
  in results but was not retrieved.

## Unknowable from available evidence

- **Whether N-PORT and N-CEN count as "periodic filings"** in the sense the
  ratified constraint intends. The SEC has expressly designated N-CSR a periodic
  report and has made no corresponding statement either way for N-PORT or
  N-CEN. This is a drafting question for the owner, not a fact to be looked up:
  the constraint's wording must decide it, because the source will not.

## Sources

All primary, all `sec.gov` unless noted.

- Amendments to Timing Requirements for Filing Reports on Form N-PORT, IC-33384
  (27 Feb 2019), and press release 2019-23.
- Investment Company Reporting Modernization — small entity compliance guide.
- Press release 2024-110 (28 Aug 2024, IC-35308); press release 2025-64
  (16 Apr 2025) and rule page S7-26-22; press release 2026-19 and proposing
  release IC-35962 (18 Feb 2026), rule page S7-2026-05.
- Certification of Management Investment Company Shareholder Reports and
  Designation of Certified Shareholder Reports as Exchange Act Periodic
  Reporting Forms (June 2003).
- Division of Investment Management, Tailored Shareholder Reports FAQs;
  ADI 2024-14, Tailored Shareholder Report Common Issues.
- Form N-CEN.
- 17 CFR 230.485 (retrieved via the Cornell LII mirror, not sec.gov);
  ADI 2019-07 on automatic effectiveness.
- Money Market Fund Reforms, 33-11211; Form N-MFP data sets.
- Exchange-Traded Funds: A Small Entity Compliance Guide (Rule 6c-11).
