"""ced-evidence: operational evidence commands for Phase 1.

Subcommands
-----------
generate
    Generate N completed steps using ``stub:counting`` and TestModel against
    the local substrate. Produces real ``step.started`` / ``step.completed``
    events with true ``occurred_at`` timestamps. Requires the substrate.

step-duration
    Pair ``step.started`` and ``step.completed`` events from the event log,
    compute p99 (nearest-rank) and the page threshold (p99 × 3 from the same
    sample), and emit JSON. Refuses a sample smaller than SAMPLE_FLOOR.
    Also emits the deployed ``CED_STEP_DEADLINE_SECONDS`` it was run with, so
    AC-0306's check has a recorded value to compare against the deployed one.
    Requires the substrate.

cancellation
    Open a real Bedrock response stream, close its response body, and observe
    whether this process's reader completes within the observation window.
    Emits ``terminated`` when the reader completes, ``abandoned`` otherwise.
    Requires live AWS credentials and provider access.

quota
    Read the Bedrock tokens-per-minute quota from Service Quotas. Region comes
    from the resolved client, not a configured constant. Requires live AWS
    credentials and Service Quotas access.

Design notes
------------
- ``compute_step_duration_metrics`` is a **pure function**: it takes a list
  of durations, refuses an undersized sample, and returns p99 and the page
  threshold derived from the same sorted list. Tests target this function
  directly without a database.
- ``classify_cancellation_outcome`` is a **pure observer**: it takes two
  callables (close the response body, observe this process's reader
  completing) and classifies from the observation alone. No operator-supplied
  outcome parameter exists.
- ``read_quota_record`` (in ``ced.adapters.bedrock.quota``) takes the
  resolved client and takes Region from ``client.meta.region_name``.

Every field the committed record
``docs/specs/walking-skeleton-evidence/notes/measurements.json`` carries is
emitted by one of these subcommands, and ``--out`` merges that subcommand's
own top-level keys into an existing record rather than replacing the file, so
three independently-run subcommands compose one record without any field
being written by hand. AC-0307.

AC-0306, AC-0307, AC-0308, AC-0309, AC-0310, AC-0311.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import platform
import sys
import tempfile
from collections.abc import Callable, Mapping
from typing import Any

__all__ = [
    "PLATFORM_NOTE",
    "SAMPLE_FLOOR",
    "SAMPLE_SCOPE",
    "STEP_DEADLINE_ENV",
    "build_step_duration_record",
    "classify_cancellation_outcome",
    "compute_step_duration_metrics",
    "query_step_durations",
    "run",
]

#: AC-0307: the minimum number of completed real steps required for measurement.
#: The command refuses a smaller sample rather than extrapolating from it.
SAMPLE_FLOOR = 30

#: Pool class used by the generate subcommand. Nothing else polls this class,
#: so generated steps are isolated from the running substrate workers.
_GENERATE_POOL_CLASS = "ced-evidence-measure"
_GENERATE_PRINCIPAL = "ced-evidence"
_GENERATE_ROLE = "ced-evidence-measurement"
_GENERATE_WORKER_ID = "ced-evidence-generator"

#: The default observation window for cancellation in seconds.
_CANCELLATION_WINDOW_SECONDS = 30.0

#: The deployed step deadline the step-duration subcommand records beside the
#: measured bounds. The command reads it from its own environment and refuses
#: to measure without it, so the recorded value names a configuration that was
#: actually present rather than one someone typed into the record. AC-0306's
#: check compares it against what `deploy/compose.yaml` sets.
STEP_DEADLINE_ENV = "CED_STEP_DEADLINE_SECONDS"

#: What the sample is, stated beside the value it produces. This is the
#: predicate ``query_step_durations`` implements: it is deliberately
#: unscoped, so the sample is whatever completed steps the event log held
#: when the command ran — including steps left by other work against the
#: same database. Changing the query without changing this string makes the
#: record describe a sample it does not have.
SAMPLE_SCOPE = (
    "Every step.started/step.completed pair in the event log, joined on step_id, "
    "with no role, pool-class, principal or time filter. The sample is whatever "
    "the event log held at the moment of measurement, so it is reproducible only "
    "against that same event-log state; a step a later suite completes enters a "
    "later sample."
)

#: Why the measured numbers are smaller than a deployed fleet's would be.
PLATFORM_NOTE = (
    "Local Docker Compose substrate driven by ced-evidence generate with "
    "stub:counting (TestModel, no provider call). The executor writes "
    "step.started and step.completed through the full executor path with "
    "authentic occurred_at timestamps, so the durations measure executor "
    "overhead and database round-trips only: inference time and provider "
    "network latency are absent. This is the Phase 1 measurement under the "
    "local-container substitution the spec Assumptions accept; AC-0314 names "
    "the resulting limits."
)


# ── Pure computation layer ───────────────────────────────────────────────────


def compute_step_duration_metrics(durations: list[float]) -> dict[str, object]:
    """Compute p99 and page threshold from a list of step durations.

    Method: nearest-rank percentile. Given n sorted durations:
        p99 index = ceil(0.99 × n) − 1  (0-indexed, so the 99th percentile)
        page_threshold = p99 × 3

    Both values derive from the same sorted sample. The page threshold is
    computed from ``p99 * 3``, not from an independent percentile, so a
    mutation that recomputes either from a different list produces a detectable
    disagreement (``page_threshold != p99 * 3``).

    Raises ``ValueError`` when ``len(durations) < SAMPLE_FLOOR``. The floor
    is defined at module level so a test can reference and mutate it.

    AC-0307: refuses undersized sample.
    AC-0308: page threshold from the same sample as p99.
    """
    n = len(durations)
    if n < SAMPLE_FLOOR:
        raise ValueError(
            f"sample too small: {n} completed step(s), need at least {SAMPLE_FLOOR}. "
            f"Run more steps and retry."
        )
    sorted_d = sorted(durations)
    idx = math.ceil(0.99 * n) - 1
    p99 = sorted_d[idx]
    # Derived from the same p99, not from a separate sample or percentile.
    page_threshold = p99 * 3
    return {
        "p99_seconds": p99,
        "page_threshold_seconds": page_threshold,
        "sample_size": n,
        "method": "nearest-rank p99, floor 30",
        "platform": (
            f"{platform.system()} ({platform.machine()}), local Docker Compose substrate"
        ),
    }


def build_step_duration_record(durations: list[float]) -> dict[str, object]:
    """Build the committed ``step_duration`` block from a list of durations.

    Adds the two statements that must travel with the value — what the sample
    is scoped to (``sample_scope``) and why the platform makes it small
    (``platform_note``) — to the computed metrics. The command writes exactly
    this block, so nothing in the record's ``step_duration`` key is authored
    by hand.
    """
    return {
        **compute_step_duration_metrics(durations),
        "sample_scope": SAMPLE_SCOPE,
        "platform_note": PLATFORM_NOTE,
        "measured": measured_on(),
    }


def measured_on() -> str:
    """Today's UTC date as ``YYYY-MM-DD``, stamped into each emitted record.

    The record carries when it was taken because a measurement whose date is
    unknown cannot be told from one that was never retaken.
    """
    return datetime.datetime.now(datetime.UTC).date().isoformat()


def _write_record(out_path: str, payload: Mapping[str, object]) -> None:
    """Merge ``payload``'s top-level keys into the JSON record at ``out_path``.

    Each subcommand owns its own top-level keys — ``step-duration`` writes
    three of the record's five — and the committed record is the union of
    three independently-run subcommands. A replacing write would make
    the operator paste the other two keys back by hand, which is exactly the
    hand-authorship AC-0307 forbids.

    Starts from an empty record only when the file is absent. A present file
    that is unreadable or that holds anything other than a JSON object is
    refused with a ``ValueError`` that names the path and the reason; the
    original bytes are left byte-for-byte untouched. The merged record is
    written to a temporary file in the same directory then placed atomically
    with ``os.replace``, so an interrupted write leaves the original intact.

    AC-0307.
    """
    existing: dict[str, object] = {}
    if os.path.exists(out_path):
        try:
            with open(out_path) as f:
                loaded = json.load(f)
        except OSError as exc:
            raise ValueError(f"{out_path}: cannot read: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"{out_path}: not valid JSON: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"{out_path}: expected a JSON object, got {type(loaded).__name__}")
        existing = loaded

    existing.update(payload)
    dir_path = os.path.dirname(os.path.abspath(out_path))
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(existing, indent=2) + "\n")
        os.replace(tmp_path, out_path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _resolve_deployed_step_deadline() -> float:
    """Read the deployed step deadline from this command's own environment.

    Raises ``ValueError`` naming :data:`STEP_DEADLINE_ENV` when the variable is
    absent, blank, unparseable, or not a positive finite number. The command
    refuses rather than defaulting, because a defaulted value recorded as the
    deployed one would make AC-0306's agreement check compare the record
    against itself.
    """
    raw = os.environ.get(STEP_DEADLINE_ENV)
    if raw is None or not raw.strip():
        raise ValueError(
            f"{STEP_DEADLINE_ENV} is unset; run this command with the same value "
            f"deploy/compose.yaml sets on the worker services"
        )
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"{STEP_DEADLINE_ENV} is not a number: {raw!r}") from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{STEP_DEADLINE_ENV} must be positive and finite, got {raw!r}")
    return value


class StreamNotInFlightError(ValueError):
    """The stream had already ended when cancellation was requested.

    Raised instead of classifying, because a reader that finished on its own
    before the close says nothing about cancellation: recording it as
    ``terminated`` would measure the close of a stream that was not running.
    AC-0309 measures cancellation "on an in-flight model stream", and the
    measurement commands refuse an invalid sample rather than record it.
    """


def classify_cancellation_outcome(
    close_stream: Callable[[], bool],
    observe_closure: Callable[[float], bool],
    *,
    window_seconds: float = _CANCELLATION_WINDOW_SECONDS,
) -> str:
    """Classify a cancellation outcome from this process's reader completing.

    ``close_stream()`` closes the provider response body and returns whether
    this process's reader was **still running at the moment of the close**.
    ``observe_closure(timeout)`` returns ``True`` when that reader completes
    within ``timeout`` seconds of the close.

    **A stream that was not in flight is refused, not classified.** When
    ``close_stream()`` reports the reader had already finished, the stream
    ended on its own and the close cancelled nothing; this raises
    :class:`StreamNotInFlightError` rather than return ``"terminated"``. Only a
    reader alive at the close and finished after it is a cancellation.

    Returns ``"terminated"`` when the reader completes inside
    ``window_seconds`` and ``"abandoned"`` otherwise. The outcome is derived
    entirely from that observation and is never supplied by the caller — there
    is no ``outcome`` parameter. AC-0310.

    **The observation is local.** It says that this process stopped reading;
    it says nothing about whether the provider stopped generating or stopped
    billing. ``docs/architecture/pydantic-ai-worker-runtime/operations.md``
    § Cancellation measurement records that limit and the unreachable
    ``abandoned`` branch beside the measured value.

    Local resources are always released: ``observe_closure`` is called even
    when the classification is ``"abandoned"``, to allow a bounded join on the
    reader thread before returning.
    """
    in_flight_at_close = close_stream()
    if not in_flight_at_close:
        # Still join the reader, so local resources are released on refusal too.
        observe_closure(window_seconds)
        raise StreamNotInFlightError(
            "the reader had already finished when the response body was closed; "
            "the stream was not in flight, so the sample is refused"
        )
    observed_closed = observe_closure(window_seconds)
    return "terminated" if observed_closed else "abandoned"


# ── Database read layer ──────────────────────────────────────────────────────


def query_step_durations(conn: Any) -> list[float]:
    """Pair ``step.started`` and ``step.completed`` events and return durations.

    Joins on ``step_id``: each completed step contributes one duration in
    seconds (``step.completed.occurred_at − step.started.occurred_at``).

    Incomplete steps (no ``step.completed``) are excluded. Multiple
    ``step.started`` / ``step.completed`` events for the same step (which
    would indicate a lease-overlap race) produce multiple rows; the measurement
    takes all of them and notes it in the sample size.
    """
    rows = conn.execute(
        """
        SELECT s.occurred_at, c.occurred_at
          FROM events s
          JOIN events c ON s.step_id = c.step_id
         WHERE s.type = 'step.started'
           AND c.type = 'step.completed'
           AND s.step_id IS NOT NULL
        """
    ).fetchall()
    return [
        (c_ts - s_ts).total_seconds()
        for s_ts, c_ts in rows
        if s_ts is not None and c_ts is not None
    ]


# ── Subcommand implementations ───────────────────────────────────────────────


def _cmd_generate(args: argparse.Namespace) -> int:
    """Generate N completed steps for the step-duration measurement.

    Uses TestModel (no provider call) and the full executor path so that
    real ``step.started`` and ``step.completed`` events appear in the event
    log with authentic ``occurred_at`` timestamps.

    Steps are isolated on pool class ``ced-evidence-measure`` so the running
    substrate workers do not claim them.
    """
    import threading
    import uuid

    import psycopg

    from ced.adapters.bedrock.quota import make_references_test_model
    from ced.adapters.postgres.dsn import database_url
    from ced.adapters.postgres.event_log import start_run
    from ced.worker.executor import make_step_body
    from ced.worker.pool import Lease, PoolConfig

    n: int = args.n

    _GENERATE_LIMITS: dict[str, int | bool] = {
        "per_request_input_tokens_limit": 20_000,
        "input_tokens_limit": 200_000,
        "request_limit": 20,
        "tool_calls_limit": 40,
        "count_tokens_before_request": False,
    }

    config = PoolConfig(
        worker_id=_GENERATE_WORKER_ID,
        default_limits=_GENERATE_LIMITS,
        allowed_model_ids=("stub:counting",),
        non_provider_model_ids=("stub:counting",),
        model_factory=lambda _: make_references_test_model(),
        pool_class=_GENERATE_POOL_CLASS,
    )

    model_settings: dict[str, object] = {
        "model_id": "stub:counting",
        "settings": {},
        "limits": {},
    }

    # Insert the measurement role (quarantined: empty ceiling, reference-selection).
    with psycopg.connect(database_url("migration")) as conn:
        conn.execute(
            """
            INSERT INTO agent_role
                (role_name, version, ceiling, instructions, model_settings, output_schema_ref)
            VALUES (%s, 1, '[]'::jsonb, 'Local measurement step', %s::jsonb,
                    'reference-selection')
            ON CONFLICT (role_name, version) DO NOTHING
            """,
            (_GENERATE_ROLE, json.dumps(model_settings)),
        )
        conn.commit()

    step_body = make_step_body(config)
    completed = 0

    for _ in range(n):
        run_id = uuid.uuid4()
        step_id = uuid.uuid4()

        # Create the run and its coordinator step.
        with psycopg.connect(database_url("api")) as conn:
            start_run(
                conn,
                run_id=run_id,
                step_id=step_id,
                principal=_GENERATE_PRINCIPAL,
                agent_role=_GENERATE_ROLE,
            )

        # Claim the step manually (no pool supervisor running).
        with psycopg.connect(database_url("worker")) as conn:
            row = conn.execute(
                """
                UPDATE steps
                   SET state = 'leased',
                       owner = %s,
                       lease_epoch = lease_epoch + 1,
                       lease_expires_at = now() + interval '300 seconds',
                       pool_class = %s
                 WHERE step_id = %s
                RETURNING lease_epoch
                """,
                (config.worker_id, _GENERATE_POOL_CLASS, step_id),
            ).fetchone()
            conn.commit()

        if row is None:
            sys.stderr.write(f"warning: could not claim step {step_id}; skipping\n")
            continue

        lease = Lease(
            step_id=step_id,
            run_id=run_id,
            epoch=int(row[0]),
            agent_role=_GENERATE_ROLE,
        )

        # Run the step body. This appends step.started and step.completed.
        stop = threading.Event()
        try:
            step_body(lease, stop)
            completed += 1
        except Exception as exc:
            sys.stderr.write(f"warning: step {step_id} body raised {exc!r}; skipping\n")

    result = {
        "generated": completed,
        "requested": n,
        "pool_class": _GENERATE_POOL_CLASS,
        "role": _GENERATE_ROLE,
    }
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0 if completed == n else 1


def _cmd_step_duration(args: argparse.Namespace) -> int:
    """Measure step-duration p99 and page threshold from the event log.

    Refuses a sample smaller than SAMPLE_FLOOR, and refuses to measure at all
    without :data:`STEP_DEADLINE_ENV`, which it records beside the bounds so
    AC-0306's check can compare the recorded deadline against the deployed
    one. Emits JSON to stdout and merges it into ``--out`` when specified.
    """
    import psycopg

    from ced.adapters.postgres.dsn import database_url

    try:
        step_deadline = _resolve_deployed_step_deadline()
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    with psycopg.connect(database_url("worker")) as conn:
        durations = query_step_durations(conn)

    try:
        step_duration = build_step_duration_record(durations)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    output: dict[str, object] = {
        "step_duration": step_duration,
        "configured_step_deadline_seconds": step_deadline,
        "configured_step_deadline_source": (
            f"{STEP_DEADLINE_ENV} in this command's environment, set to the value "
            f"deploy/compose.yaml carries on both worker services"
        ),
    }

    sys.stdout.write(json.dumps(output, indent=2) + "\n")

    out: str | None = getattr(args, "out", None)
    if out:
        try:
            _write_record(out, output)
        except ValueError as exc:
            # The record is already on stdout, so a refused merge loses nothing.
            sys.stderr.write(f"error: {exc}\n")
            return 1
        sys.stderr.write(f"written to {out}\n")

    return 0


def _cmd_cancellation(args: argparse.Namespace) -> int:
    """Measure cancellation latency on a live Bedrock response stream.

    Delegates stream open and boto3 usage to the adapter layer (AC-0007: AWS
    SDK confined to ``adapters/``). ``classify_cancellation_outcome`` derives
    the result from one locally observed property — this process's reader
    completing after the response body is closed — and never from a
    caller-supplied outcome. AC-0309, AC-0310.
    """
    import time

    from ced.adapters.bedrock.quota import open_cancellation_stream

    model_id = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    _WINDOW = _CANCELLATION_WINDOW_SECONDS

    try:
        region, close_stream, observe_closure = open_cancellation_stream(model_id)
    except Exception as exc:
        sys.stderr.write(f"error: Bedrock invoke failed: {exc}\n")
        return 1

    t_start = time.monotonic()
    try:
        outcome = classify_cancellation_outcome(
            close_stream, observe_closure, window_seconds=_WINDOW
        )
    except StreamNotInFlightError as exc:
        # Refused, not recorded: a stream that ended on its own before the
        # close is not a cancellation sample, and recording it would be the
        # false witness this check exists to prevent.
        sys.stderr.write(f"error: {exc}\n")
        return 1
    latency_seconds = time.monotonic() - t_start

    record: dict[str, object] = {
        "cancellation": {
            "outcome": outcome,
            "latency_seconds": round(latency_seconds, 6),
            "region": region,
            "model_id": model_id,
            "method": (
                "long generation; close response body while the reader is still "
                f"running; observe reader join within {_WINDOW:.0f}s window"
            ),
            # Always true when a record is written: a sample whose reader had
            # already finished is refused above. Emitted so the witness
            # carries the observation its in-flight premise rests on.
            "in_flight_at_close": True,
            "measured": measured_on(),
        }
    }
    sys.stdout.write(json.dumps(record, indent=2) + "\n")

    out: str | None = getattr(args, "out", None)
    if out:
        try:
            _write_record(out, record)
        except ValueError as exc:
            # The record is already on stdout, so a refused merge loses nothing.
            sys.stderr.write(f"error: {exc}\n")
            return 1
        sys.stderr.write(f"written to {out}\n")

    return 0


def _cmd_quota(args: argparse.Namespace) -> int:
    """Read the Bedrock TPM quota from AWS Service Quotas.

    Delegates boto3 client creation to the adapter layer (AC-0007: AWS SDK
    confined to ``adapters/``). Region is taken from the resolved client.
    Credential and account metadata are never read or written. AC-0311.
    """
    from ced.adapters.bedrock.quota import run_quota_measurement

    try:
        record = run_quota_measurement()
    except Exception as exc:
        sys.stderr.write(f"error: Service Quotas read failed: {exc}\n")
        return 1

    output = {"quota": {**record, "measured": measured_on()}}
    sys.stdout.write(json.dumps(output, indent=2) + "\n")

    out: str | None = getattr(args, "out", None)
    if out:
        try:
            _write_record(out, output)
        except ValueError as exc:
            # The record is already on stdout, so a refused merge loses nothing.
            sys.stderr.write(f"error: {exc}\n")
            return 1
        sys.stderr.write(f"written to {out}\n")

    return 0


# ── CLI entry point ──────────────────────────────────────────────────────────


def run() -> None:
    """The ``ced-evidence`` console-script entry point."""
    parser = argparse.ArgumentParser(
        prog="ced-evidence",
        description="Phase 1 operational evidence commands.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # generate
    gen_p = sub.add_parser("generate", help="Generate N completed steps for measurement.")
    gen_p.add_argument(
        "--n", type=int, default=SAMPLE_FLOOR, help="Number of steps to generate."
    )

    # step-duration
    dur_p = sub.add_parser(
        "step-duration", help="Compute p99 step duration from the event log."
    )
    dur_p.add_argument(
        "--out", metavar="PATH", help="Write JSON to PATH in addition to stdout."
    )

    # cancellation (live provider)
    canc_p = sub.add_parser(
        "cancellation", help="Measure cancellation latency (requires AWS credentials)."
    )
    canc_p.add_argument(
        "--out", metavar="PATH", help="Write JSON to PATH in addition to stdout."
    )

    # quota (live provider)
    quota_p = sub.add_parser("quota", help="Read Bedrock TPM quota (requires AWS credentials).")
    quota_p.add_argument(
        "--out", metavar="PATH", help="Write JSON to PATH in addition to stdout."
    )

    args = parser.parse_args()
    dispatch: dict[str, Callable[[argparse.Namespace], int]] = {
        "generate": _cmd_generate,
        "step-duration": _cmd_step_duration,
        "cancellation": _cmd_cancellation,
        "quota": _cmd_quota,
    }
    sys.exit(dispatch[args.cmd](args))
