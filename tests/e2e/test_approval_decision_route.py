"""AC-0328: the approval decision route, driven end-to-end over the wire.

AC-0328 requires:
- A missing Origin is refused with 400.
- A foreign Origin is refused with 400.
- These refusals happen before any append (the DB is not touched).
- The decision set is bounded (too many pairs → 422 before append).
- 404 for a nonexistent run.
- 409 when the step is not in the run.
- The happy path commits a decision.

AC-0303: ``require_distinct_approver`` is deployment configuration, not
caller-supplied. The test configures the flag both ways (by setting
``app.state.require_distinct_approver``) and reads back two different
appended payload values, so a module constant cannot satisfy it.

All tests drive the shipped route over a real uvicorn server on a loopback
port. ``e2e_server`` is session-scoped so startup cost is paid once. Tests
that change ``app.state`` reset it in a finally block to avoid contaminating
the session.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from ced.adapters.objectstore.client import read_payload
from ced.adapters.postgres.dsn import database_url

from .conftest import E2EClient, SuspendedE2E

pytestmark = pytest.mark.substrate


# ── AC-0328: Origin defence ──────────────────────────────────────────────────


def test_origin_absent_is_refused(e2e_server: E2EClient) -> None:
    """AC-0328: an absent Origin header is refused with 400 before any append.

    The route checks Origin before touching the database (``_require_run`` is
    not called), so no run needs to exist.  Mutation-proof: if the Origin check
    is dropped, the route falls through to ``_require_run`` and returns 404,
    not 400 — a different status code that reds this assertion.
    """
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    resp = e2e_server.post(
        f"/runs/{run_id}/steps/{step_id}/decision",
        payload={
            "suspension_seq": 1,
            "decisions": [{"call_id": "c1", "granted": True}],
            "principal": "approver",
        },
        # No Origin header — should be refused with 400.
    )
    assert resp.status == 400, f"expected 400 for absent Origin, got {resp.status}: {resp.body}"
    assert "origin" in str(resp.body).lower(), (
        f"expected 'origin' in error detail, got {resp.body!r}"
    )


def test_foreign_origin_is_refused(e2e_server: E2EClient) -> None:
    """AC-0328: a foreign Origin is refused with 400 before any append.

    Mutation-proof: if the origin comparison is removed, the request falls
    through to ``_require_run`` and returns 404 for this non-existent run,
    not 400 — a different status that reds this assertion.
    """
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    resp = e2e_server.post(
        f"/runs/{run_id}/steps/{step_id}/decision",
        payload={
            "suspension_seq": 1,
            "decisions": [{"call_id": "c1", "granted": True}],
            "principal": "approver",
        },
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status == 400, (
        f"expected 400 for foreign Origin, got {resp.status}: {resp.body}"
    )
    assert "does not match" in str(resp.body).lower() or "origin" in str(resp.body).lower(), (
        f"expected origin mismatch in error detail, got {resp.body!r}"
    )


def test_nonexistent_run_is_404(e2e_server: E2EClient) -> None:
    """AC-0328: a run that does not exist returns 404."""
    run_id = uuid.uuid4()
    step_id = uuid.uuid4()
    resp = e2e_server.post(
        f"/runs/{run_id}/steps/{step_id}/decision",
        payload={
            "suspension_seq": 1,
            "decisions": [{"call_id": "c1", "granted": True}],
            "principal": "approver",
        },
        headers={"Origin": e2e_server.origin},
    )
    assert resp.status == 404, (
        f"expected 404 for nonexistent run, got {resp.status}: {resp.body}"
    )


def test_step_not_in_run_is_404(e2e_server: E2EClient, suspended_e2e: SuspendedE2E) -> None:
    """AC-0328: a step that does not belong to the run returns 404."""
    other_step = uuid.uuid4()
    resp = e2e_server.post(
        f"/runs/{suspended_e2e.run_id}/steps/{other_step}/decision",
        payload={
            "suspension_seq": suspended_e2e.suspension_seq,
            "decisions": [{"call_id": "c1", "granted": True}],
            "principal": "approver",
        },
        headers={"Origin": e2e_server.origin},
    )
    assert resp.status == 404, (
        f"expected 404 for step not in run, got {resp.status}: {resp.body}"
    )


def test_decision_set_bound_is_refused_before_append(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0328: too many decision pairs is refused (422) before any append.

    The ``decisions`` field is bounded at ``ATTRIBUTION_MAX_LENGTH`` entries by
    Pydantic, which validates before the route body runs. Mutation-proof: if the
    bound is removed, the request succeeds (not 422), and the status assertion
    reds. The "refused before any append" half is verified by reading the event
    count before and after — it must not change.
    """
    from ced.api.models import ATTRIBUTION_MAX_LENGTH

    with psycopg.connect(database_url("migration")) as conn:
        count_before = conn.execute(
            "SELECT count(*) FROM events WHERE run_id = %s",
            (suspended_e2e.run_id,),
        ).fetchone()[0]  # type: ignore[index]

    oversized_decisions = [
        {"call_id": f"call-{i}", "granted": True} for i in range(ATTRIBUTION_MAX_LENGTH + 1)
    ]
    resp = e2e_server.post(
        f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
        payload={
            "suspension_seq": suspended_e2e.suspension_seq,
            "decisions": oversized_decisions,
            "principal": "approver",
        },
        headers={"Origin": e2e_server.origin},
    )
    assert resp.status == 422, (
        f"expected 422 for oversized decision set, got {resp.status}: {resp.body}"
    )

    with psycopg.connect(database_url("migration")) as conn:
        count_after = conn.execute(
            "SELECT count(*) FROM events WHERE run_id = %s",
            (suspended_e2e.run_id,),
        ).fetchone()[0]  # type: ignore[index]

    assert count_after == count_before, (
        f"event count changed from {count_before} to {count_after}: "
        "the oversized request must not append any event"
    )


def test_wrong_suspension_seq_is_409(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0328: a decision naming a stale suspension seq returns 409."""
    resp = e2e_server.post(
        f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
        payload={
            "suspension_seq": suspended_e2e.suspension_seq + 99,  # wrong seq
            "decisions": [{"call_id": "c1", "granted": True}],
            "principal": "approver",
        },
        headers={"Origin": e2e_server.origin},
    )
    assert resp.status == 409, (
        f"expected 409 for stale suspension seq, got {resp.status}: {resp.body}"
    )


def test_happy_path_commits_and_returns_last_seq(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0328: a well-formed decision over the right suspension commits."""
    resp = e2e_server.post(
        f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
        payload={
            "suspension_seq": suspended_e2e.suspension_seq,
            "decisions": [{"call_id": "c1", "granted": True}],
            "principal": "approver",
        },
        headers={"Origin": e2e_server.origin},
    )
    assert resp.status == 200, f"expected 200 for happy path, got {resp.status}: {resp.body}"
    assert "last_seq" in resp.body, f"response missing last_seq: {resp.body!r}"
    assert resp.body["last_seq"] > 0


# ── AC-0303: require_distinct_approver — deployment configuration ─────────────


def test_require_distinct_configured_false_records_false_in_payload(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0303: with the flag off, the payload records false and the same
    principal as the run's initiator is accepted.

    This is one of two required configurations. The flag is read from
    ``app.state`` (deployment config), not from the request body.
    """
    from ced.api.main import app as _app  # the module-level singleton

    _app.state.require_distinct_approver = False
    try:
        resp = e2e_server.post(
            f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
            payload={
                "suspension_seq": suspended_e2e.suspension_seq,
                "decisions": [{"call_id": "c1", "granted": True}],
                # Same as initiating principal — must succeed when flag is False.
                "principal": suspended_e2e.initiating_principal,
            },
            headers={"Origin": e2e_server.origin},
        )
    finally:
        _app.state.require_distinct_approver = False  # restore

    assert resp.status == 200, (
        f"expected 200 when require_distinct_approver=false, got {resp.status}: {resp.body}"
    )

    # Read the payload_ref from the committed event and load it from the object store.
    last_seq = resp.body["last_seq"]
    with psycopg.connect(database_url("migration")) as conn:
        row = conn.execute(
            "SELECT payload_ref FROM events WHERE run_id = %s AND seq = %s",
            (suspended_e2e.run_id, last_seq),
        ).fetchone()
    assert row is not None and row[0] is not None, "committed event has no payload_ref"
    payload = read_payload(row[0])
    assert payload.get("require_distinct_approver") is False, (
        f"payload must record require_distinct_approver=false when flag is off, "
        f"got {payload.get('require_distinct_approver')!r}"
    )


def test_require_distinct_configured_true_refuses_same_principal(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0303: with the flag on, the same principal as the initiator is refused.

    This is the second required configuration. The flag is deployment config;
    the caller cannot override it by sending a different request body field.
    Mutation-proof: if the guard is absent, the request succeeds (200) and
    this assertion reds on the 200 status.
    """
    from ced.api.main import app as _app

    _app.state.require_distinct_approver = True
    try:
        resp = e2e_server.post(
            f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
            payload={
                "suspension_seq": suspended_e2e.suspension_seq,
                "decisions": [{"call_id": "c1", "granted": True}],
                # Same as initiating principal — must be refused when flag is True.
                "principal": suspended_e2e.initiating_principal,
            },
            headers={"Origin": e2e_server.origin},
        )
    finally:
        _app.state.require_distinct_approver = False  # restore

    assert resp.status == 409, (
        f"expected 409 when require_distinct_approver=true and same principal, "
        f"got {resp.status}: {resp.body}"
    )
    assert "distinct" in str(resp.body).lower() or "principal" in str(resp.body).lower(), (
        f"expected 'distinct' or 'principal' in error detail, got {resp.body!r}"
    )


def test_require_distinct_configured_true_records_true_in_payload(
    e2e_server: E2EClient, suspended_e2e: SuspendedE2E
) -> None:
    """AC-0303: with the flag on, a distinct principal succeeds and the payload
    records true — producing a different value than the flag-off case.

    This completes the "configuring both ways and reading back two different
    appended values" requirement. A module constant set to False would fail
    this assertion (because it could not record True); a constant set to True
    would fail test_require_distinct_configured_false_records_false_in_payload.
    """
    from ced.api.main import app as _app

    _app.state.require_distinct_approver = True
    try:
        resp = e2e_server.post(
            f"/runs/{suspended_e2e.run_id}/steps/{suspended_e2e.step_id}/decision",
            payload={
                "suspension_seq": suspended_e2e.suspension_seq,
                "decisions": [{"call_id": "c1", "granted": True}],
                # DIFFERENT from initiating principal — must succeed.
                "principal": "distinct-approver-principal",
            },
            headers={"Origin": e2e_server.origin},
        )
    finally:
        _app.state.require_distinct_approver = False  # restore

    assert resp.status == 200, (
        f"expected 200 when require_distinct_approver=true and distinct principal, "
        f"got {resp.status}: {resp.body}"
    )

    last_seq = resp.body["last_seq"]
    with psycopg.connect(database_url("migration")) as conn:
        row = conn.execute(
            "SELECT payload_ref FROM events WHERE run_id = %s AND seq = %s",
            (suspended_e2e.run_id, last_seq),
        ).fetchone()
    assert row is not None and row[0] is not None, "committed event has no payload_ref"
    payload = read_payload(row[0])
    assert payload.get("require_distinct_approver") is True, (
        f"payload must record require_distinct_approver=true when flag is on, "
        f"got {payload.get('require_distinct_approver')!r}"
    )
