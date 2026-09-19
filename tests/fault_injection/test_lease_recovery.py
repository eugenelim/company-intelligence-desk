"""AC-0010 and AC-0011 — host loss and graceful drain, told apart.

Both drive real containers. `docker kill` sends SIGKILL, so the worker gets no
chance to tidy up and the only thing that returns the step is the lease
expiring — which is the recovery path r7 specifies and the one an unplanned
host loss actually takes. `docker kill --signal=TERM`
sends SIGTERM without waiting, which the worker handles by expiring its own
lease — and which lets the measured interval start at signal delivery.

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

from ced.worker.pool import (
    DERIVED_REACQUISITION_BOUND_SECONDS,
)

from .conftest import (
    CONTAINER_POOL_CLASS,
    OBSERVATION_MARGIN_SECONDS,
    OBSERVER_STEP_SECONDS,
    POLL_SECONDS,
    POOL_HEARTBEAT_SECONDS,
    REACQUIRE_BOUND_SECONDS,
    WORST_CASE_SECONDS,
    container_is_running,
    docker,
    observe,
    wait_for_lease_surrender,
    wait_for_reacquisition,
    wait_until_claimed,
)

pytestmark = pytest.mark.substrate

#: The claim has to happen before anything can be killed. `quiet_substrate`
#: has already proved a worker has capacity, so this only has to cover one poll
#: interval plus scheduling margin.
CLAIM_TIMEOUT_SECONDS = POLL_SECONDS + OBSERVATION_MARGIN_SECONDS


def _container_for(owner: str) -> str:
    """`CED_WORKER_ID` is the container's own name minus Compose's decoration."""
    return f"deploy-{owner}-1"


def _restart(container: str) -> None:
    """Put the killed worker back, and fail loudly here if it does not come.

    Returning quietly on failure is what turned a restart problem into a
    reacquisition failure in a later test.
    """
    docker("start", container)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if container_is_running(container):
            return
        time.sleep(0.5)
    pytest.fail(
        f"{container} did not return to running within 60 s; the two-worker "
        "precondition is broken for every later check"
    )


def test_the_running_workers_poll_the_partition_the_fixtures_insert_at(
    running_workers: list[str],
) -> None:
    """The deployment and this suite must agree on the pool class.

    `pending_step` inserts at `CONTAINER_POOL_CLASS` and nothing else does, so
    if the workers polled a different class every check in this file would wait
    out its timeout and report a reacquisition failure — a broken partition
    wearing the costume of a broken pool.

    **Read from the running containers, not from `deploy/compose.yaml`.** The
    first version parsed the file, which cannot catch the realistic failure: a
    container keeps the environment it was created with, so a stack brought up
    before the value changed keeps polling the old class while the file reads
    correctly and the guard stays green. `docker inspect` is what the
    containers are actually doing.
    """
    for container in running_workers:
        result = docker(
            "inspect",
            "-f",
            "{{range .Config.Env}}{{println .}}{{end}}",
            container,
        )
        assert result.returncode == 0, result.stderr
        configured = next(
            (
                line.split("=", 1)[1]
                for line in result.stdout.splitlines()
                if line.startswith("CED_POOL_CLASS=")
            ),
            None,
        )
        assert configured == CONTAINER_POOL_CLASS, (
            f"{container} is running with CED_POOL_CLASS={configured!r} but this "
            f"suite inserts at {CONTAINER_POOL_CLASS!r}; every check here would "
            "wait out its timeout and blame the pool. Recreate the stack — "
            "editing deploy/compose.yaml does not change a running container."
        )


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
        f"{reacquired.epoch}). Criterion bound {WORST_CASE_SECONDS} s; bound "
        f"derivable from the timings {DERIVED_REACQUISITION_BOUND_SECONDS} s."
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

    # `docker kill --signal=TERM`, **not** `docker stop`. `docker stop` blocks
    # until the container exits, so a clock started after it returns begins
    # once the drain is already over — measured at 0.16 s with the container
    # gone. `docker kill --signal=TERM` returns in 0.06 s with the container
    # still running, so the interval below starts at signal delivery and the
    # drain is inside what is measured. This is the difference between an
    # assertion that bounds the drain and one that bounds the survivor's poll.
    signalled_at = time.monotonic()
    signalled = docker("kill", "--signal=TERM", victim)
    assert signalled.returncode == 0, signalled.stderr

    try:
        # Clause 1 — the lease is surrendered without waiting out a heartbeat.
        surrender, seen = wait_for_lease_surrender(
            owner_conn,
            step_id,
            first_owner,
            POOL_HEARTBEAT_SECONDS + OBSERVATION_MARGIN_SECONDS,
            signalled_at,
        )
        surrendered_at = signalled_at + surrender
        # Clause 2 — reacquisition within one poll interval *of that surrender*.
        reacquired, elapsed = wait_for_reacquisition(
            owner_conn,
            step_id,
            first_owner,
            REACQUIRE_BOUND_SECONDS + OBSERVATION_MARGIN_SECONDS,
            started=surrendered_at,
        )
    finally:
        _restart(victim)

    assert reacquired.owner != first_owner
    # Each clause against its own bound. The arithmetic that has to hold, and
    # which round 4 broke in both directions: clause 1 asserts under 20 with a
    # 40 s timeout, clause 2 asserts at most 30.5 with a 50 s timeout — every
    # helper timeout strictly above the bound asserted after it, so the
    # assertion reds before the helper does.
    assert surrender < POOL_HEARTBEAT_SECONDS, (
        f"the lease stopped being held {surrender:.1f} s after SIGTERM "
        f"(observed as {seen!r}), which is a whole heartbeat "
        f"({POOL_HEARTBEAT_SECONDS} s) or more — the drain waited rather than "
        "acting on the signal"
    )
    # **`OBSERVER_STEP_SECONDS`, not `OBSERVATION_MARGIN_SECONDS`.** Round 4
    # added the 20 s scheduling headroom to this assertion while leaving the
    # helper's timeout at the same total, so every value the helper could
    # return satisfied it and AC-0011's own 30 s was asserted nowhere — the
    # round-1 defect, reintroduced by the commit that was fixing its twin. The
    # only slack an assertion may carry is the observer's own poll step.
    assert elapsed <= REACQUIRE_BOUND_SECONDS + OBSERVER_STEP_SECONDS, (
        f"reacquisition took {elapsed:.1f} s after the surrender, outside "
        f"AC-0011's one poll interval ({REACQUIRE_BOUND_SECONDS} s) even "
        f"allowing the observer's {OBSERVER_STEP_SECONDS} s poll step"
    )
    qualifier = (
        "the surrender itself"
        if seen == "surrendered"
        else "reacquisition, so this bounds the drain AND the survivor's poll "
        "together and the drain's own tight bound is the in-process check"
    )
    print(
        f"\nAC-0011 clause 1: {first_owner}'s lease stopped being held "
        f"{surrender:.2f} s after SIGTERM — observed as {qualifier} "
        f"(bound: under one heartbeat, {POOL_HEARTBEAT_SECONDS} s)."
        f"\nAC-0011 clause 2: {reacquired.owner} reacquired step {step_id} "
        f"{elapsed:.1f} s later (bound: one poll interval, "
        f"{REACQUIRE_BOUND_SECONDS} s)."
        f"\nEnd-to-end {surrender + elapsed:.1f} s, reported not asserted."
    )


def test_a_step_is_claimed_by_exactly_one_worker_at_a_time(
    owner_conn: psycopg.Connection,
    running_workers: list[str],
    pending_step: tuple[UUID, UUID],
) -> None:
    """One owner recorded on the row, and a renewal rather than a re-take.

    **This does not establish mutual exclusion.** `steps.owner` is a single
    column, so "carries exactly one owner" cannot fail once an owner exists,
    and nothing here observes whether two workers are executing the same step.
    What it does establish is that a fresh step is claimed at epoch 1 and that
    across a heartbeat the owner and epoch are unchanged while
    `lease_expires_at` advances — a renewal, not a re-take. Review round 1
    corrected an earlier docstring and ledger entry that claimed more.
    """
    _run_id, step_id = pending_step

    claimed = wait_until_claimed(owner_conn, step_id, CLAIM_TIMEOUT_SECONDS)

    assert claimed.owner in ("worker-a", "worker-b")
    assert claimed.epoch == 1, "a fresh step should be claimed at epoch 1"
    # Poll for the renewal rather than sleeping past one cadence. A fixed
    # sleep(25) against a 20 s heartbeat on a Docker host is the shape that
    # fails once a quarter and gets rerun instead of diagnosed.
    deadline = time.monotonic() + 3 * POOL_HEARTBEAT_SECONDS
    later = observe(owner_conn, step_id)
    while time.monotonic() < deadline:
        later = observe(owner_conn, step_id)
        if later.lease_expires_at > claimed.lease_expires_at:
            break
        time.sleep(1)
    else:
        pytest.fail("the heartbeat did not renew the lease")

    assert later.owner == claimed.owner, "ownership oscillated across a renewal"
    assert later.epoch == claimed.epoch, "the lease was re-taken, not renewed"
    assert later.lease_expires_at > claimed.lease_expires_at
