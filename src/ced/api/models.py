"""Request and response shapes for the run surface.

These mirror `contracts/openapi/runs.yaml` § components.schemas. AC-0009
asserts the served document agrees with that file, so the contract is the
authority and this module is what makes the application satisfy it.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ced.domain.events import EventEnvelope

#: The bound on both attribution fields. Both are self-asserted on an
#: unauthenticated surface and land in unconstrained `text` columns, so
#: unbounded they let one request persist an arbitrarily large string that
#: every later read of the run returns.
#:
#: **The same number is published in `contracts/openapi/runs.yaml`, and
#: AC-0009 does not compare the two.** This comment used to claim it did.
#: AC-0009's check reduces both documents to a route table — paths, methods,
#: `operationId`, parameters, `requestBodyRequired`, response statuses — and
#: excludes `components.schemas` deliberately, so raising this constant while
#: the YAML stayed at 256 would red nothing there. `tests/api` carries a
#: separate check that the two agree; that check, not AC-0009, is what stops
#: them drifting.
ATTRIBUTION_MAX_LENGTH = 256


class AnalysisRequest(BaseModel):
    """Optional analysis parameters — required when agent_role is first-published-analysis.

    ``extra="forbid"`` rejects any field not listed here with a 422, so a
    client cannot smuggle unrecognised keys past the boundary (AC-0411).
    Only the three canonical fields enter the persisted request object.
    """

    model_config = ConfigDict(extra="forbid")

    cik: str
    as_of_date: str
    snapshot_ref: str


class StartRunRequest(BaseModel):
    """What a client must supply to start a run."""

    principal: str = Field(min_length=1, max_length=ATTRIBUTION_MAX_LENGTH)
    agent_role: str = Field(min_length=1, max_length=ATTRIBUTION_MAX_LENGTH)
    analysis: AnalysisRequest | None = None


class StartedRun(BaseModel):
    run_id: UUID
    step_id: UUID
    seq: int


class Snapshot(BaseModel):
    """A run's state and the sequence number it is current to.

    A client that has been disconnected long enough to be uncertain of its
    cursor reads this, discards local state and resumes at `as_of_seq`.
    """

    run_id: UUID
    state: str
    as_of_seq: int


class Event(BaseModel):
    schema_version: int
    run_id: UUID
    seq: int
    type: str
    principal: str
    step_id: UUID | None = None
    agent_role: str | None = None
    payload_ref: str | None = None
    idempotency_key: str | None = None

    @classmethod
    def of(cls, envelope: EventEnvelope) -> Event:
        return cls(
            schema_version=envelope.schema_version,
            run_id=envelope.run_id,
            seq=envelope.seq,
            type=envelope.type,
            principal=envelope.principal,
            step_id=envelope.step_id,
            agent_role=envelope.agent_role,
            payload_ref=envelope.payload_ref,
            idempotency_key=envelope.idempotency_key,
        )


class EventPage(BaseModel):
    run_id: UUID
    events: list[Event]


class DecisionPair(BaseModel):
    """One call-id / decision pair in an approval request.

    ``call_id`` identifies the deferred tool call. ``granted`` is True for
    ``approval.granted`` and False for ``approval.rejected``.

    Both are bounded: ``call_id`` at ``ATTRIBUTION_MAX_LENGTH`` characters
    so one unauthenticated request cannot persist an arbitrarily long string
    in the event log (AC-0328). The bound at the route is what makes the
    decision set finite; AC-0330 validates whether the call ids in the
    request match the pending set in the suspension payload.
    """

    call_id: str = Field(min_length=1, max_length=ATTRIBUTION_MAX_LENGTH)
    granted: bool


class ApprovalDecisionRequest(BaseModel):
    """What the approver submits to release a suspended step.

    ``suspension_seq`` identifies which suspension is being answered — the
    seq of the committed ``step.suspended`` event (AC-0334). The decision
    path refuses a seq that is not the step's latest suspension.

    ``decisions`` carries one pair per pending call id. An empty list is
    refused (one unauthenticated request would consume the suspension and
    kill the run via AC-0330). The list is bounded at
    ``ATTRIBUTION_MAX_LENGTH`` entries — the same seam as the per-call-id
    length — so the number of rows one request appends is finite (AC-0328).

    ``principal`` is the approver's self-asserted identity. Unauthenticated
    in Phase 1; recorded for inspectability (AC-0303, AC-0328, AC-0329).
    """

    suspension_seq: int = Field(ge=1)
    decisions: list[DecisionPair] = Field(
        min_length=1,
        max_length=ATTRIBUTION_MAX_LENGTH,
    )
    principal: str = Field(min_length=1, max_length=ATTRIBUTION_MAX_LENGTH)


class DecisionResult(BaseModel):
    """The approval route's response: the seq of the last committed event."""

    last_seq: int


# ---------------------------------------------------------------------------
# Analysis artifact response models (AC-0414, AC-0415)
#
# These mirror the JSON produced by ``ced.domain.diligence.canonical_bytes``.
# Decimal-valued domain fields are serialised as strings; all fields are
# required (no defaults). ``extra="forbid"`` rejects unrecognised keys,
# matching the domain's own fail-closed posture.
#
# These models drive the ``response_model`` on ``GET /runs/{run_id}/analysis``
# and therefore the 200 schema in the generated OpenAPI document.  The route
# returns the raw canonical bytes as a ``Response`` so byte-identity with the
# stored artifact is preserved; FastAPI does not re-serialise a ``Response``
# object even when ``response_model`` is set.
# ---------------------------------------------------------------------------


class Period(BaseModel):
    """Duration context period (start and end date strings)."""

    model_config = ConfigDict(extra="forbid")

    start_date: str
    end_date: str


class Claim(BaseModel):
    """One factual claim in the analysis memo."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    text: str
    evidence_refs: list[str]


class Memo(BaseModel):
    """The fixed-format research memo."""

    model_config = ConfigDict(extra="forbid")

    title: str
    claims: list[Claim]


class EvidenceSource(BaseModel):
    """One archived SEC source referenced by the evidence manifest."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    archived_url: str
    digest: str
    source_ref: str


class FilingFact(BaseModel):
    """One validated XBRL numeric fact extracted from the filing.

    ``decimal_value`` is stored as a string because the canonical JSON
    serialises ``Decimal`` via ``str()``; accepting a float here would risk
    precision loss on round-trip.
    """

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    concept: str
    context: str
    period: Period
    unit: str
    scale: int
    decimal_value: str
    source_id: str
    source_fragment: str


class Calculation(BaseModel):
    """Lineage record for one deterministic arithmetic claim.

    ``numerator``, ``denominator``, and ``value`` are strings because the
    canonical JSON serialises ``Decimal`` fields via ``str()``.
    """

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    operation: str
    input_fact_refs: list[str]
    formula: str
    numerator: str
    denominator: str
    rounding_rule: str
    output_scale: int
    unit: str
    value: str


class ClaimLink(BaseModel):
    """One entry linking a claim id to its calculation."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    calculation_ref: str


class EvidenceManifest(BaseModel):
    """Machine-readable evidence manifest for one analysis artifact."""

    model_config = ConfigDict(extra="forbid")

    sources: list[EvidenceSource]
    facts: list[FilingFact]
    calculations: list[Calculation]
    claim_links: list[ClaimLink]


class PublishedAnalysis(BaseModel):
    """Complete deterministic analysis artifact returned by GET /runs/{run_id}/analysis.

    Mirrors the structure produced by ``ced.domain.diligence.canonical_bytes``.
    Execution-varying fields (run id, retrieval time) are excluded so identical
    pinned inputs produce identical bytes (AC-0410).  The response omits
    initiating-principal and SEC-contact values (AC-0415).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    cik: str
    as_of_date: str
    source_url: str
    filing_digest: str
    memo: Memo
    evidence_manifest: EvidenceManifest
