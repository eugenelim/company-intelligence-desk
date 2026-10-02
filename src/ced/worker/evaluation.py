"""Analytical comparison: Phase 0 Spike 4 rerun under the current stack.

Reruns the original A/B comparison against the recorded 10-Q fixture using
the current Pydantic AI model adapter (BedrockConverseModel) and the
shipped quarantine types.

AC-0312: the record identifies provider, model id, role revision, prompt
revision, and fixture revision, and reports causality, table-anchor, and
selection/legal-exposure loss categories.

AC-0313: ``narrowing_loss`` (observations lost by vocabulary reduction) and
``boundary_loss`` (observations lost by anchor-resolution enforcement) are
independently derived from different predicates and independently serialised.

Dependency constraints:
- No pydantic_ai import: framework types are reached through
  ``ced.adapters.framework_contract`` and ``ced.adapters.bedrock.model_factory``,
  both of which have root ``ced`` and satisfy the dependency-direction gate.
- No boto3 / botocore import: AWS SDK calls go through adapters/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import platform
import re
import sys
from collections.abc import Callable
from typing import Any, Final

from ced.domain.quarantine.vocabulary import LABEL_VOCABULARY

__all__ = [
    "ANALYST_QUESTION",
    "FIXTURE_SHA256",
    "MODEL_ID",
    "SPIKE_LABELS",
    "build_producer_tuple",
    "compute_loss_breakdown",
    "derive_loss_from_qa_responses",
    "extract_filing_excerpt",
    "parse_qa_observations",
    "run",
]

# ── Constants ────────────────────────────────────────────────────────────────

#: The spike's 20-label closed vocabulary, used for the "wide" comparison.
#: Source: spikes/phase-0/quarantine_quality_spike.py ``LABELS`` set.
SPIKE_LABELS: Final = frozenset(
    {
        "revenue_increase",
        "revenue_decrease",
        "margin_expansion",
        "margin_compression",
        "segment_outperformance",
        "segment_underperformance",
        "cost_increase",
        "cost_decrease",
        "tax_rate_change",
        "share_repurchase",
        "dividend_change",
        "litigation_exposure",
        "regulatory_exposure",
        "supply_concentration",
        "customer_concentration",
        "guidance_raised",
        "guidance_lowered",
        "foreign_exchange_headwind",
        "foreign_exchange_tailwind",
        "no_material_change",
    }
)

#: SHA-256 of the recorded 10-Q fixture file — the fixture revision identifier
#: required by AC-0312. Also the filename stem under ``spikes/phase-0/fixtures/``.
FIXTURE_SHA256: Final = "4ad5bea67cedfa7542d623900355cc8d143ef95c1acc135a597f2eedabdb9177"

#: The selected non-adaptive model for both quarantined-agent and analyst roles.
#: An adaptive model fails the existing compile guard, per plan.md § Constraints.
MODEL_ID: Final = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

#: The analyst question — identical to the spike's, so results are comparable.
ANALYST_QUESTION: Final = (
    "Identify the three most material changes for a diligence reader. "
    "For each: one sentence, and cite the figure you relied on. Be terse."
)

#: The MD&A section header used to locate the excerpt — same as the spike.
_EXCERPT_START: Final = "Products and Services Performance"

#: Excerpt length in characters — same as the spike.
_EXCERPT_LENGTH: Final = 30_000

#: Fixture directory relative to the repository root.
_FIXTURES_DIR: Final = pathlib.Path("spikes") / "phase-0" / "fixtures"

#: Notes directory for the rebaseline output.
_NOTES_DIR: Final = pathlib.Path("docs") / "specs" / "walking-skeleton-evidence" / "notes"

# ── Pure computation layer ───────────────────────────────────────────────────


def _normalise(text: str) -> str:
    """Collapse whitespace runs to a single space and strip leading/trailing."""
    return re.sub(r"\s+", " ", text).strip()


def _anchor_resolves(anchor: str, excerpt: str) -> bool:
    """Return True when the first 40 normalised chars of the anchor appear in the excerpt."""
    norm = _normalise(anchor)[:40]
    return bool(norm) and norm in _normalise(excerpt)


def extract_filing_excerpt(html: str) -> str:
    """Strip HTML and return the MD&A section excerpt used by the spike.

    Pipeline matches the spike exactly:

    1. Remove ``<script>`` and ``<style>`` blocks.
    2. Strip all HTML tags.
    3. Decode simple HTML entities.
    4. Collapse whitespace.
    5. Locate ``_EXCERPT_START`` and return ``_EXCERPT_LENGTH`` chars from it.

    Raises ``ValueError`` when the section header is absent.
    """
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&#\d+;|&[a-z]+;", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)

    start = text.find(_EXCERPT_START)
    if start == -1:
        raise ValueError(f"section header {_EXCERPT_START!r} not found in the filing text")
    return text[start : start + _EXCERPT_LENGTH]


def parse_qa_observations(
    raw: str,
    excerpt: str,
    labels: frozenset[str],
    *,
    check_anchors: bool = True,
) -> tuple[list[dict[str, object]], list[tuple[str, str]]]:
    """Parse QA agent JSON output, filtering by label set and optionally anchors.

    Implements the same deterministic fail-closed parser as the spike:

    - JSON extraction by regex.
    - Label-membership check against ``labels``.
    - Anchor-resolution check against the excerpt (when ``check_anchors=True``).

    Returns ``(admitted, dropped)`` where ``dropped`` is a list of
    ``(label_or_marker, reason)`` tuples. Observations failing the label check
    are dropped with reason ``"label not in admitted set: ..."``; those passing
    the label check but failing the anchor check are dropped with reason
    ``"anchor not present in source: ..."``.

    AC-0312: same deterministic parser as the spike; all refusals are
    listed in ``dropped``.

    **Fail-closed on malformed input.** A non-list ``observations`` field, a
    non-object observation, a non-string label, and a non-string anchor each
    land in ``dropped`` with a named reason. The function always returns
    ``(admitted, dropped)`` and never raises on any JSON-shaped input.
    """
    admitted: list[dict[str, object]] = []
    dropped: list[tuple[str, str]] = []

    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return admitted, dropped

    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        dropped.append(("<parse error>", f"JSON invalid: {exc}"))
        return admitted, dropped

    raw_observations = obj.get("observations", [])
    if not isinstance(raw_observations, list):
        dropped.append(
            (
                "<parse error>",
                f"observations field is not a list: {type(raw_observations).__name__}",
            )
        )
        return admitted, dropped

    for obs in raw_observations:
        if not isinstance(obs, dict):
            dropped.append(
                (
                    "<non-object observation>",
                    f"observation is not a JSON object: {type(obs).__name__}",
                )
            )
            continue

        label = obs.get("label")
        anchor = obs.get("anchor", "")

        if not isinstance(label, str):
            dropped.append(
                (
                    "<non-string label>",
                    f"label is not a string: {type(label).__name__}",
                )
            )
            continue

        if not isinstance(anchor, str):
            dropped.append((label, f"anchor is not a string: {type(anchor).__name__}"))
            continue

        if label not in labels:
            dropped.append((str(label), f"label not in admitted set: {label!r}"))
            continue

        if check_anchors and not _anchor_resolves(str(anchor), excerpt):
            dropped.append((str(label), f"anchor not present in source: {str(anchor)[:60]!r}"))
            continue

        admitted.append(obs)

    return admitted, dropped


def compute_loss_breakdown(
    wide_pre_obs: list[dict[str, object]],
    narrow_pre_obs: list[dict[str, object]],
    narrow_post_obs: list[dict[str, object]],
    narrow_dropped_anchors: list[tuple[str, str]],
) -> dict[str, object]:
    """Return independently-derived narrowing and boundary loss breakdowns.

    AC-0313: the two costs are computed from different predicates and
    independently serialised. Collapsing them into a single total removes at
    least one key and fails the construction test.

    The two losses are derived from separate data:

    - ``narrowing_loss`` compares ``wide_pre_obs`` (spike's 20 labels, no anchor
      check) with ``narrow_pre_obs`` (shipped 3-label vocabulary, no anchor
      check). The predicate is label membership; anchor checking is excluded so
      anchor resolution plays no part. The two lists come from independent
      model calls, so the figure bounds the vocabulary's effect rather than
      isolating it.

    - ``boundary_loss`` compares ``narrow_pre_obs`` (shipped labels, no anchor)
      with ``narrow_post_obs`` (shipped labels, with anchor). The predicate is
      anchor resolution; the label set is held constant.

    Args:
        wide_pre_obs: observations admitted by the spike's 20-label vocabulary,
            no anchor check. From the wide-label QA run.
        narrow_pre_obs: observations admitted by the shipped 3-label vocabulary,
            no anchor check. From the narrow-label QA run.
        narrow_post_obs: observations admitted by the shipped 3-label vocabulary
            after anchor-resolution enforcement. A subset of narrow_pre_obs.
        narrow_dropped_anchors: ``(label, reason)`` pairs for observations in the
            narrow run that passed the label check but failed the anchor check.
    """
    narrowing_loss: dict[str, object] = {
        # Independently derived: label-only comparison across two QA runs.
        "observations_wide_pre": len(wide_pre_obs),
        "observations_narrow_pre": len(narrow_pre_obs),
        "dropped": len(wide_pre_obs) - len(narrow_pre_obs),
        "categories": {
            "causality": (
                "Causality cannot cross a closed vocabulary regardless of its size; "
                "the finding from the original spike holds for the shipped 3-label set."
            ),
            "table_anchor": (
                "N/A at the vocabulary-narrowing step — anchor enforcement is measured "
                "separately as boundary_loss."
            ),
            "selection_legal": (
                "Labels available in the spike vocabulary but absent from the shipped "
                "3-label set include litigation_exposure and regulatory_exposure; "
                "observations using those labels are excluded at the label-check step "
                "before the boundary is reached."
            ),
        },
    }

    boundary_loss: dict[str, object] = {
        # Independently derived: anchor-check comparison within the narrow QA run.
        "observations_narrow_pre": len(narrow_pre_obs),
        "observations_narrow_post": len(narrow_post_obs),
        "dropped": len(narrow_pre_obs) - len(narrow_post_obs),
        "drop_reasons": [reason for _, reason in narrow_dropped_anchors],
        "categories": {
            "causality": (
                "Causality is not recoverable at the boundary step; "
                "it was already excluded at the vocabulary-narrowing step."
            ),
            "table_anchor": (
                "Anchor-resolution failures drop observations whose quoted anchors "
                "do not appear verbatim in the source — the structural finding the "
                "spike established applies equally to facts assembled from table cells."
            ),
            "selection_legal": (
                "Legal-exposure labels are absent from the shipped vocabulary, "
                "so no boundary-step drop can apply to them in this run."
            ),
        },
    }

    return {
        "narrowing_loss": narrowing_loss,
        "boundary_loss": boundary_loss,
    }


def build_producer_tuple(
    model_id: str,
    fixture_sha: str,
    role_revision: str,
    prompt_revision: str,
    framework_version: str,
    *,
    provider: str = "bedrock",
    model_adapter: str = "BedrockConverseModel",
) -> dict[str, object]:
    """Build the producer tuple required by AC-0312.

    Fingerprints repository-owned inputs (fixture, role, prompt) and records
    provider metadata when the provider exposes it. The Bedrock converse API
    does not expose a model revision or provider snapshot in the response body,
    so ``model_revision`` is recorded as ``None``.
    """
    return {
        "provider": provider,
        "model_id": model_id,
        "model_revision": None,
        "model_adapter": model_adapter,
        "framework_version": framework_version,
        "fixture_sha256": fixture_sha,
        "role_revision": role_revision,
        "prompt_revision": prompt_revision,
    }


def derive_loss_from_qa_responses(
    wide_raw: str,
    narrow_raw: str,
    excerpt: str,
) -> dict[str, object]:
    """Derive the loss breakdown from raw QA response strings.

    Pure and offline-callable. Applies the correct ``check_anchors`` predicate
    to each observation list and returns ``compute_loss_breakdown``'s result.

    The predicate assignment is load-bearing for AC-0313:

    - ``narrow_pre_obs`` uses ``check_anchors=False`` — anchor enforcement is
      excluded so only label membership decides.
    - ``narrow_post_obs`` uses ``check_anchors=True`` — anchor resolution is
      the boundary predicate.

    Swapping these predicates (e.g. ``check_anchors=True`` for
    ``narrow_pre_obs``) conflates vocabulary narrowing with boundary enforcement
    and breaks the independent derivation AC-0313 requires.

    AC-0313.
    """
    wide_pre_obs, _ = parse_qa_observations(
        wide_raw, excerpt, SPIKE_LABELS, check_anchors=False
    )
    narrow_pre_obs, _ = parse_qa_observations(
        narrow_raw, excerpt, LABEL_VOCABULARY, check_anchors=False
    )
    narrow_post_obs, narrow_post_dropped = parse_qa_observations(
        narrow_raw, excerpt, LABEL_VOCABULARY, check_anchors=True
    )
    narrow_anchor_drops = [
        (label, reason)
        for label, reason in narrow_post_dropped
        if "anchor not present" in reason
    ]
    return compute_loss_breakdown(
        wide_pre_obs=wide_pre_obs,
        narrow_pre_obs=narrow_pre_obs,
        narrow_post_obs=narrow_post_obs,
        narrow_dropped_anchors=narrow_anchor_drops,
    )


def _verify_fixture_digest(content: bytes, expected_sha: str, path: str) -> None:
    """Verify the fixture's SHA-256, refusing with a named error if it disagrees.

    The fixture revision identifier required by AC-0312 is the SHA-256 of the
    bytes actually read from disk. ``FIXTURE_SHA256`` is the committed constant;
    a fixture file that disagrees with it is refused before any model call is
    made, so the record cannot describe a fixture it did not use.

    Raises ``ValueError`` naming the path and both digests when they disagree.
    """
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected_sha:
        raise ValueError(
            f"{path}: fixture digest mismatch: expected {expected_sha!r}, got {actual!r}"
        )


# ── Provider call layer ──────────────────────────────────────────────────────


def _sha16(text: str) -> str:
    """Return the first 16 hex chars of the SHA-256 of the UTF-8 encoding."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _ask_model(
    system: str,
    user: str,
    *,
    model_id: str = MODEL_ID,
) -> tuple[str, dict[str, int]]:
    """Run a single-turn text completion and return ``(response_text, usage)``.

    All pydantic_ai and AWS SDK references are resolved through ``ced.adapters.*``
    (root ``ced``), which satisfies the dependency-direction gate. No direct
    ``pydantic_ai`` import appears in this file.

    Returns ``(response_text, {"input_tokens": N, "output_tokens": M})``.
    """
    # Lazy imports with ced.adapters.* root — allowed in any layer by the gate.
    from ced.adapters.bedrock.model_factory import make_bedrock_model  # noqa: PLC0415
    from ced.adapters.framework_contract import Agent  # noqa: PLC0415

    model = make_bedrock_model(model_id)
    # Agent is pydantic_ai.Agent re-exported from ced.adapters.framework_contract.
    # output_type=str requests a plain-text response.
    agent: Any = Agent(model=model, output_type=str, system_prompt=system)
    result = agent.run_sync(user)
    usage = {
        "input_tokens": int(result.usage.input_tokens or 0),
        "output_tokens": int(result.usage.output_tokens or 0),
    }
    return str(result.output), usage


# ── Subcommand implementation ────────────────────────────────────────────────


def _cmd_rebaseline(args: argparse.Namespace) -> int:
    """Run the A/B analytical comparison and write the rebaseline record.

    Makes four model calls:

    1. Wide QA: quarantined-agent role reads the filing excerpt using the
       spike's 20-label vocabulary (wide comparison, reproduces prior claim).
    2. Narrow QA: quarantined-agent role reads the same excerpt using the
       shipped 3-label vocabulary (current shipped boundary).
    3. Analyst baseline: analyst reads the full filing prose (run A).
    4. Analyst post-boundary: analyst reads the narrow post-boundary
       observations (run B).

    The comparison is recorded once. A poor result is not a reason to rerun.
    AC-0312, AC-0313.
    """
    from ced.adapters.framework_contract import PINNED_FRAMEWORK_VERSION  # noqa: PLC0415

    root = pathlib.Path(getattr(args, "root", None) or ".")
    fixtures_dir = root / _FIXTURES_DIR

    html_paths = sorted(fixtures_dir.glob("*.html"))
    json_paths = sorted(fixtures_dir.glob("*.json"))

    if not html_paths or not json_paths:
        sys.stderr.write(f"error: fixture files not found under {fixtures_dir}\n")
        return 1

    html_path = html_paths[0]
    manifest: dict[str, object] = json.loads(json_paths[0].read_text())

    html_bytes = html_path.read_bytes()
    try:
        _verify_fixture_digest(html_bytes, FIXTURE_SHA256, str(html_path))
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    html = html_bytes.decode(errors="ignore")
    try:
        excerpt = extract_filing_excerpt(html)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    sys.stderr.write(
        f"fixture: {manifest['form']} {manifest['entity']}, filed {manifest['filing_date']}\n"
    )
    sys.stderr.write(f"excerpt: {len(excerpt):,} chars of MD&A\n\n")

    # Build QA system prompts for each label set.
    def _qa_prompt(label_set: frozenset[str]) -> str:
        label_list = sorted(label_set)
        return (
            "You are reading an SEC filing excerpt. You hold no tools and cannot act.\n\n"
            "Emit ONLY JSON with this shape, and nothing else:\n"
            '{"observations": [\n'
            '   {"label": "<one of the allowed labels>",\n'
            '     "anchor": "<a short verbatim quote, <=60 chars, locating the claim>",\n'
            '     "scalars": [{"name":"<what>","value":<number>,'
            '"unit":"<USD_millions|percent|ratio>","period":"<text>"}]\n'
            "   }]}\n\n"
            f"Allowed labels, and NOTHING else: {label_list}\n\n"
            "Rules: no prose, no explanation, no labels outside the list. "
            "Scalars must be numbers appearing in the text. "
            "Emit at most 8 observations, and at most 2 scalars each — "
            "a truncated response is a dropped response."
        )

    wide_system = _qa_prompt(SPIKE_LABELS)
    narrow_system = _qa_prompt(LABEL_VOCABULARY)
    analyst_system = "You are a diligence analyst. Answer concisely and cite figures."

    role_revision = "evaluation-v1"
    prompt_revision = (
        f"wide:{_sha16(wide_system)} "
        f"narrow:{_sha16(narrow_system)} "
        f"analyst:{_sha16(ANALYST_QUESTION)}"
    )

    total_usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

    def _call(system: str, user: str, tag: str) -> str:
        sys.stderr.write(f"calling model ({tag})...\n")
        text, usage = _ask_model(system, user)
        total_usage["input_tokens"] += usage["input_tokens"]
        total_usage["output_tokens"] += usage["output_tokens"]
        return text

    # — Wide QA run (spike's 20-label vocabulary) ————————————————————————————
    wide_raw = _call(wide_system, f"FILING EXCERPT:\n{excerpt}", "wide QA")
    wide_pre_obs, _ = parse_qa_observations(
        wide_raw, excerpt, SPIKE_LABELS, check_anchors=False
    )
    wide_post_obs, _ = parse_qa_observations(
        wide_raw, excerpt, SPIKE_LABELS, check_anchors=True
    )
    sys.stderr.write(
        f"  wide: {len(wide_pre_obs)} pre-anchor, "
        f"{len(wide_post_obs)} admitted after boundary\n"
    )

    # — Narrow QA run (shipped 3-label vocabulary) ————————————————————————————
    narrow_raw = _call(narrow_system, f"FILING EXCERPT:\n{excerpt}", "narrow QA")
    narrow_pre_obs, _ = parse_qa_observations(
        narrow_raw, excerpt, LABEL_VOCABULARY, check_anchors=False
    )
    narrow_post_obs, narrow_post_dropped = parse_qa_observations(
        narrow_raw, excerpt, LABEL_VOCABULARY, check_anchors=True
    )
    # Anchor drops only: passed the label check but failed the anchor check.
    narrow_anchor_drops = [
        (label, reason)
        for label, reason in narrow_post_dropped
        if "anchor not present" in reason
    ]
    sys.stderr.write(
        f"  narrow: {len(narrow_pre_obs)} pre-anchor, "
        f"{len(narrow_post_obs)} admitted after boundary, "
        f"{len(narrow_anchor_drops)} dropped by anchor\n"
    )

    # — Analyst baseline: reads full prose ————————————————————————————————————
    baseline_response = _call(
        analyst_system,
        f"{ANALYST_QUESTION}\n\nSOURCE (filing excerpt):\n{excerpt}",
        "analyst baseline",
    )

    # — Analyst post-boundary: reads narrow-admitted observations ————————————
    crossed = (
        json.dumps({"observations": narrow_post_obs}, indent=1)
        if narrow_post_obs
        else "(no observations crossed the boundary)"
    )
    boundary_response = _call(
        analyst_system,
        (
            f"{ANALYST_QUESTION}\n\nSOURCE (structured observations only — "
            f"no access to the filing prose):\n{crossed}"
        ),
        "analyst post-boundary",
    )

    sys.stderr.write("\n")

    # — Loss breakdown (predicate wiring pinned by derive_loss_from_qa_responses) ——
    loss = derive_loss_from_qa_responses(wide_raw, narrow_raw, excerpt)

    # — Producer tuple (AC-0312) ——————————————————————————————————————————————
    producer = build_producer_tuple(
        model_id=MODEL_ID,
        fixture_sha=FIXTURE_SHA256,
        role_revision=role_revision,
        prompt_revision=prompt_revision,
        framework_version=PINNED_FRAMEWORK_VERSION,
    )

    # — Comparison figures (for the A/B summary) ——————————————————————————————
    figs_baseline = set(re.findall(r"\d+(?:\.\d+)?", baseline_response))
    figs_boundary = set(re.findall(r"\d+(?:\.\d+)?", boundary_response))

    result: dict[str, object] = {
        "producer": producer,
        "fixture": {
            "sha256": FIXTURE_SHA256,
            "form": manifest["form"],
            "entity": manifest["entity"],
            "filing_date": manifest["filing_date"],
            "excerpt_chars": len(excerpt),
        },
        "platform": f"{platform.system()} ({platform.machine()})",
        "prior_claim": {
            "source": "spikes/README.md § Spike 4",
            "hypothesis": (
                "Does references-only quarantine preserve analytical quality "
                "on a real filing? Falsified if closed-vocabulary classification "
                "loses distinctions the diligence output depends on."
            ),
            "original_result": (
                "Falsified: causality, table-anchor, and selection/legal losses identified."
            ),
            "original_wide_admitted": 6,
            "original_wide_label_count": 20,
            "original_narrow_label_count": 3,
        },
        "comparison": {
            "A_baseline": baseline_response.strip(),
            "B_post_boundary": boundary_response.strip(),
            "wide_admitted": len(wide_post_obs),
            "narrow_admitted": len(narrow_post_obs),
            "figures_baseline_count": len(figs_baseline),
            "figures_boundary_count": len(figs_boundary),
            "figures_in_common": len(figs_baseline & figs_boundary),
        },
        "loss": loss,
        "usage": total_usage,
    }

    text = json.dumps(result, indent=2) + "\n"
    sys.stdout.write(text)

    out: str | None = getattr(args, "out", None)
    if out:
        out_path = root / pathlib.Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text)
        sys.stderr.write(f"written to {out}\n")

    approx_cost = (
        total_usage["input_tokens"] / 1_000_000 * 0.80
        + total_usage["output_tokens"] / 1_000_000 * 4.00
    )
    sys.stderr.write(
        f"tokens: {total_usage['input_tokens']} in / "
        f"{total_usage['output_tokens']} out   "
        f"approx cost ${approx_cost:.3f}\n"
    )
    return 0


# ── CLI entry point ──────────────────────────────────────────────────────────


def run() -> None:
    """Console-script entry point for the evaluation command.

    Intended for use as ``python -m ced.worker.evaluation`` when no dedicated
    script entry point is wired in pyproject.toml.
    """
    parser = argparse.ArgumentParser(
        prog="ced-evaluate",
        description="Phase 1 analytical quality evaluation commands.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    rebase_p = sub.add_parser(
        "rebaseline",
        help="Rerun Spike 4 A/B comparison under the current Pydantic AI stack.",
    )
    rebase_p.add_argument(
        "--out", metavar="PATH", help="Write JSON to PATH in addition to stdout."
    )
    rebase_p.add_argument(
        "--root",
        metavar="DIR",
        default=".",
        help="Repository root (default: current directory).",
    )

    dispatch: dict[str, Callable[[argparse.Namespace], int]] = {
        "rebaseline": _cmd_rebaseline,
    }
    args = parser.parse_args()
    sys.exit(dispatch[args.cmd](args))


if __name__ == "__main__":
    # Allow ``python -m ced.worker.evaluation rebaseline --out <path>``.
    run()
