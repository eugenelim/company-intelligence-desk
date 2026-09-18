"""The lock-ordering rule, demonstrated by showing it failing.

`steps` before `runs`, on every path including the fence. Both that and
fence-before-allocate follow from one property: the `runs` row lock serialises
appends per run, so it must be taken last and held briefly.

Phase 0 sharpened the claim and this suite carries that sharpening. A
*uniformly* inverted order does **not** deadlock — every writer takes the same
`runs` row first and serialises there, so no cycle can form. The hazard is
strictly one path inverting **against** another. A test that only showed
"inverted order deadlocks" would be asserting something false.

The container runs `deadlock_timeout` at 200 ms, so the detector fires quickly
here. Production defaults to 1 s.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from uuid import UUID

import psycopg
import pytest

from ced.adapters.postgres.dsn import database_url

pytestmark = pytest.mark.substrate

ROUNDS = 12
_BARRIER_TIMEOUT_SECONDS = 5.0

_LOCK_STEPS = ("SELECT 1 FROM steps WHERE step_id = %s FOR UPDATE", "step")
_LOCK_RUNS = ("UPDATE runs SET next_seq = next_seq WHERE run_id = %s", "run")


@pytest.fixture
def contended_pair(owner_conn: psycopg.Connection) -> Iterator[tuple[UUID, UUID]]:
    """One run and one step, so every contender fights over the same two rows."""
    run_id, step_id = uuid.uuid4(), uuid.uuid4()
    with owner_conn.transaction():
        owner_conn.execute("INSERT INTO runs (run_id) VALUES (%s)", (run_id,))
        owner_conn.execute(
            "INSERT INTO steps (step_id, run_id, lease_epoch) VALUES (%s, %s, 1)",
            (step_id, run_id),
        )
    try:
        yield run_id, step_id
    finally:
        with owner_conn.transaction():
            owner_conn.execute("DELETE FROM events WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM steps WHERE run_id = %s", (run_id,))
            owner_conn.execute("DELETE FROM runs WHERE run_id = %s", (run_id,))


def _contend(
    run_id: UUID, step_id: UUID, order: tuple[str, str], barrier: threading.Barrier
) -> list[str]:
    """Take two row locks in `order`, pausing between them at the barrier.

    The barrier is what makes the interleaving deterministic enough to observe:
    both contenders hold their first lock before either asks for its second.
    """
    deadlocks: list[str] = []
    ids = {"step": (step_id,), "run": (run_id,)}
    for _ in range(ROUNDS):
        try:
            with psycopg.connect(database_url("migration")) as conn:
                with conn.transaction():
                    for position, which in enumerate(order):
                        sql = _LOCK_STEPS[0] if which == "step" else _LOCK_RUNS[0]
                        conn.execute(sql, ids[which])
                        if position == 0:
                            try:
                                barrier.wait(timeout=_BARRIER_TIMEOUT_SECONDS)
                            except threading.BrokenBarrierError:
                                pass
        except psycopg.errors.DeadlockDetected as exc:
            deadlocks.append(str(exc).splitlines()[0][:100])
        except psycopg.Error:
            # A lock timeout or a broken barrier is not a deadlock and is not
            # counted either way. Only 40P01 answers this question.
            pass
    return deadlocks


def _run_contenders(
    run_id: UUID, step_id: UUID, orders: tuple[tuple[str, str], ...]
) -> list[str]:
    barrier = threading.Barrier(len(orders))
    results: list[list[str]] = []
    threads = [
        threading.Thread(
            target=lambda o=order: results.append(_contend(run_id, step_id, o, barrier))
        )
        for order in orders
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return [d for group in results for d in group]


def test_mixing_the_two_orders_deadlocks(
    contended_pair: tuple[UUID, UUID],
) -> None:
    """The rule, shown failing. One path inverting against another cycles."""
    run_id, step_id = contended_pair

    deadlocks = _run_contenders(run_id, step_id, (("step", "run"), ("run", "step")))

    assert deadlocks, (
        "no deadlock observed under mixed lock orders — the ordering rule is "
        "unproven, not satisfied"
    )


def test_a_uniformly_inverted_order_does_not_deadlock(
    contended_pair: tuple[UUID, UUID],
) -> None:
    """Phase 0's sharpening, asserted so the claim above stays precise.

    Every writer takes the same `runs` row first and serialises there, so no
    cycle forms. Without this test the suite would be read as "inverted order
    deadlocks", which is false and would send a reader looking for the wrong
    defect.
    """
    run_id, step_id = contended_pair

    deadlocks = _run_contenders(run_id, step_id, (("run", "step"), ("run", "step")))

    assert deadlocks == [], f"unexpected deadlocks: {deadlocks[:2]}"


def test_the_designed_order_does_not_deadlock(
    contended_pair: tuple[UUID, UUID],
) -> None:
    """And the order the code actually uses is clean under the same pressure."""
    run_id, step_id = contended_pair

    deadlocks = _run_contenders(run_id, step_id, (("step", "run"), ("step", "run")))

    assert deadlocks == [], f"unexpected deadlocks: {deadlocks[:2]}"


def test_both_append_paths_take_the_steps_lock_first(
    owner_conn: psycopg.Connection,
) -> None:
    """A structural check on the SQL, so a future edit cannot silently invert it.

    Reads the function bodies out of the catalogue. The behavioural tests above
    show the rule mattering; this one names where it is written down, which is
    what a reader needs when one of them starts failing.
    """
    for name in ("append_step_event", "append_policy_decision"):
        row = owner_conn.execute(
            "SELECT prosrc FROM pg_proc p JOIN pg_namespace n "
            "ON n.oid = p.pronamespace WHERE n.nspname = 'public' "
            "AND p.proname = %s",
            (name,),
        ).fetchone()
        assert row is not None, f"{name} is absent"
        body = row[0]

        fence_at = body.index("fence_step(")
        allocate_at = body.index("UPDATE runs")
        assert fence_at < allocate_at, (
            f"{name} allocates from `runs` before fencing on `steps`, "
            "inverting the ratified lock order"
        )
