"""Construction test for the analytical comparison: AC-0312, AC-0313.

All tests are **offline** (no substrate, no provider call). They target the
pure-computation seams in ``ced.worker.evaluation``.

The goal-based provider witness (the real comparison run) is recorded in
``docs/specs/walking-skeleton-evidence/notes/rebaseline.json`` and summarised
in ``notes/rebaseline.md``.

Mutation proofs for every key these tests pin — each producer-tuple key and
each loss category, deleted one at a time — are recorded in
``docs/specs/walking-skeleton-evidence/notes/verification-ledger.md`` §§ T3, T7.
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ced.domain.quarantine.vocabulary import LABEL_VOCABULARY
from ced.worker.evaluation import (
    FIXTURE_SHA256,
    SPIKE_LABELS,
    _verify_fixture_digest,
    build_producer_tuple,
    compute_loss_breakdown,
    derive_loss_from_qa_responses,
    extract_filing_excerpt,
    parse_qa_observations,
)

# ── AC-0312: producer-tuple schema ───────────────────────────────────────────

#: The complete key set ``build_producer_tuple`` emits, read from the shipped
#: builder's return statement rather than from any prose list. Asserted as an
#: exact set, not as subset containment: a subset check cannot fail when a key
#: is deleted, so it would keep confirming an incomplete list.
EXPECTED_PRODUCER_KEYS = {
    "provider",
    "model_id",
    "model_revision",
    "model_adapter",
    "framework_version",
    "fixture_sha256",
    "role_revision",
    "prompt_revision",
}


def test_producer_tuple_emits_exactly_the_recorded_key_set() -> None:
    """``build_producer_tuple`` emits the AC-0312 key set and nothing else.

    AC-0312 requires the record to identify the provider, the model id, the
    model revision or provider snapshot when the provider exposes it, the role
    revision, the prompt revision, and the fixture revision.

    Mutations that must red this test (proved in the ledger): deleting any one
    key from the builder's returned dict. Set equality — not ``in`` — is what
    makes a deletion visible; it also reds an undeclared key being added.
    """
    producer = build_producer_tuple(
        model_id="us.example.model-v1:0",
        fixture_sha="4ad5bea6",
        role_revision="evaluation-v1",
        prompt_revision="wide:aaaa narrow:bbbb analyst:cccc",
        framework_version="2.45.0",
    )

    assert set(producer) == EXPECTED_PRODUCER_KEYS, (
        "AC-0312: the producer tuple's key set must equal the recorded set; "
        f"got {sorted(producer)}"
    )


def test_producer_tuple_values_are_the_arguments_and_the_recorded_defaults() -> None:
    """Each producer-tuple key carries the value AC-0312 names for it.

    The provider, model adapter and model revision are fixed by the builder:
    Bedrock's converse API exposes no model revision or provider snapshot in
    the response body, so ``model_revision`` is recorded as ``None`` rather
    than omitted — an absent key and a key recording "not exposed" are
    different claims.
    """
    producer = build_producer_tuple(
        model_id="us.example.model-v1:0",
        fixture_sha="4ad5bea6",
        role_revision="evaluation-v1",
        prompt_revision="wide:aaaa narrow:bbbb analyst:cccc",
        framework_version="2.45.0",
    )

    assert producer["provider"] == "bedrock"
    assert producer["model_id"] == "us.example.model-v1:0"
    assert producer["model_revision"] is None, (
        "the provider exposes no model revision; the key records that, it is not omitted"
    )
    assert producer["model_adapter"] == "BedrockConverseModel"
    assert producer["framework_version"] == "2.45.0"
    assert producer["fixture_sha256"] == "4ad5bea6"
    assert producer["role_revision"] == "evaluation-v1"
    assert producer["prompt_revision"] == "wide:aaaa narrow:bbbb analyst:cccc"


# ── AC-0313: loss-separation mutation proof ──────────────────────────────────

#: The three loss categories AC-0312 names, as the shipped builder spells them.
EXPECTED_LOSS_CATEGORIES = {"causality", "table_anchor", "selection_legal"}


def test_rebaseline_separates_narrowing_from_boundary_loss() -> None:
    """``compute_loss_breakdown`` serialises narrowing and boundary loss separately.

    AC-0313: the two costs are independently derived from different predicates
    and independently serialised. Collapsing them into a single total removes
    at least one top-level key, causing at least one assertion here to fail.

    Input contract for this test (fixed values, not computed from a constant,
    so a change to the function that merges the two fields is visible):

    - ``wide_pre_obs``: 5 observations admitted by the wide (spike) vocabulary
      with no anchor check.
    - ``narrow_pre_obs``: 2 observations admitted by the narrow (shipped)
      vocabulary with no anchor check.
    - ``narrow_post_obs``: 1 observation admitted by the narrow vocabulary
      after the anchor-resolution check.
    - ``narrow_dropped_anchors``: 1 observation whose anchor did not resolve.

    Mutation that must red this test (proved in the ledger):
        In ``compute_loss_breakdown``, replace the return value with
        ``{"total_loss": {"dropped": ...}}`` rather than two separate keys.
        Then ``"narrowing_loss" not in loss`` makes the first assertion fail.
    """
    wide_pre_obs: list[dict[str, object]] = [
        {"label": "revenue_increase", "anchor": "net sales increased", "scalars": []}
    ] * 5
    narrow_pre_obs: list[dict[str, object]] = [
        {"label": "margin-expansion", "anchor": "margin expanded", "scalars": []}
    ] * 2
    narrow_post_obs: list[dict[str, object]] = [
        {"label": "margin-expansion", "anchor": "margin expanded", "scalars": []}
    ] * 1
    narrow_dropped_anchors: list[tuple[str, str]] = [
        ("margin-expansion", "anchor not present in source: 'margin expanded'")
    ]

    loss = compute_loss_breakdown(
        wide_pre_obs=wide_pre_obs,
        narrow_pre_obs=narrow_pre_obs,
        narrow_post_obs=narrow_post_obs,
        narrow_dropped_anchors=narrow_dropped_anchors,
    )

    # Both must exist as separate top-level keys — the mutation removes one.
    assert "narrowing_loss" in loss, (
        "narrowing_loss must be a separate field; "
        "collapsing to a total removes this key and fails this assertion"
    )
    assert "boundary_loss" in loss, (
        "boundary_loss must be a separate field; "
        "collapsing to a total removes this key and fails this assertion"
    )

    nl = loss["narrowing_loss"]
    bl = loss["boundary_loss"]

    # Narrowing loss is derived from wide_pre vs narrow_pre (label-only, no anchor check).
    assert isinstance(nl, dict)
    assert nl["observations_wide_pre"] == 5, (
        "wide_pre count must reflect the input wide observation list"
    )
    assert nl["observations_narrow_pre"] == 2, (
        "narrow_pre count must reflect the input narrow observation list"
    )
    assert nl["dropped"] == 3, "dropped = wide_pre - narrow_pre = 5 - 2 = 3"

    # Boundary loss is derived from narrow_pre vs narrow_post (anchor check within narrow run).
    assert isinstance(bl, dict)
    assert bl["observations_narrow_pre"] == 2, (
        "narrow_pre count must match the narrow_pre input"
    )
    assert bl["observations_narrow_post"] == 1, (
        "narrow_post count must reflect the post-anchor input"
    )
    assert bl["dropped"] == 1, "dropped = narrow_pre - narrow_post = 2 - 1 = 1"
    assert bl["drop_reasons"] == ["anchor not present in source: 'margin expanded'"], (
        "drop_reasons must reflect the narrow_dropped_anchors input"
    )

    # AC-0312: both breakdowns report the same three loss categories as the
    # original spike. Set equality, so deleting any one category reds this.
    nl_categories = nl["categories"]
    bl_categories = bl["categories"]
    assert isinstance(nl_categories, dict)
    assert isinstance(bl_categories, dict)
    assert set(nl_categories) == EXPECTED_LOSS_CATEGORIES, (
        "AC-0312: narrowing_loss must report causality, table_anchor and "
        f"selection_legal; got {sorted(nl_categories)}"
    )
    assert set(bl_categories) == EXPECTED_LOSS_CATEGORIES, (
        "AC-0312: boundary_loss must report causality, table_anchor and "
        f"selection_legal; got {sorted(bl_categories)}"
    )
    for name, categories in (
        ("narrowing_loss", nl_categories),
        ("boundary_loss", bl_categories),
    ):
        for category in EXPECTED_LOSS_CATEGORIES:
            text = categories[category]
            assert isinstance(text, str) and text.strip(), (
                f"AC-0312: {name}.categories[{category!r}] must carry recorded content"
            )


# ── Auxiliary: extract_filing_excerpt ────────────────────────────────────────


def test_extract_filing_excerpt_finds_the_section() -> None:
    """``extract_filing_excerpt`` locates the section and returns up to the declared length."""
    # Build minimal HTML with the expected section marker.
    html = (
        "<html><body>"
        "<p>Some preamble.</p>"
        "<h2>Products and Services Performance</h2>"
        "<p>" + ("A " * 20000) + "</p>"
        "</body></html>"
    )
    excerpt = extract_filing_excerpt(html)
    assert excerpt.startswith("Products and Services Performance")
    assert len(excerpt) <= 30_000


def test_extract_filing_excerpt_raises_when_section_absent() -> None:
    """``extract_filing_excerpt`` raises ``ValueError`` for an HTML without the section."""
    with pytest.raises(ValueError, match="not found"):
        extract_filing_excerpt("<html><body>No matching section here.</body></html>")


# ── Auxiliary: parse_qa_observations ─────────────────────────────────────────


def test_parse_qa_observations_admits_valid_label_and_anchor() -> None:
    """Observations with a valid label and a resolving anchor are admitted."""
    excerpt = "Products gross margin expanded 560 bps year over year."
    raw = json_with_obs("margin_expansion", "gross margin expanded 560 bps")
    admitted, dropped = parse_qa_observations(raw, excerpt, SPIKE_LABELS)
    assert len(admitted) == 1
    assert len(dropped) == 0


def test_parse_qa_observations_drops_unknown_label() -> None:
    """Observations with labels outside the given set are dropped."""
    excerpt = "Net sales rose strongly this quarter."
    raw = json_with_obs("unknown_label_xyz", "Net sales rose strongly")
    admitted, dropped = parse_qa_observations(raw, excerpt, SPIKE_LABELS)
    assert len(admitted) == 0
    assert len(dropped) == 1
    assert "label not in admitted set" in dropped[0][1]


def test_parse_qa_observations_drops_non_resolving_anchor() -> None:
    """Observations whose anchor does not appear in the excerpt are dropped."""
    excerpt = "Net sales rose strongly this quarter."
    raw = json_with_obs("revenue_increase", "completely fabricated anchor text xyz123")
    admitted, dropped = parse_qa_observations(raw, excerpt, SPIKE_LABELS)
    assert len(admitted) == 0
    assert len(dropped) == 1
    assert "anchor not present" in dropped[0][1]


def test_parse_qa_observations_no_anchor_check_admits_all_valid_labels() -> None:
    """With ``check_anchors=False``, only the label check applies."""
    excerpt = "Net sales rose strongly this quarter."
    raw = json_with_obs("revenue_increase", "completely fabricated anchor text xyz123")
    admitted, dropped = parse_qa_observations(raw, excerpt, SPIKE_LABELS, check_anchors=False)
    assert len(admitted) == 1
    assert len(dropped) == 0


# ── AC-0312: fail-closed parser (malformed shapes) ──────────────────────────


@pytest.mark.parametrize(
    "raw, expected_drop_fragment",
    [
        # null observations → non-list, lands in dropped
        (
            json.dumps({"observations": None}),
            "not a list",
        ),
        # integer observations → non-list
        (
            json.dumps({"observations": 42}),
            "not a list",
        ),
        # string in the observations list → non-object observation
        (
            json.dumps({"observations": ["not a dict"]}),
            "not a JSON object",
        ),
        # integer in the observations list → non-object observation
        (
            json.dumps({"observations": [99]}),
            "not a JSON object",
        ),
        # list-valued label → non-string label (would be unhashable without guard)
        (
            json.dumps(
                {"observations": [{"label": ["a", "b"], "anchor": "text", "scalars": []}]}
            ),
            "not a string",
        ),
        # None label → non-string label
        (
            json.dumps({"observations": [{"label": None, "anchor": "text", "scalars": []}]}),
            "not a string",
        ),
        # dict anchor → non-string anchor
        (
            json.dumps(
                {
                    "observations": [
                        {"label": "revenue_increase", "anchor": {"nested": 1}, "scalars": []}
                    ]
                }
            ),
            "not a string",
        ),
    ],
    ids=[
        "observations_null",
        "observations_integer",
        "observation_string",
        "observation_integer",
        "label_list",
        "label_none",
        "anchor_dict",
    ],
)
def test_parse_qa_observations_fail_closed_on_malformed_shapes(
    raw: str, expected_drop_fragment: str
) -> None:
    """Malformed observation shapes land in ``dropped`` with a reason, never raise.

    AC-0312: all refusals are listed in ``dropped``; the function always returns
    ``(admitted, dropped)`` without raising on any JSON-shaped input.

    Break: remove the shape guards → the malformed cases raise ``TypeError``
    or ``AttributeError`` instead of landing in ``dropped`` → ``pytest.raises``
    would be needed here → test reds as written because no exception is caught.
    """
    excerpt = "some filing excerpt text for anchor resolution"
    admitted, dropped = parse_qa_observations(raw, excerpt, SPIKE_LABELS)
    assert isinstance(admitted, list), "must always return a list for admitted"
    assert isinstance(dropped, list), "must always return a list for dropped"
    assert len(dropped) >= 1, (
        f"malformed input must land in dropped; got admitted={admitted}, dropped={dropped}"
    )
    assert any(expected_drop_fragment in reason for _, reason in dropped), (
        f"expected {expected_drop_fragment!r} in a dropped reason; got {dropped!r}"
    )


# ── Hypothesis: parse_qa_observations never raises ───────────────────────────


_json_leaf = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text()
_json_values = st.recursive(
    _json_leaf,
    lambda children: (
        st.lists(children, max_size=5) | st.dictionaries(st.text(), children, max_size=5)
    ),
    max_leaves=10,
)


@given(observations=_json_values)
@settings(max_examples=200)
def test_parse_qa_observations_never_raises_on_arbitrary_json_observations(
    observations: object,
) -> None:
    """``parse_qa_observations`` returns ``(admitted, dropped)`` for any JSON observations.

    Break: remove the list or object guard → a non-list ``observations``
    raises ``TypeError``, or a non-dict entry raises ``AttributeError`` →
    hypothesis finds the falsifying example within a few tries → test reds.

    Does not establish: the field-level guards. The strategy draws dictionary
    keys from arbitrary text, so it almost never produces a ``label`` or
    ``anchor`` key, and removing the non-string-label or non-string-anchor
    guard leaves this property green. Those guards are pinned by the
    parametrized ``label_list``, ``label_none`` and ``anchor_dict`` cases of
    ``test_parse_qa_observations_fail_closed_on_malformed_shapes``.
    """
    raw = json.dumps({"observations": observations})
    excerpt = "some excerpt"
    result = parse_qa_observations(raw, excerpt, SPIKE_LABELS)
    assert isinstance(result, tuple) and len(result) == 2
    admitted, dropped = result
    assert isinstance(admitted, list)
    assert isinstance(dropped, list)


# ── AC-0313: derive_loss_from_qa_responses predicate wiring ─────────────────


def test_derive_loss_from_qa_responses_wires_narrow_pre_as_no_anchor_check() -> None:
    """``derive_loss_from_qa_responses`` uses ``check_anchors=False`` for ``narrow_pre_obs``.

    An observation whose anchor does not resolve in the excerpt is admitted
    into ``narrow_pre_obs`` (no anchor check) but dropped from ``narrow_post_obs``
    (anchor check enforced). The narrowing_loss count reflects this.

    Break: use ``check_anchors=True`` for ``narrow_pre_obs`` → the non-resolving
    anchor is dropped at that step → ``observations_narrow_pre == 0`` instead of
    ``1`` → the assertion fails → red.
    """
    excerpt = "revenue increased significantly this quarter"
    narrow_label = next(iter(sorted(LABEL_VOCABULARY)))  # first label alphabetically

    # wide_raw: one SPIKE_LABELS observation whose anchor resolves in the excerpt.
    wide_obs = {"label": "revenue_increase", "anchor": "revenue increased", "scalars": []}
    wide_raw = json.dumps({"observations": [wide_obs]})

    # narrow_raw: one narrow observation whose anchor does NOT resolve.
    # With check_anchors=False (correct) → admitted into narrow_pre_obs.
    # With check_anchors=True (swapped) → dropped at narrow_pre step.
    narrow_obs = {
        "label": narrow_label,
        "anchor": "completely absent anchor text xyz",
        "scalars": [],
    }
    narrow_raw = json.dumps({"observations": [narrow_obs]})

    loss = derive_loss_from_qa_responses(wide_raw, narrow_raw, excerpt)

    nl = loss["narrowing_loss"]
    bl = loss["boundary_loss"]

    # With correct predicates:
    # - narrow_pre_obs uses check_anchors=False → non-resolving anchor is NOT checked
    #   → the observation is admitted → narrow_pre count = 1
    # With swapped predicates (check_anchors=True for narrow_pre):
    # - non-resolving anchor is checked and fails → dropped → narrow_pre count = 0 → red
    assert nl["observations_narrow_pre"] == 1, (
        "narrow_pre_obs must use check_anchors=False; swapping to True drops the "
        "non-resolving anchor → this count becomes 0 → red"
    )

    # narrow_post_obs uses check_anchors=True → non-resolving anchor is dropped
    assert bl["observations_narrow_post"] == 0, (
        "narrow_post_obs must use check_anchors=True; the non-resolving anchor is dropped"
    )
    assert bl["dropped"] == 1, (
        "one observation passed the label check but failed the anchor check"
    )


# ── AC-0312: fixture digest verification ─────────────────────────────────────


def test_verify_fixture_digest_refuses_wrong_content() -> None:
    """``_verify_fixture_digest`` refuses bytes whose SHA-256 disagrees with the expected value.

    Break: record the constant ``FIXTURE_SHA256`` without computing from the
    bytes actually read (e.g. always pass without checking) → the refusal is
    never reached → a corrupted fixture is silently accepted → test reds
    because no ``ValueError`` is raised.
    """
    with pytest.raises(ValueError, match="fixture digest mismatch"):
        _verify_fixture_digest(b"wrong content bytes", FIXTURE_SHA256, "/path/to/fixture.html")


def test_verify_fixture_digest_passes_for_matching_content() -> None:
    """``_verify_fixture_digest`` does not raise when the digest matches."""
    import hashlib

    content = b"some fixture content"
    sha = hashlib.sha256(content).hexdigest()
    _verify_fixture_digest(content, sha, "/path/to/fixture.html")  # must not raise


# ── Helpers ──────────────────────────────────────────────────────────────────


def json_with_obs(label: str, anchor: str) -> str:
    """Return a minimal QA agent JSON string with one observation."""
    return json.dumps({"observations": [{"label": label, "anchor": anchor, "scalars": []}]})
