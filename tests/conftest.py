"""Shared fixtures. The substrate-backed suites all need the same connections.

Every suite marked `substrate` needs `deploy/compose.yaml` up and migrations
applied. Nothing here starts containers: a test that silently provisions its
own infrastructure hides how long the real bring-up takes and what it needs.
`AGENTS.md` § The local substrate carries the two commands.
"""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from ced.adapters.postgres.dsn import database_url

#: The database roles this spec's code authenticates as.
ROLES = ("migration", "api", "worker", "policy")


def _connect(role: str) -> psycopg.Connection:
    return psycopg.connect(database_url(role))


@pytest.fixture(scope="session")
def require_substrate() -> None:
    """Skip a substrate suite with an actionable reason, never a bare error."""
    try:
        with _connect("migration") as conn:
            conn.execute("SELECT 1 FROM alembic_version")
    except psycopg.Error as exc:
        pytest.skip(
            "substrate unavailable — run "
            "`docker-compose -f deploy/compose.yaml up -d` and "
            f"`./.venv/bin/alembic upgrade head` first ({exc.__class__.__name__})"
        )


@pytest.fixture
def owner_conn(require_substrate: None) -> Iterator[psycopg.Connection]:
    """A connection as the bootstrap identity, for setup and for reading."""
    with _connect("migration") as conn:
        yield conn


@pytest.fixture
def api_conn(require_substrate: None) -> Iterator[psycopg.Connection]:
    with _connect("api") as conn:
        yield conn


@pytest.fixture
def worker_conn(require_substrate: None) -> Iterator[psycopg.Connection]:
    with _connect("worker") as conn:
        yield conn


@pytest.fixture
def policy_conn(require_substrate: None) -> Iterator[psycopg.Connection]:
    with _connect("policy") as conn:
        yield conn
