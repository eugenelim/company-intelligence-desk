"""The retry wrapper's own branches, and the terminal-state guard.

Both were unexercised. `retry_on_deadlock` sits on all three append paths and
r7 § Event log requires it, but the only check naming it asserted a fence is
*not* retried — so the retry branch, the backoff indexing and the
exhausted-attempts re-raise never ran under the gate that `AGENTS.md` records
as the whole gate. `RunAlreadyTerminal` was raised and never caught.

The retry checks are in-process against a stub callable rather than against a
real deadlock. A real 40P01 through an append path is not reliably producible
on demand — the designed lock order is precisely what prevents it — so the
choice is a stub that exercises the branch or no coverage at all.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from ced.adapters.postgres import event_log

from .conftest import LeasedStep, next_seq_of, sequence_of


def test_a_deadlock_is_retried_and_the_second_attempt_succeeds() -> None:
    """The retry branch, observed rather than assumed."""
    attempts: list[int] = []

    def flaky() -> str:
        attempts.append(len(attempts) + 1)
        if len(attempts) < 2:
            raise psycopg.errors.DeadlockDetected("deadlock detected")
        return "committed"

    assert event_log.retry_on_deadlock(flaky) == "committed"
    assert attempts == [1, 2]


def test_every_backoff_step_is_walked_before_giving_up() -> None:
    """The backoff indexing: three attempts, and no IndexError on the last."""
    attempts: list[int] = []

    def always_deadlocks() -> str:
        attempts.append(len(attempts) + 1)
        raise psycopg.errors.DeadlockDetected("deadlock detected")

    with pytest.raises(psycopg.errors.DeadlockDetected):
        event_log.retry_on_deadlock(always_deadlocks)

    assert len(attempts) == event_log.DEADLOCK_ATTEMPTS


def test_the_exhausted_case_re_raises_rather_than_returning_none() -> None:
    """The declared return type is `T`; falling through would return `None`."""

    def always_deadlocks() -> str:
        raise psycopg.errors.DeadlockDetected("the last one")

    with pytest.raises(psycopg.errors.DeadlockDetected, match="the last one"):
        event_log.retry_on_deadlock(always_deadlocks)


def test_a_non_deadlock_error_is_not_retried() -> None:
    """Scoped to 40P01. A fence loss must reach the caller on the first try."""
    attempts: list[int] = []

    def fenced() -> str:
        attempts.append(1)
        raise psycopg.errors.SerializationFailure("fenced")

    with pytest.raises(psycopg.errors.SerializationFailure):
        event_log.retry_on_deadlock(fenced)
    assert attempts == [1]


# ── The terminal-state guard ────────────────────────────────────────────────


@pytest.mark.substrate
def test_a_late_cancel_after_a_terminal_state_is_a_no_op(
    api_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
    leased_step: LeasedStep,
) -> None:
    """`RunAlreadyTerminal`, which was raised and never asserted.

    The guard is not cosmetic: the stream closes on a terminal event, so a
    `run.cancelled` committing after a terminal state would be present in the
    log and invisible to every live client — a reconstruction divergence.
    """
    assert (
        event_log.append_run_event(
            api_conn,
            run_id=leased_step.run_id,
            type="run.requested",
            principal="operator",
        )
        == 1
    )
    with owner_conn.transaction():
        owner_conn.execute(
            "UPDATE runs SET state = 'completed' WHERE run_id = %s",
            (leased_step.run_id,),
        )

    with pytest.raises(event_log.RunAlreadyTerminal):
        event_log.append_run_event(
            api_conn,
            run_id=leased_step.run_id,
            type="run.cancelled",
            principal="operator",
        )

    # And it consumed no sequence number, so the log stays dense.
    assert sequence_of(owner_conn, leased_step.run_id) == [1]
    assert next_seq_of(owner_conn, leased_step.run_id) == 1


@pytest.mark.substrate
def test_an_append_to_an_absent_run_is_refused(api_conn: psycopg.Connection) -> None:
    """The same guard covers a run that never existed."""
    with pytest.raises(event_log.RunAlreadyTerminal):
        event_log.append_run_event(
            api_conn, run_id=uuid.uuid4(), type="run.requested", principal="operator"
        )


def test_the_backoff_tuple_has_one_value_per_gap_between_attempts() -> None:
    """`retry_on_deadlock` sleeps between attempts, never after the last.

    Held here rather than by a module-level `assert`, which `python -O` strips
    — leaving the invariant as the trust the assert claimed to replace. A
    fourth attempt would otherwise sleep off the end of the tuple, and a
    shortened tuple would silently skip a sleep.
    """
    assert len(event_log.DEADLOCK_BACKOFF_SECONDS) == event_log.DEADLOCK_ATTEMPTS - 1, (
        f"{event_log.DEADLOCK_ATTEMPTS} attempts need "
        f"{event_log.DEADLOCK_ATTEMPTS - 1} backoff values, but the tuple has "
        f"{len(event_log.DEADLOCK_BACKOFF_SECONDS)}"
    )
