"""T3 — a migration applies to an empty database and leaves a usable schema.

The plan states this as a goal-based check: `alembic upgrade head` exits 0.
That turned out to be insufficient — the first version of `migrations/env.py`
ran every revision inside a transaction it never committed, so the command
exited 0 having created nothing. The check therefore asserts the *schema*, and
the exit code is only one of the things it asserts.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.substrate

#: Every table revision 0001 creates, including the three a sibling spec fills.
EXPECTED_TABLES = frozenset(
    {
        "runs",
        "steps",
        "events",
        "agent_role",
        "integration_registry",
        "entitlements",
    }
)


def test_every_table_exists_and_is_owned_by_the_schema_owner(
    owner_conn: psycopg.Connection,
) -> None:
    """Ownership is not cosmetic.

    Revision 0002's `SECURITY DEFINER` functions run with their owner's
    privileges, so a table owned by whoever happened to run the migration would
    make the privilege split depend on the operator's identity.
    """
    rows = owner_conn.execute(
        """
        SELECT relname, pg_get_userbyid(relowner)
          FROM pg_class
         WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace
        """
    ).fetchall()
    owners = dict(rows)

    assert EXPECTED_TABLES <= owners.keys()
    assert {owners[t] for t in EXPECTED_TABLES} == {"ced_owner"}


def test_the_sequence_counter_is_not_a_bigserial(
    owner_conn: psycopg.Connection,
) -> None:
    """The spec's Never-do, asserted against the shipped schema.

    A `bigserial` would appear as an identity or a sequence default on either
    `runs.next_seq` or `events.seq`. Both must be plain integers whose value a
    rollback undoes.
    """
    rows = owner_conn.execute(
        """
        SELECT table_name, column_name, column_default, is_identity
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND (table_name, column_name) IN
               (('runs', 'next_seq'), ('events', 'seq'))
        """
    ).fetchall()

    assert len(rows) == 2, "both counters must exist"
    for table, column, default, is_identity in rows:
        assert is_identity == "NO", f"{table}.{column} is an identity column"
        assert default is None or "nextval" not in default, (
            f"{table}.{column} defaults to {default!r}, which is a sequence"
        )


def test_no_role_can_create_objects_in_the_public_schema(
    api_conn: psycopg.Connection,
) -> None:
    """Without this, any login role could create a shadowing object."""
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        api_conn.execute("CREATE TABLE shadow_probe (x int)")


@pytest.mark.parametrize("role", ["api", "worker", "policy"])
def test_each_application_role_can_open_a_connection_and_read(
    role: str, request: pytest.FixtureRequest
) -> None:
    """T3's Done when: the next task can open connections against this schema."""
    conn: psycopg.Connection = request.getfixturevalue(f"{role}_conn")

    assert conn.execute("SELECT count(*) FROM runs").fetchone() == (0,)
    assert conn.execute("SELECT current_setting('deadlock_timeout')").fetchone() == ("200ms",)


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the real `alembic` console script from the project's environment."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_upgrade_head_is_idempotent(require_substrate: None) -> None:
    """Re-running the migration is a no-op, not a second application."""
    result = _alembic("upgrade", "head")

    assert result.returncode == 0, result.stderr
    assert _alembic("current").stdout.strip().startswith("0001")


def test_downgrade_is_not_offered(require_substrate: None) -> None:
    """Migrations are expand-only, and the refusal names the reason.

    A generated `downgrade()` that silently passes is worse than none: it makes
    the command look supported while doing nothing. This asserts the exit code
    *and* the message, because a non-zero exit for some unrelated reason would
    otherwise satisfy the check.
    """
    result = _alembic("downgrade", "-1")

    assert result.returncode != 0
    assert "expand-only" in result.stderr
    assert "no downgrade path" in result.stderr


def test_the_schema_survived_the_attempted_downgrade(
    owner_conn: psycopg.Connection,
) -> None:
    """The refusal must abort, not half-apply."""
    present = {
        row[0]
        for row in owner_conn.execute(
            "SELECT relname FROM pg_class "
            "WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace"
        ).fetchall()
    }
    assert EXPECTED_TABLES <= present
