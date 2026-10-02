"""Construction tests for the ced-evidence command: AC-0306, AC-0307, AC-0308,
AC-0309, AC-0310, and AC-0311.

Every test here is **offline** (no substrate, no provider). They target the
pure-computation and stubbed-client seams in ``ced.worker.evidence`` and
``ced.adapters.bedrock.quota``, plus two committed files — the measurement
record and ``deploy/compose.yaml`` — that AC-0306 and AC-0307 compare against
each other. Goal-based provider witnesses (the real cancellation observation
and the real quota read) are recorded in the verification ledger when the
operator has authenticated.

Mutation proofs are recorded in
``docs/specs/walking-skeleton-evidence/notes/verification-ledger.md``.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest
import yaml

from ced.adapters.bedrock.quota import (
    BEDROCK_SERVICE_CODE,
    BEDROCK_TPM_QUOTA_CODE,
    read_quota_record,
)
from ced.worker.evidence import (
    PLATFORM_NOTE,
    SAMPLE_FLOOR,
    SAMPLE_SCOPE,
    STEP_DEADLINE_ENV,
    StreamNotInFlightError,
    _write_record,
    build_step_duration_record,
    classify_cancellation_outcome,
    compute_step_duration_metrics,
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Path to the committed measurement record. Written by ``ced-evidence
#: step-duration --out <path>`` and read by AC-0306.
_MEASUREMENTS_PATH = (
    _REPO_ROOT / "docs" / "specs" / "walking-skeleton-evidence" / "notes" / "measurements.json"
)

#: The deployed configuration AC-0306 compares the record against. This is the
#: committed file, not a running container: a container recreated from an older
#: file would still report the old value, and the gate's claim is about what
#: this repository deploys, not about what happens to be running.
_COMPOSE_PATH = _REPO_ROOT / "deploy" / "compose.yaml"


def _read_measurements() -> dict[str, Any]:
    """Return the committed measurement record, failing when it is absent.

    **This fails rather than skips.** A gate whose input can vanish without the
    gate noticing is not a gate: renaming ``measurements.json`` would otherwise
    turn AC-0306 green by deleting its evidence.
    """
    assert _MEASUREMENTS_PATH.exists(), (
        f"{_MEASUREMENTS_PATH} is missing. AC-0306's evidence cannot be absent and "
        "the criterion still pass; run 'ced-evidence generate --n 30' then "
        f"'{STEP_DEADLINE_ENV}=<deployed value> ced-evidence step-duration --out "
        f"{_MEASUREMENTS_PATH.name}' against the local substrate to restore it."
    )
    loaded = json.loads(_MEASUREMENTS_PATH.read_text())
    assert isinstance(loaded, dict), f"{_MEASUREMENTS_PATH.name} must hold a JSON object"
    return loaded


def _deployed_step_deadlines() -> dict[str, float]:
    """Return every service in ``deploy/compose.yaml`` that sets the deadline.

    Parsed as YAML rather than matched by line, so a value moved, re-indented,
    or inherited through the ``<<`` merge key is still read.
    """
    compose = yaml.safe_load(_COMPOSE_PATH.read_text())
    deadlines: dict[str, float] = {}
    for service, body in (compose.get("services") or {}).items():
        environment = (body or {}).get("environment") or {}
        raw = environment.get(STEP_DEADLINE_ENV)
        if raw is not None:
            deadlines[service] = float(raw)
    return deadlines


# ── _write_record: atomic write and refusal behaviour ───────────────────────


def test_write_record_creates_file_when_absent(tmp_path: pathlib.Path) -> None:
    """``_write_record`` creates the record when the file is absent.

    Break: restore the silent fallback (``OSError`` → empty record) → this
    test still passes (absent file is not an error either way), but the corrupt-
    file and JSON-array tests below red.
    """
    out_path = tmp_path / "new.json"
    _write_record(str(out_path), {"key": "value"})
    loaded = json.loads(out_path.read_text())
    assert loaded == {"key": "value"}


def test_write_record_merges_into_existing_object(tmp_path: pathlib.Path) -> None:
    """``_write_record`` merges payload into an existing record, preserving other keys.

    Break: restore the silent fallback → the corrupt-file test below red.
    """
    out_path = tmp_path / "record.json"
    original = {"existing": "preserved", "will_be_overwritten": "old"}
    out_path.write_text(json.dumps(original) + "\n")

    _write_record(str(out_path), {"new_key": "added", "will_be_overwritten": "new"})
    loaded = json.loads(out_path.read_text())

    assert loaded["existing"] == "preserved", "pre-existing keys must survive the merge"
    assert loaded["new_key"] == "added"
    assert loaded["will_be_overwritten"] == "new", (
        "payload keys overwrite matching existing keys"
    )


def test_write_record_refuses_corrupt_file_and_leaves_it_untouched(
    tmp_path: pathlib.Path,
) -> None:
    """``_write_record`` refuses a present but unreadable file and leaves it intact.

    Break: restore the silent fallback (catching ``JSONDecodeError`` → empty
    record) → the function overwrites the corrupt file rather than raising →
    the assertion that the file is unchanged reds, and the ``pytest.raises``
    context fails because no ``ValueError`` is raised.
    """
    out_path = tmp_path / "corrupt.json"
    corrupt_bytes = b"this is not JSON {"
    out_path.write_bytes(corrupt_bytes)

    with pytest.raises(ValueError, match=str(out_path)):
        _write_record(str(out_path), {"key": "value"})

    assert out_path.read_bytes() == corrupt_bytes, (
        "corrupt file must be byte-for-byte untouched after refusal"
    )


def test_write_record_refuses_json_array_and_leaves_it_untouched(
    tmp_path: pathlib.Path,
) -> None:
    """``_write_record`` refuses a present JSON array (not an object) and leaves it intact.

    Break: restore the silent fallback (non-dict JSON → empty record) → the
    function silently overwrites the array with just the payload → the byte
    comparison reds, and the ``pytest.raises`` context fails.
    """
    out_path = tmp_path / "array.json"
    array_bytes = (json.dumps([1, 2, 3]) + "\n").encode()
    out_path.write_bytes(array_bytes)

    with pytest.raises(ValueError, match=str(out_path)):
        _write_record(str(out_path), {"key": "value"})

    assert out_path.read_bytes() == array_bytes, (
        "JSON array file must be byte-for-byte untouched after refusal"
    )


def test_write_record_atomic_write_protects_original_on_failure(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A write interrupted while serialising leaves the original byte-for-byte intact.

    ``json.dumps`` is patched to raise, standing in for any failure between
    starting the write and finishing it. The merged record is serialised into
    a temporary file beside the original, so the original is never opened for
    writing and survives. No temporary file is left behind.

    Break: write directly with ``open(out_path, "w")`` instead of the temporary
    file and ``os.replace`` → the open truncates the original before the
    failure fires → ``out_path.read_bytes() != original_bytes`` → red.
    """
    import ced.worker.evidence as _ev

    out_path = tmp_path / "record.json"
    out_path.write_text(json.dumps({"existing": "value"}) + "\n")
    original_bytes = out_path.read_bytes()

    def _failing_dumps(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("simulated interrupted write")

    monkeypatch.setattr(_ev.json, "dumps", _failing_dumps)

    with pytest.raises(RuntimeError, match="simulated interrupted write"):
        _write_record(str(out_path), {"new_key": "new_value"})

    assert out_path.read_bytes() == original_bytes, (
        "original must be byte-for-byte intact after an interrupted write"
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["record.json"]


# ── Committed record: p99 × 3 relation and sample floor ─────────────────────


def test_committed_record_p99_relation_and_sample_floor() -> None:
    """The committed record's page_threshold equals p99 × 3 and sample_size >= SAMPLE_FLOOR.

    AC-0307 (sample floor) and AC-0308 (same-sample derivation). Both are
    checked against the committed ``measurements.json`` so a hand-edit that
    breaks either invariant reds here without re-running the measurement command.

    Breaks (each hand-edit must be restored exactly after verification):
        Edit ``page_threshold_seconds`` from 0.262293 to 0.9 →
        ``assert_almost_equal`` fails → red.

        Edit ``sample_size`` from 30 to 5 →
        ``assert sample_size >= SAMPLE_FLOOR`` fails → red.
    """
    measurements = _read_measurements()
    step = measurements["step_duration"]
    p99 = float(step["p99_seconds"])
    page_threshold = float(step["page_threshold_seconds"])
    sample_size = int(step["sample_size"])

    # page_threshold must equal p99 × 3, to the record's own rounding.
    # round() at 6 decimal places matches the precision of the committed values
    # (0.087431 × 3 = 0.262293).
    assert round(page_threshold, 6) == round(p99 * 3, 6), (
        f"page_threshold_seconds {page_threshold!r} must equal p99_seconds {p99!r} × 3; "
        "a hand-edit breaking this relation reds here"
    )

    assert sample_size >= SAMPLE_FLOOR, (
        f"sample_size {sample_size} must be >= SAMPLE_FLOOR {SAMPLE_FLOOR}; "
        "editing sample_size below the floor reds here"
    )


# ── AC-0307: sample floor ────────────────────────────────────────────────────


def test_step_duration_measurement_refuses_an_undersized_sample() -> None:
    """``compute_step_duration_metrics`` raises when the sample is below SAMPLE_FLOOR.

    AC-0307: the command refuses a smaller sample rather than extrapolating.

    The sample sizes are **fixed** in the test, not computed from ``SAMPLE_FLOOR``,
    so that lowering the floor constant in the implementation makes the test red.

    Mutation that must red this test (proved in the ledger):
        Lower ``SAMPLE_FLOOR`` in ``evidence.py`` to 29.
        ``compute_step_duration_metrics([0.1] * 29)`` no longer raises, so
        the ``pytest.raises`` context exits without a match → test reds.
    """
    # Fixed at 29 — one below the required floor of 30.
    with pytest.raises(ValueError, match="sample too small"):
        compute_step_duration_metrics([0.1] * 29)

    # Exactly 30 is sufficient (the floor itself).
    result = compute_step_duration_metrics([0.1] * 30)
    assert result["sample_size"] == 30


# ── AC-0308: same-sample derivation ─────────────────────────────────────────


def test_thresholds_share_one_sample() -> None:
    """``page_threshold`` equals ``p99 × 3``, both from the same sorted sample.

    AC-0308: the page threshold is derived from the same p99, not from an
    independent percentile or a differently filtered list.

    Mutation that must red this test (proved in the ledger):
        In ``compute_step_duration_metrics``, compute ``page_threshold`` from
        a different sorted list, e.g. ``sorted(durations[:-1])``, so
        ``page_threshold != p99 * 3`` for this sample. The assertion
        ``result["page_threshold_seconds"] == result["p99_seconds"] * 3``
        then fails.
    """
    # 31 samples: [1.0, 2.0, ..., 31.0].
    # nearest-rank p99: ceil(0.99 × 31) − 1 = ceil(30.69) − 1 = 31 − 1 = 30
    # sorted[30] = 31.0 → p99 = 31.0, page_threshold = 93.0
    durations = [float(i) for i in range(1, 32)]  # 31 values
    result = compute_step_duration_metrics(durations)

    p99 = result["p99_seconds"]
    page_threshold = result["page_threshold_seconds"]

    # Both derived from the same p99.
    assert page_threshold == p99 * 3, (
        f"page_threshold {page_threshold!r} must equal p99 {p99!r} × 3; "
        "a mutation using a different sample would produce a detectable mismatch"
    )
    # Verify the p99 value itself (nearest-rank).
    assert p99 == 31.0, f"expected nearest-rank p99 = 31.0, got {p99!r}"
    assert page_threshold == 93.0, f"expected page_threshold = 93.0, got {page_threshold!r}"


# ── AC-0306: deadline ordering ───────────────────────────────────────────────


def test_deployed_deadline_matches_the_record_and_sits_between_measured_limits() -> None:
    """The deployed deadline equals the recorded one and lies inside the bounds.

    AC-0306 reads three numbers from **two** sources: p99 and the page
    threshold from the committed ``measurements.json``, and the deadline from
    both of them — the record, and ``deploy/compose.yaml``, which is what this
    repository deploys. Reading the deadline only from the record would let
    the deployed value drift with the gate still green, because the record
    would then be compared against itself.

    Every service that sets ``CED_STEP_DEADLINE_SECONDS`` is read, so changing
    the value on **either** worker service reds this test — one changed service
    disagrees with the other, and two changed services disagree with the
    record.

    Mutations that must red this test (proved in the ledger):
        Change ``CED_STEP_DEADLINE_SECONDS`` on ``worker-a`` in
        ``deploy/compose.yaml`` → the two services disagree.
        Change it on both services → both disagree with the record.
        Rename ``measurements.json`` → ``_read_measurements`` fails rather
        than skipping.
        Set ``configured_step_deadline_seconds`` to exactly
        ``step_duration.p99_seconds`` → ``p99 < p99`` is False.
    """
    measurements = _read_measurements()
    p99 = float(measurements["step_duration"]["p99_seconds"])
    page_threshold = float(measurements["step_duration"]["page_threshold_seconds"])
    recorded_deadline = float(measurements["configured_step_deadline_seconds"])

    deployed = _deployed_step_deadlines()
    assert deployed, (
        f"no service in {_COMPOSE_PATH.name} sets {STEP_DEADLINE_ENV}; "
        "the recorded deadline would then describe nothing deployed"
    )
    assert set(deployed.values()) == {recorded_deadline}, (
        f"deployed {STEP_DEADLINE_ENV} {deployed!r} must agree with the recorded "
        f"configured_step_deadline_seconds {recorded_deadline!r}; re-run "
        f"'{STEP_DEADLINE_ENV}=<deployed value> ced-evidence step-duration --out "
        f"{_MEASUREMENTS_PATH.name}' after changing the deployed value"
    )

    assert p99 < recorded_deadline < page_threshold, (
        f"ordering violated: p99={p99:.6g} < step_deadline={recorded_deadline:.6g} "
        f"< page_threshold={page_threshold:.6g} must hold; "
        f"set {STEP_DEADLINE_ENV} to a value strictly between the two bounds"
    )


# ── AC-0307: the record is the command's output ──────────────────────────────


def test_the_record_carries_only_fields_the_command_emits() -> None:
    """Every field in ``measurements.json`` has a subcommand that produces it.

    AC-0307: the record is the command's actual output, platform string
    included. Each top-level key is written by one subcommand, and ``--out``
    merges rather than replaces, so the three keys compose without one
    subcommand's write deleting another's.

    **One field is operator-recorded, and this check does not claim
    otherwise.** ``quota.measured`` carries ``2026-09-29``, the date the quota
    read was run; the ``measured`` stamp was added to the command afterwards
    and the read has not been re-run, so that date is one a person wrote down.
    ``cancellation.measured`` was in the same position until the owner-directed
    re-run of 2026-10-01, and is now the command's own stamp. That provenance
    is recorded in ``docs/architecture/pydantic-ai-worker-runtime/operations.md``
    § Cancellation measurement and in the verification ledger — not in
    ``measurements.json`` itself, which carries only fields a subcommand emits.
    This check asserts the key set and the step-duration fields; it asserts
    nothing about the provenance of the quota date.

    The ``step_duration`` key set is compared against
    ``build_step_duration_record`` itself, and the two prose fields against the
    constants the command emits, so hand-writing either one reds here without
    the substrate.

    Mutation that must red this test (proved in the ledger):
        Hand-edit ``step_duration.platform`` or ``platform_note`` in
        ``measurements.json``; re-running the command restores it.
    """
    measurements = _read_measurements()

    assert set(measurements) == {
        "step_duration",
        "configured_step_deadline_seconds",
        "configured_step_deadline_source",
        "cancellation",
        "quota",
    }, f"unexpected top-level keys: {sorted(measurements)}"

    # 30 values: enough to clear the sample floor, so the builder returns a
    # record whose key set can be compared against the committed one.
    emitted = build_step_duration_record([0.1] * 30)
    assert set(measurements["step_duration"]) == set(emitted), (
        "recorded step_duration fields must be exactly what "
        "build_step_duration_record emits; "
        f"recorded {sorted(measurements['step_duration'])}, "
        f"emitted {sorted(emitted)}"
    )
    assert measurements["step_duration"]["method"] == emitted["method"]
    assert measurements["step_duration"]["sample_scope"] == SAMPLE_SCOPE, (
        "the sample's scoping predicate must be the one the command emits, not prose"
    )
    assert measurements["step_duration"]["platform_note"] == PLATFORM_NOTE, (
        "the platform note must be the one the command emits, not prose"
    )
    assert measurements["step_duration"]["platform"].endswith(
        "local Docker Compose substrate"
    ), "the platform string is the command's, built from the platform module"

    assert set(measurements["cancellation"]) == {
        "outcome",
        "latency_seconds",
        "region",
        "model_id",
        "method",
        "in_flight_at_close",
        "measured",
    }, f"unexpected cancellation fields: {sorted(measurements['cancellation'])}"

    assert set(measurements["quota"]) == {
        "region",
        "service_code",
        "quota_code",
        "quota_name",
        "value",
        "measured",
    }, f"unexpected quota fields: {sorted(measurements['quota'])}"


# ── AC-0309 / AC-0310: cancellation classification ──────────────────────────


def test_cancellation_outcome_comes_from_the_reader_completing() -> None:
    """``classify_cancellation_outcome`` reads one local property and nothing else.

    The property the amended AC-0310 names is **this process's reader
    completing after the response body is closed** — not the stream
    connection closing, which this measurement never observes. The
    classification is ``"terminated"`` when the reader completes inside the
    window and ``"abandoned"`` when it does not, and AC-0309 measures latency
    to that same endpoint.

    AC-0310 also forbids an operator-supplied outcome: the function has no
    ``outcome`` parameter, and the body must be closed before the observation
    is taken on both branches.

    Three mutations are proved in the ledger, and all must red this test:

    Mutation A — ignore the reader observation:
        Replace ``return "terminated" if observed_closed else "abandoned"``
        with ``return "terminated"``. The ``abandoned`` case reds, because the
        observation it supplies stops changing the answer.

    Mutation B — accept an operator-supplied outcome:
        Add an ``outcome: str | None = None`` parameter returned when
        supplied. Calling with the keyword raises ``TypeError`` today, so the
        third case below reds once the parameter exists.

    Mutation C — swap the call order (observe before close):
        Move ``observe_closure`` before ``close_stream``. The
        ``call_log.index("close") < call_log.index("observe")`` assertion
        fails because "observe" now appears before "close" in the log.
    """
    call_log: list[str] = []

    def close_body() -> bool:
        call_log.append("close")
        return True  # the reader was still running when the body was closed

    # Case 1: the reader completes inside the window → terminated.
    def observe_terminated(timeout: float) -> bool:
        call_log.append("observe")
        return True  # reader completes immediately

    terminated_result = classify_cancellation_outcome(
        close_stream=close_body,
        observe_closure=observe_terminated,
        window_seconds=0.1,
    )
    assert terminated_result == "terminated", (
        f"a reader that completes inside the window must produce 'terminated', "
        f"got {terminated_result!r}"
    )
    assert call_log.index("close") < call_log.index("observe"), (
        "close_stream must be called before observe_closure on the terminated path; "
        "swapping the two calls makes 'observe' appear first → red"
    )

    call_log.clear()

    # Case 2: the reader does not complete inside the window → abandoned.
    def observe_abandoned(timeout: float) -> bool:
        call_log.append("observe")
        return False  # reader never completes in the window

    abandoned_result = classify_cancellation_outcome(
        close_stream=close_body,
        observe_closure=observe_abandoned,
        window_seconds=0.1,
    )
    assert abandoned_result == "abandoned", (
        f"a reader that does not complete inside the window must produce "
        f"'abandoned', got {abandoned_result!r}"
    )
    assert call_log.index("close") < call_log.index("observe"), (
        "close_stream must be called before observe_closure on the abandoned path; "
        "swapping the two calls makes 'observe' appear first → red"
    )

    # Case 3: there is no seam for an operator to supply the outcome at all.
    with pytest.raises(TypeError):
        classify_cancellation_outcome(  # type: ignore[call-arg]
            close_stream=close_body,
            observe_closure=lambda t: False,
            window_seconds=0.1,
            outcome="terminated",
        )


def test_a_stream_that_was_not_in_flight_is_refused() -> None:
    """A reader already finished at the close is refused, never ``terminated``.

    AC-0309 measures cancellation "on an in-flight model stream". If the
    reader had already drained the stream before the close, the stream ended
    on its own and the close cancelled nothing — but the reader is still
    observed as finished, so without this check the sample would be recorded
    as ``terminated``. That is exactly what an earlier revision of the command
    could do, requesting a one-word reply and starting the reader before the
    close.

    The reader is still joined on refusal, so local resources are released.

    Mutation that must red this test (proved in the ledger):
        Drop the liveness check — ignore ``close_stream()``'s return value.
        The sample is then classified ``terminated`` instead of refused.
    """
    observed: list[float] = []

    def close_after_reader_finished() -> bool:
        return False  # the reader had already finished before the close

    def observe(timeout: float) -> bool:
        observed.append(timeout)
        return True  # a finished reader is, trivially, observed as finished

    with pytest.raises(StreamNotInFlightError):
        classify_cancellation_outcome(
            close_stream=close_after_reader_finished,
            observe_closure=observe,
            window_seconds=0.1,
        )
    assert observed, "the reader must still be joined on refusal, to release resources"


# ── AC-0311: quota serialization ─────────────────────────────────────────────


class _StubQuotasClient:
    """A minimal Service Quotas client stub for the offline construction test.

    ``meta.region_name`` is set to a non-default region so a mutation that
    substitutes a configured constant (e.g. 'us-east-1') produces a
    detectable mismatch.
    """

    class meta:
        region_name: str = "us-stub-2"

    def get_service_quota(self, *, ServiceCode: str, QuotaCode: str) -> dict[str, Any]:
        return {
            "Quota": {
                "QuotaName": "Stub TPM quota",
                "Value": 99999.0,
                "QuotaCode": QuotaCode,
                "ServiceCode": ServiceCode,
            }
        }


def test_quota_record_uses_the_resolved_client_region() -> None:
    """``read_quota_record`` takes region from the resolved client, not a constant.

    AC-0311: the record must carry region, quota identity (service_code and
    quota_code), and value. Credential and account metadata must be absent.

    Two mutations are proved in the ledger:

    Mutation A — substitute a configured region (e.g. hard-code 'us-east-1'):
        The stub client reports 'us-stub-2'; the record would report 'us-east-1'
        → ``assert record["region"] == "us-stub-2"`` reds.

    Mutation B — omit the quota identity (remove service_code or quota_code):
        ``assert record["service_code"] == BEDROCK_SERVICE_CODE`` reds.
    """
    client = _StubQuotasClient()
    record = read_quota_record(client)

    # Region from the resolved client, not a constant.
    assert record["region"] == "us-stub-2", (
        f"region must come from client.meta.region_name ('us-stub-2'), "
        f"got {record.get('region')!r}"
    )

    # Quota identity must be recorded.
    assert record["service_code"] == BEDROCK_SERVICE_CODE, (
        f"service_code must be {BEDROCK_SERVICE_CODE!r}, got {record.get('service_code')!r}"
    )
    assert record["quota_code"] == BEDROCK_TPM_QUOTA_CODE, (
        f"quota_code must be {BEDROCK_TPM_QUOTA_CODE!r}, got {record.get('quota_code')!r}"
    )

    # Value must be present.
    assert "value" in record, "value must be recorded"
    assert record["quota_name"] == "Stub TPM quota"

    # Credential and account metadata must be absent.
    forbidden = {"access_key", "secret_key", "session_token", "account_id", "arn"}
    assert not forbidden.intersection(record.keys()), (
        f"credential/account keys must not appear in the record; "
        f"found {forbidden.intersection(record.keys())}"
    )
