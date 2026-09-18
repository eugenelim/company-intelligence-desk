"""AC-0001 — a run starts over HTTP and is readable in state `requested`."""

from __future__ import annotations

import uuid

import psycopg
import pytest

from .conftest import Client

pytestmark = pytest.mark.substrate


def test_post_runs_returns_an_identifier_and_the_run_is_readable(
    api_server: Client, clean_runs: None
) -> None:
    """AC-0001, end to end over the wire."""
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})

    assert created.status == 201, created.body
    run_id = created.body["run_id"]
    assert uuid.UUID(run_id)
    assert created.body["seq"] == 1

    snapshot = api_server.get(f"/runs/{run_id}/snapshot")

    assert snapshot.status == 200, snapshot.body
    assert snapshot.body["state"] == "requested"
    assert snapshot.body["run_id"] == run_id
    assert snapshot.body["as_of_seq"] == 1


def test_the_run_requested_event_is_readable_with_the_envelope_r7_specifies(
    api_server: Client, clean_runs: None
) -> None:
    """The event log is the system of record; the snapshot projects over it."""
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    page = api_server.get(f"/runs/{run_id}/events")

    assert page.status == 200, page.body
    assert page.body["run_id"] == run_id
    assert len(page.body["events"]) == 1
    event = page.body["events"][0]
    assert event["type"] == "run.requested"
    assert event["seq"] == 1
    assert event["principal"] == "operator"
    assert event["schema_version"] == 1
    # Null on the run-lifecycle path, per the r7 envelope: the event is
    # appended before any step is leased.
    assert event["step_id"] is None
    assert event["agent_role"] is None


def test_the_coordinator_step_exists_and_is_runnable(
    api_server: Client, owner_conn: psycopg.Connection, clean_runs: None
) -> None:
    """A run with no coordinator step is a run nothing will ever claim."""
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})

    row = owner_conn.execute(
        "SELECT step_id, state, agent_role, pool_class FROM steps WHERE run_id = %s",
        (uuid.UUID(created.body["run_id"]),),
    ).fetchall()

    assert len(row) == 1
    step_id, state, agent_role, pool_class = row[0]
    assert str(step_id) == created.body["step_id"]
    assert state == "runnable"
    assert agent_role == "coordinator"
    # r7 change 3: one class in MVP, so the claim predicate is a no-op until
    # the day it is not.
    assert pool_class == "default"


def test_the_cursor_is_the_clients_and_after_is_honoured(
    api_server: Client, clean_runs: None
) -> None:
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    assert api_server.get(f"/runs/{run_id}/events?after=0").body["events"]
    assert api_server.get(f"/runs/{run_id}/events?after=1").body["events"] == []


def test_an_unknown_run_is_404_not_an_empty_page(api_server: Client) -> None:
    """An empty page would read as "this run has no events yet", which is a
    different fact from "there is no such run"."""
    missing = uuid.uuid4()

    assert api_server.get(f"/runs/{missing}/snapshot").status == 404
    assert api_server.get(f"/runs/{missing}/events").status == 404


def test_a_malformed_body_is_refused(
    api_server: Client, owner_conn: psycopg.Connection
) -> None:
    """422, per the contract, and no run is created.

    The second clause is asserted rather than stated. It was stated only, in a
    suite whose standard is recording what a check does not establish.
    """
    before = owner_conn.execute("SELECT count(*) FROM runs").fetchone()

    assert api_server.post("/runs", {"principal": ""}).status == 422
    assert api_server.post("/runs", {}).status == 422

    assert owner_conn.execute("SELECT count(*) FROM runs").fetchone() == before


def test_a_malformed_run_id_is_refused_rather_than_looked_up(
    api_server: Client,
) -> None:
    assert api_server.get("/runs/not-a-uuid/snapshot").status == 422


def test_an_out_of_range_cursor_is_refused(api_server: Client, clean_runs: None) -> None:
    """The contract bounds `after` and `limit`; the served routes must too."""
    created = api_server.post("/runs", {"principal": "operator", "agent_role": "coordinator"})
    run_id = created.body["run_id"]

    assert api_server.get(f"/runs/{run_id}/events?after=-1").status == 422
    assert api_server.get(f"/runs/{run_id}/events?limit=0").status == 422
    assert api_server.get(f"/runs/{run_id}/events?limit=1001").status == 422


def test_the_api_identity_cannot_reach_a_model_or_forge_a_decision(
    api_server: Client, clean_runs: None
) -> None:
    """A structural check on the served surface, not on the grants.

    The grant tests in `tests/event_log` assert what the database refuses this
    role. This asserts the complementary fact about the HTTP surface: there is
    no route through which a client could ask the API to append anything but
    the two run-lifecycle types, because no such route exists.
    """
    served = api_server.get("/openapi.json").body

    assert sorted(served["paths"]) == [
        "/runs",
        "/runs/{run_id}/events",
        "/runs/{run_id}/snapshot",
    ]
