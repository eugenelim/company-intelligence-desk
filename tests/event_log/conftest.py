"""Fixtures for the event-log suite: a run with a leased step, per test."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import psycopg
import pytest


@dataclass(frozen=True)
class LeasedStep:
    """A committed run with one step already leased at a known epoch."""

    run_id: UUID
    step_id: UUID
    lease_epoch: int


@pytest.fixture
def leased_step(owner_conn: psycopg.Connection) -> Iterator[LeasedStep]:
    """Create a run and a step leased at epoch 1, and clean both up after.

    Set up as the owner rather than through the API path on purpose: this
    fixture must not depend on the code under test to establish its
    preconditions, or a broken append path would look like a broken fixture.
    """
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute("INSERT INTO runs (run_id) VALUES (%s)", (run_id,))
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, state, owner, lease_epoch, "
            "lease_expires_at) VALUES (%s, %s, 'leased', 'fixture', 1, "
            "now() + interval '60 seconds')",
            (step_id, run_id),
        )
    try:
        yield LeasedStep(run_id=run_id, step_id=step_id, lease_epoch=1)
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


def sequence_of(conn: psycopg.Connection, run_id: UUID) -> list[int]:
    """Return a run's committed `seq` values in order."""
    return [
        row[0]
        for row in conn.execute(
            "SELECT seq FROM events WHERE run_id = %s ORDER BY seq", (run_id,)
        ).fetchall()
    ]


def next_seq_of(conn: psycopg.Connection, run_id: UUID) -> int:
    row = conn.execute("SELECT next_seq FROM runs WHERE run_id = %s", (run_id,)).fetchone()
    assert row is not None
    return int(row[0])
