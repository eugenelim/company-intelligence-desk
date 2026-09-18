"""T3 — a migration applies to an empty database and leaves a usable schema.

The plan states this as a goal-based check: `alembic upgrade head` exits 0.
That turned out to be insufficient — the first version of `migrations/env.py`
ran every revision inside a transaction it never committed, so the command
exited 0 having created nothing. The check therefore asserts the *schema*, and
the exit code is only one of the things it asserts.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

from ced.adapters.postgres.dsn import database_url

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


@pytest.mark.parametrize("role", ["api", "worker", "policy"])
def test_no_role_can_create_objects_in_the_public_schema(
    role: str, request: pytest.FixtureRequest
) -> None:
    """Without this, any login role could create a shadowing object.

    Parametrised over all three roles; it covered `api` alone. The role
    revision 0002 transiently grants and revokes `CREATE` for is `ced_fence`
    (ADR-0004), which is `NOLOGIN` and so unreachable by a connection probe —
    `tests/event_log/test_definer_hardening.py` asserts its privilege from the
    catalogue instead.
    """
    conn: psycopg.Connection = request.getfixturevalue(f"{role}_conn")

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("CREATE TABLE shadow_probe (x int)")
    conn.rollback()


@pytest.mark.parametrize("role", ["api", "worker", "policy"])
def test_each_application_role_can_open_a_connection_and_read(
    role: str, request: pytest.FixtureRequest
) -> None:
    """T3's Done when: the next task can open connections against this schema.

    Asserts the read *succeeds*, not that the table is empty. An earlier
    version asserted a count of zero, which coupled it to whatever else had run
    against the shared substrate first — and it duly failed once rows from
    another check were still present.
    """
    conn: psycopg.Connection = request.getfixturevalue(f"{role}_conn")

    row = conn.execute("SELECT count(*) FROM runs").fetchone()
    assert row is not None and row[0] >= 0
    assert conn.execute("SELECT current_setting('deadlock_timeout')").fetchone() == ("200ms",)


def _alembic(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run the real `alembic` console script from the project's environment."""
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=None if env is None else {**os.environ, **env},
    )


def _revision_ids(output: str) -> set[str]:
    """Return the revision identifiers in an `alembic current`/`heads` listing.

    Each line is `<rev> (head)` or `<rev>`, so the identifier is the first
    token. Parsed rather than matched against a literal: an earlier version of
    this test asserted `startswith("0001")` and broke the moment revision 0002
    landed, which is a test pinned to a number nobody meant to freeze.
    """
    return {line.split()[0] for line in output.splitlines() if line.strip()}


def test_upgrade_head_is_idempotent(require_substrate: None) -> None:
    """Re-running the migration is a no-op, not a second application."""
    result = _alembic("upgrade", "head")
    assert result.returncode == 0, result.stderr

    current = _alembic("current")
    heads = _alembic("heads")
    assert current.returncode == 0, current.stderr
    assert _revision_ids(current.stdout) == _revision_ids(heads.stdout)
    assert _revision_ids(heads.stdout), "alembic reports no head revision"


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


def test_the_terminal_index_names_the_same_types_as_the_domain_vocabulary(
    owner_conn: psycopg.Connection,
) -> None:
    """The partial index and the Python set must not drift apart.

    Nothing in this spec appends a terminal event, so neither side has a caller
    that would catch a mismatch. This is what stops the two definitions of
    "terminal" diverging before `walking-skeleton-evidence` relies on both.
    """
    from ced.domain.events import TERMINAL_EVENT_TYPES

    row = owner_conn.execute(
        "SELECT pg_get_indexdef(indexrelid) FROM pg_index "
        "WHERE indexrelid = 'events_terminal_idx'::regclass"
    ).fetchone()
    assert row is not None, "events_terminal_idx is absent"
    definition = row[0]

    for event_type in TERMINAL_EVENT_TYPES:
        assert f"'{event_type}'" in definition, (
            f"{event_type!r} is in TERMINAL_EVENT_TYPES but not in the index"
        )
    # And nothing extra: count the quoted literals in the predicate.
    predicate = definition.split("WHERE", 1)[1]
    assert predicate.count("'") // 2 == len(TERMINAL_EVENT_TYPES), (
        f"the index predicate names types the vocabulary does not: {predicate}"
    )


def test_the_run_lifecycle_function_admits_exactly_the_domain_vocabulary(
    owner_conn: psycopg.Connection,
) -> None:
    """`RUN_LIFECYCLE_TYPES` is re-declared in the migration; join the two.

    The domain module claims to hold "the vocabulary both sides agree on", and
    agreement means checked. `RESERVED_EVENT_TYPE` is checked behaviourally by
    the privilege-split suite and `TERMINAL_EVENT_TYPES` by the index check
    above; this is the third, and it was missing.
    """
    from ced.domain.events import RUN_LIFECYCLE_TYPES

    row = owner_conn.execute(
        "SELECT prosrc FROM pg_proc p JOIN pg_namespace n "
        "ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = 'append_run_event'"
    ).fetchone()
    assert row is not None, "append_run_event is absent"
    predicate = row[0].split("NOT IN (", 1)[1].split(")", 1)[0]

    admitted = {piece.strip().strip("'") for piece in predicate.split(",")}
    assert admitted == set(RUN_LIFECYCLE_TYPES), (
        f"the migration admits {sorted(admitted)} while the domain module "
        f"declares {sorted(RUN_LIFECYCLE_TYPES)}"
    )


def test_the_migration_applies_to_a_database_at_no_revision(
    require_substrate: None, owner_conn: psycopg.Connection
) -> None:
    """QE-05 — every other check here reads a schema it did not create.

    `require_substrate` skips unless `alembic_version` already exists, so
    `upgrade head` is an Alembic-level no-op in this process and the
    commit-nothing defect this module exists for would pass unseen. This
    creates a throwaway database, migrates it from nothing, and asserts the
    tables are there — so a revision that commits nothing reds.
    """
    name = "ced_migration_probe"
    _require_local_substrate()
    # CREATE DATABASE cannot run inside a transaction block.
    with psycopg.connect(database_url("migration"), autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {name}")
        admin.execute(f"CREATE DATABASE {name}")
    try:
        probe_url = database_url("migration").rsplit("/", 1)[0] + "/" + name
        # The roles are cluster-wide, but the schema owner's grants are not:
        # replay the provisioning file so the migration has an owner to
        # SET ROLE to, exactly as the container init hook does.
        init_sql = (REPO_ROOT / "deploy" / "postgres-init" / "01-roles.sql").read_text()
        # Strip comment lines *before* splitting. Splitting first leaves each
        # comment attached to the statement that follows it, which Postgres
        # then tries to parse as SQL.
        bare = "\n".join(
            line
            for line in init_sql.splitlines()
            if line.strip() and not line.strip().startswith("--")
        )
        statements = [s.strip() for s in bare.split(";") if s.strip()]
        with psycopg.connect(probe_url, autocommit=True) as probe:
            for statement in statements:
                probe.execute(_classify_provisioning(statement))

        before = _table_names(probe_url)
        assert before == set(), f"the probe database was not empty: {before}"

        result = _alembic("upgrade", "head", env={"CED_DATABASE_URL": probe_url})
        assert result.returncode == 0, result.stderr

        after = _table_names(probe_url)
        assert EXPECTED_TABLES <= after, (
            f"upgrade head exited 0 but left {sorted(after)} — the "
            "commit-nothing defect this check exists for"
        )
    finally:
        with psycopg.connect(database_url("migration"), autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {name}")


def _table_names(url: str) -> set[str]:
    with psycopg.connect(url) as conn:
        return {
            row[0]
            for row in conn.execute(
                "SELECT relname FROM pg_class "
                "WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace"
            ).fetchall()
        }


#: Provisioning statements that are cluster-scoped, so the cluster already has
#: them and replaying them into the probe database would be wrong. Matched on a
#: normalised prefix, and anything unrecognised **fails the check** rather than
#: being executed — role DDL is cluster-wide, so a statement this filter did
#: not expect would reach the live cluster instead of the throwaway database.
_CLUSTER_SCOPED_PREFIXES = ("CREATE ROLE", "GRANT CED_FENCE TO")

#: Schema-scoped statements that must be replayed into the probe database.
_SCHEMA_SCOPED_PREFIXES = (
    "REVOKE ALL ON SCHEMA",
    "ALTER SCHEMA",
    "GRANT USAGE ON SCHEMA",
    "GRANT CED_OWNER TO",
)


def _classify_provisioning(statement: str) -> str:
    """Return the statement to run, or `SELECT 1` when it is cluster-scoped.

    Fails loudly on anything it does not recognise. The earlier version let any
    unmatched statement through, so a later `ALTER ROLE` or `DROP ROLE` added to
    `01-roles.sql` would have been applied to the live cluster.
    """
    normalised = " ".join(statement.split()).upper()
    if normalised.startswith(_CLUSTER_SCOPED_PREFIXES):
        return "SELECT 1"
    if normalised.startswith(_SCHEMA_SCOPED_PREFIXES):
        return statement
    pytest.fail(
        "unrecognised provisioning statement; classify it as cluster-scoped or "
        f"schema-scoped before this check can replay it: {statement[:90]!r}"
    )


def _require_local_substrate() -> None:
    """Refuse cluster-level DDL unless the target is the local throwaway stack.

    `database_url("migration")` honours `$CED_DATABASE_URL`, and the only other
    precondition proves merely that *something* answers there — so a developer
    with that variable pointed at a shared cluster would have this check
    `CREATE` and `DROP` a database on it. `AGENTS.md` § Development workflow
    requires confirmation before a destructive operation, and a test cannot ask.
    """
    from ced.adapters.postgres.dsn import LOCAL_HOST, LOCAL_PORT

    url = database_url("migration")
    if f"@{LOCAL_HOST}:{LOCAL_PORT}/" not in url:
        pytest.skip(
            "refusing CREATE/DROP DATABASE against a non-local target: this "
            f"check only runs against {LOCAL_HOST}:{LOCAL_PORT}, the throwaway "
            "substrate in deploy/compose.yaml"
        )
