"""AC-0010 and AC-0011 — host loss and graceful drain, told apart.

Both drive real containers. `docker kill` sends SIGKILL, so the worker gets no
chance to tidy up and the only thing that returns the step is the lease
expiring — which is the recovery path r7 specifies and the one an unplanned
host loss actually takes. `docker stop` sends SIGTERM, which the worker
handles by expiring its own lease.

Without AC-0011 the two paths are indistinguishable at 150 s, and a rolling
deploy would silently cost as much as losing a host.

**What these results do not establish.** Two workers are running throughout, so
"no operator action" holds because the replacement **already existed** — not
because a scheduler created one. A deployed ECS service with a desired count
would replace the killed task; nothing here does. And these are local
containers on one Docker host: nothing about Fargate task replacement, its
timing, or its notice period is measured.
"""

from __future__ import annotations

import time
from uuid import UUID

import psycopg
import pytest

from .conftest import (
    OBSERVATION_MARGIN_SECONDS,
    WORST_CASE_SECONDS,
    container_is_running,
    docker,
    observe,
    wait_for_reacquisition,
    wait_until_claimed,
)

pytestmark = pytest.mark.substrate

#: The claim has to happen before anything can be killed. One poll interval
#: plus margin; a longer wait here would hide a worker that never polls.
CLAIM_TIMEOUT_SECONDS = 45

#: r7 § Step execution: a drain recovers "in one poll interval".
POLL_SECONDS = 30


def _container_for(owner: str) -> str:
    """`CED_WORKER_ID` is the container's own name minus Compose's decoration."""
    return f"deploy-{owner}-1"


def _restart(container: str) -> None:
    """Put the killed worker back, so the next test starts from two again."""
    docker("start", container)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if container_is_running(container):
            return
        time.sleep(0.5)


def test_a_killed_worker_has_its_step_reacquired_within_150_seconds(
    owner_conn: psycopg.Connection,
    running_workers: list[str],
    pending_step: tuple[UUID, UUID],
) -> None:
    """AC-0010. SIGKILL, so only lease expiry can return the step."""
    _run_id, step_id = pending_step

    claimed = wait_until_claimed(owner_conn, step_id, CLAIM_TIMEOUT_SECONDS)
    assert claimed.owner is not None
    first_owner = claimed.owner
    first_epoch = claimed.epoch
    victim = _container_for(first_owner)

    killed = docker("kill", victim)
    assert killed.returncode == 0, killed.stderr
    assert not container_is_running(victim)

    try:
        reacquired, elapsed = wait_for_reacquisition(
            owner_conn,
            step_id,
            first_owner,
            WORST_CASE_SECONDS + OBSERVATION_MARGIN_SECONDS,
        )
    finally:
        _restart(victim)

    assert reacquired.owner != first_owner
    # The epoch advanced, which is what fences the dead worker out for good:
    # were it somehow still alive, every write it attempted would roll back.
    assert reacquired.epoch > first_epoch
    assert elapsed <= WORST_CASE_SECONDS, (
        f"reacquisition took {elapsed:.1f} s, above the 150 s worst case"
    )
    print(
        f"\nAC-0010: {first_owner} killed; {reacquired.owner} reacquired step "
        f"{step_id} after {elapsed:.1f} s (epoch {first_epoch} → "
        f"{reacquired.epoch})"
    )


def test_a_drained_worker_returns_its_step_within_one_poll_interval(
    owner_conn: psycopg.Connection,
    running_workers: list[str],
    pending_step: tuple[UUID, UUID],
) -> None:
    """AC-0011. SIGTERM, so the worker expires its own lease before exiting."""
    _run_id, step_id = pending_step

    claimed = wait_until_claimed(owner_conn, step_id, CLAIM_TIMEOUT_SECONDS)
    assert claimed.owner is not None
    first_owner = claimed.owner
    victim = _container_for(first_owner)

    # `docker stop` sends SIGTERM and waits. The worker's handler expires the
    # lease, which is the whole difference from the test above.
    stopped = docker("stop", "-t", "30", victim)
    assert stopped.returncode == 0, stopped.stderr

    try:
        reacquired, elapsed = wait_for_reacquisition(
            owner_conn,
            step_id,
            first_owner,
            POLL_SECONDS + OBSERVATION_MARGIN_SECONDS,
        )
    finally:
        _restart(victim)

    assert reacquired.owner != first_owner
    assert elapsed <= POLL_SECONDS + OBSERVATION_MARGIN_SECONDS
    print(
        f"\nAC-0011: {first_owner} drained; {reacquired.owner} reacquired step "
        f"{step_id} after {elapsed:.1f} s (one poll interval is "
        f"{POLL_SECONDS} s)"
    )


def test_the_drain_is_faster_than_waiting_out_the_lease(
    owner_conn: psycopg.Connection,
    running_workers: list[str],
    pending_step: tuple[UUID, UUID],
) -> None:
    """The comparison AC-0011 exists to make, asserted rather than implied.

    A drain that happened to take 150 s would satisfy AC-0010's bound and tell
    an operator nothing about whether the graceful path works at all.
    """
    _run_id, step_id = pending_step

    claimed = wait_until_claimed(owner_conn, step_id, CLAIM_TIMEOUT_SECONDS)
    assert claimed.owner is not None
    victim = _container_for(claimed.owner)

    docker("stop", "-t", "30", victim)
    try:
        _reacquired, elapsed = wait_for_reacquisition(
            owner_conn,
            step_id,
            claimed.owner,
            POLL_SECONDS + OBSERVATION_MARGIN_SECONDS,
        )
    finally:
        _restart(victim)

    assert elapsed < WORST_CASE_SECONDS, (
        "the drain took as long as an unplanned host loss, so the two paths "
        "are indistinguishable"
    )


def test_a_step_is_claimed_by_exactly_one_worker_at_a_time(
    owner_conn: psycopg.Connection,
    running_workers: list[str],
    pending_step: tuple[UUID, UUID],
) -> None:
    """`FOR UPDATE SKIP LOCKED` with two workers polling the same class.

    Both workers are live and polling; the step must land with one of them and
    carry exactly one owner. Without this the recovery tests could pass while
    both workers ran the same step.
    """
    _run_id, step_id = pending_step

    claimed = wait_until_claimed(owner_conn, step_id, CLAIM_TIMEOUT_SECONDS)

    assert claimed.owner in ("worker-a", "worker-b")
    assert claimed.epoch == 1, "a fresh step should be claimed at epoch 1"
    # Read again after a heartbeat interval: ownership must not oscillate.
    time.sleep(25)
    later = observe(owner_conn, step_id)
    assert later.owner == claimed.owner
    assert later.epoch == claimed.epoch
    assert later.lease_expires_at > claimed.lease_expires_at, (
        "the heartbeat did not renew the lease"
    )
