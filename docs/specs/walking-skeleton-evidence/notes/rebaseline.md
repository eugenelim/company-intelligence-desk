# Rebaseline: analytical comparison under the current stack

- **Date:** 2026-09-29
- **Spec:** AC-0312, AC-0313
- **Source:** `docs/specs/walking-skeleton-evidence/notes/rebaseline.json`
- **Provider:** Amazon Bedrock, `us.anthropic.claude-haiku-4-5-20251001-v1:0`
- **Framework:** pydantic-ai 2.45.0, `BedrockConverseModel`
- **Fixture:** Apple Inc. 10-Q, filed 2026-07-31, SHA-256 `4ad5bea6...` (first 8 chars), 30,000 chars of MD&A
- **Platform:** macOS, arm64, local developer machine

## Prior claim (reproduced as written)

From `spikes/README.md` § Spike 4:

> **Hypothesis:** Does references-only quarantine preserve analytical quality on a real filing?
> Falsified if closed-vocabulary classification loses distinctions the diligence output depends on.
>
> **Result:** Falsified. Three losses identified: causality, table-anchor, selection/legal-exposure.
> The spike ran with a 20-label vocabulary, the quarantined agent admitted 6 of 8 observations
> after anchor resolution, and the analyst produced substantive output from the admitted set.

## What the current stack observes

The same question was put to the same model (`us.anthropic.claude-haiku-4-5-20251001-v1:0`)
twice over the same 30,000-character excerpt:

- **Run A (baseline):** analyst reads full filing prose
- **Run B (post-boundary):** analyst reads only what crossed the shipped quarantine boundary

The comparison **remains falsified.** Zero observations crossed the shipped boundary.
The analyst on run B could produce no analysis.

### Wide run (spike vocabulary, 20 labels)

The quarantined agent produced 8 observations with spike-vocabulary labels.
After anchor resolution: 5 admitted, 3 refused (anchors not present in source).

This replicates the spike's table-anchor finding: the agent constructs anchors
that include values from separate table cells. The verbatim-substring check correctly
refuses them, but the refused observations were substantively true.

### Narrow run (shipped vocabulary, 3 labels)

The quarantined agent produced 5 observations with shipped labels
(`revenue-recognition`, `margin-expansion`, `tax-rate-change`).
After anchor resolution: 0 admitted. All 5 refused for the same reason — anchors
that paraphrase or reconstruct table-cell content do not resolve verbatim.

The boundary worked as specified; the cost is that every observation was refused.

## Loss breakdown (independently derived)

### Narrowing loss — vocabulary reduction (20 → 3 labels)

| Metric | Value |
| --- | --- |
| Observations pre-anchor with wide vocabulary | 8 |
| Observations pre-anchor with narrow vocabulary | 5 |
| Dropped by vocabulary narrowing | 3 |

Causality and selection/legal losses are **inherent to the label-based design**
and not recoverable by widening the set:

- **Causality:** The baseline analyst identified gross margin expansion of 230 bps driven
  by tariff refunds (a non-recurring tailwind), the same finding as the spike. A label
  `margin-expansion` cannot carry why the margin moved. No enlargement of the label set
  fixes this: the content is a causal argument, not a category.

- **Selection/legal:** The baseline identified R&D spending rising sharply for AI
  infrastructure and iPhone revenue acceleration. Labels for legal and regulatory exposure
  (`litigation_exposure`, `regulatory_exposure`) are absent from the 3-label shipped set,
  so any such observations are excluded before the boundary is reached. The shipped
  vocabulary does not include them.

### Boundary loss — anchor-resolution enforcement

| Metric | Value |
| --- | --- |
| Observations pre-anchor with narrow vocabulary | 5 |
| Observations admitted after anchor check | 0 |
| Dropped by anchor resolution failure | 5 |

All five anchor failures follow the same pattern as the spike's table-anchor finding:
the model reconstructs table-cell content into a single string (e.g.,
`"Total gross margin percentage 50.1% compared to 46.5%"`) that does not appear
verbatim because the two percentages come from separate cells. The fail-closed
parser correctly refuses them.

**Table-anchor:** The structural finding from the spike applies without change.
Requiring verbatim prose quotes as anchors systematically drops the quantitative facts
most important to diligence — exactly the values that appear in tables.

## Analyst outputs

### A — baseline (full prose)

> Three Most Material Changes for Diligence
>
> 1. **R&D spending surge for AI infrastructure:** R&D expenses increased 33%
>    year-over-year in the nine-month period ($34.035B vs. $25.684B), driven by
>    "higher infrastructure-related costs, including investments in artificial intelligence",
>    signaling major capital intensity shift.
>
> 2. **iPhone revenue acceleration sustains growth:** iPhone sales grew 22% in nine months
>    ($196.515B vs. $160.561B), the largest absolute dollar contributor, primarily from
>    Pro model mix shift, indicating premium product strategy is working.
>
> 3. **Gross margin expansion despite cost pressures:** Total gross margin improved
>    230 basis points to 49.1% (nine months), with product margins up 300bps to 39.9%,
>    despite "higher costs, including memory," due to favorable product mix and tariff
>    refunds offsetting headwinds.

### B — post-boundary (no observations crossed)

> I cannot identify three material changes because no structured observations crossed
> the reporting boundary in your source data. Without access to filing prose or
> quantitative metrics, I lack the figures necessary to support a diligence analysis.
> Please provide actual financial data, KPIs, or observation records.

The result is more severe than the spike's: in the spike, 6 observations crossed and the
analyst produced partial output. Under the shipped boundary with the current model, 0
observations crossed. The comparison **remains falsified**, and the result is worse on
this metric.

## Result label

**Falsified.** The hypothesis does not hold under the current stack. The same three
losses apply: causality cannot cross a label boundary, the anchor-resolution check
drops all tabular facts, and legal/regulatory labels are absent from the shipped
vocabulary. The result is recorded without retry.

## Limits of this result

- **The three loss categories are asserted, not derived per run.** The
  construction check in `tests/worker/test_evaluation.py` pins that
  `causality`, `table_anchor` and `selection_legal` exist in both breakdowns and
  carry recorded content. It does not establish that a fresh run would
  re-derive those categories from its own output: the category text is written
  into `compute_loss_breakdown` from the spike's finding and this run's reading,
  and no check compares it against a new observation.
- **Narrowing loss bounds the vocabulary effect; it does not isolate it.** The
  figure is a difference between two independent single model calls — the wide
  run and the narrow run — each with its own sampled output. Two separate runs
  differ by more than the vocabulary they were given, so 3 dropped
  observations is an upper bound on the vocabulary's contribution, not a
  measurement of it. Isolating the vocabulary would need the same generated
  observations filtered through both label sets, which this run does not do.
- n=1: one filing, one excerpt, one prompt, one quarantined model (Haiku 4.5 used for
  both the quarantined agent and the analyst, unlike the spike which used Sonnet for
  the analyst). A stronger analyst model would widen the baseline advantage, not narrow it.
- Platform substitution: local developer machine (macOS, arm64); not a Fargate deployment.
- The shipped vocabulary was designed from a construction stub and spike record, not from
  a production vocabulary. Widening it does not fix causality; it is a separate design call.
- Approved spend: $0.025 for this run. T2 + T3 total is well below the $5 cap.
