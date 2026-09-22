"""T3 — a migration applies to an empty database and leaves a usable schema.

The plan states this as a goal-based check: `alembic upgrade head` exits 0.
That turned out to be insufficient — the first version of `migrations/env.py`
ran every revision inside a transaction it never committed, so the command
exited 0 having created nothing. The check therefore asserts the *schema*, and
the exit code is only one of the things it asserts.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
import threading
import warnings
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from ced.adapters.postgres.dsn import database_url

#: An unjoined copy of the name `migrations/env.py` reads. That module runs
#: the migration at import time, so it cannot be imported to share a constant.
#: `test_an_override_that_disables_the_bound_is_refused` is the check that
#: reds on a rename — the override check cannot, because a renamed variable
#: simply leaves the default in force, which is a value it has to tolerate.
_LOCK_TIMEOUT_ENV_VAR = "CED_MIGRATION_LOCK_TIMEOUT"

#: How long a probe reader is held once the run that must outlast it starts.
#: Above the 5 s default so that default gives up inside the window, and far
#: below the override under test so the override does not.
_RELEASE_AFTER = 12.0

#: A backstop on every probe reader, so a check that dies without releasing
#: cannot leave a session holding a lock on the substrate.
_HOLD_CEILING = 300.0

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


@pytest.mark.parametrize("role", ["api", "worker"])
def test_each_reading_role_can_open_a_connection_and_read(
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


def _alembic(
    *args: str,
    env: dict[str, str] | None = None,
    unset: tuple[str, ...] = (),
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the real `alembic` console script from the project's environment.

    `timeout` is what lets a check assert that a migration *stops*. Without
    one, a revision waiting on a lock it will never get hangs the suite
    instead of failing it.

    `unset` removes a variable the runner may have exported. Merging over
    `os.environ` cannot express absence, so a check asserting a *default*
    would otherwise certify whatever the developer happened to have set.
    """
    child = {**os.environ, **(env or {})}
    for name in unset:
        child.pop(name, None)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=None if env is None and not unset else child,
        timeout=timeout,
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


#: The canonical event-type shape, declared once here so the two revisions that
#: each spell it can be joined to a single expectation. Deliberately **not**
#: imported by the migrations: adjudication established that a shared
#: definition read by historical revisions breaks the self-containment an
#: applied migration depends on, and that the join belongs in a check instead —
#: which is exactly the seam review round 1 built for `RUN_LIFECYCLE_TYPES`.
EXPECTED_TYPE_SHAPE = r"^[a-z0-9]+(\.[a-z0-9]+)+$"

#: The whole constraint expression, as PostgreSQL deparses it. Compared for
#: **equality**, which is the only assertion that excludes a widening this
#: delivery has not thought of.
#:
#: Round 7 pinned the pattern operand plus a scan for further accepting terms,
#: and round 8 broke it: a `CASE WHEN … THEN true ELSE type ~ '<shape>' END`
#: carries exactly one operand and none of the scanned tokens, so it shipped
#: green while admitting anything the arm matched. The scan was a seven-token
#: denylist — the shape rounds 3 through 5 rejected for the type rule itself,
#: reintroduced as the fix for it. Equality has no complement to enumerate.
#:
#: The cost, accepted rather than discovered later: this couples to the
#: deparser's `::text` cast and parenthesisation, so a server upgrade that
#: changes either reds this check. That is affordable because the image is
#: digest-pinned in `deploy/compose.yaml`, and a formatting red is loud and
#: one-line to resolve, where a widening that ships green is neither.
EXPECTED_CONSTRAINT_DEF = "CHECK ((type ~ '" + EXPECTED_TYPE_SHAPE + "'::text))"


def test_the_type_shape_is_one_rule_in_the_column_and_in_the_append_function(
    owner_conn: psycopg.Connection,
) -> None:
    """The shape rule is written twice; this is what holds the copies together.

    **Three separate findings converge here, and a substring test satisfied
    none of them.** The previous check asserted `"a-z0-9" in <definition>`,
    which stays green under a rule widened to admit spaces or uppercase — so
    the claim that the guarantee was "asserted structurally" rested on an
    assertion that could not discriminate the shipped rule from a broken one.
    It also never established that the constraint was on `events.type` at all:
    the catalogue query matched on name alone, so a constraint moved to another
    relation or column passed.

    **Round 7 found the replacement was a substring test too**, one level up:
    `<shape> in definition` detects an *edit* to the pattern but never an
    *addition* beside it, so `CHECK (type ~ '<shape>' OR type ~ '^[a-z0-9_]+$')`
    — and even `OR type <> 'zzz'`, admitting every string but one — shipped
    green, with the column pins untouched because a disjunct on `type` alone
    satisfies them.

    **Round 8 broke that replacement too**, and the fix is the third attempt:
    pinning the operand plus scanning for further accepting terms was itself a
    seven-token denylist — the shape rounds 3 through 5 rejected for the type
    rule — and a `CASE WHEN … THEN true ELSE type ~ '<shape>' END` carries one
    operand and none of the scanned tokens. The constraint's whole expression is
    now compared for **equality**, which has no complement to enumerate.

    So what this check pins, exactly and no more: the constraint is a CHECK on
    `public.events`; it covers exactly the `type` column; its expression equals
    `EXPECTED_CONSTRAINT_DEF`; and `events.type` is `NOT NULL`, which is the
    only layer refusing a null type. Then the append function's refusal operand
    must equal the same shape — **and this leg reads the whole `prosrc`,
    comments included**, so it establishes that the function mentions exactly
    that one pattern, not that the executed guard is unwidened. The behavioural
    table in `tests/event_log/test_definer_hardening.py` is what covers the
    guard's actual reach. The drift this leg does catch is the tightening
    direction, where the function admits a type the column refuses and the
    `CheckViolation` reaches the caller past the adapter's `CED01` filter.

    What it does **not** establish: that the regex means what it reads as.
    That is an assumption about the Postgres engine, narrowed by the round-6
    security pass and recorded as open.
    """
    row = owner_conn.execute(
        """
        SELECT pg_get_constraintdef(c.oid), array_length(c.conkey, 1), a.attname
          FROM pg_constraint c
          JOIN pg_attribute a
            ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
         WHERE c.conname = 'events_type_is_canonical'
           AND c.conrelid = 'public.events'::regclass
           AND c.contype = 'c'
        """
    ).fetchone()
    assert row is not None, (
        "no CHECK constraint named events_type_is_canonical on public.events — "
        "the reserved-type rule is then only as complete as the trim class, "
        "which is the defect rounds 4 and 5 both found"
    )
    definition, columns, column_name = row
    assert columns == 1 and column_name == "type", (
        f"the constraint covers {columns} column(s) including {column_name!r}; "
        "it must constrain events.type and nothing else"
    )
    # **Equality on the whole expression.** Nothing weaker survives: round 7's
    # operand pin plus a token scan was defeated by a `CASE` arm carrying one
    # operand and no scanned token. See `EXPECTED_CONSTRAINT_DEF`.
    assert definition == EXPECTED_CONSTRAINT_DEF, (
        f"the shipped constraint is {definition!r}, not {EXPECTED_CONSTRAINT_DEF!r}. "
        "Any difference is either a widening — which reopens the bypass class "
        "rounds 3 through 5 closed — or a deparser change on a server upgrade; "
        "check which before relaxing this assertion"
    )
    # The column's `NOT NULL` is the only layer that refuses a null type: both
    # guards in `append_step_event` test the canonicalised value, and null
    # canonicalises to null, so neither `IF` fires. Pinned here because it was
    # the one layer doing real work with nothing holding it.
    notnull = owner_conn.execute(
        "SELECT attnotnull FROM pg_attribute "
        "WHERE attrelid = 'public.events'::regclass AND attname = 'type'"
    ).fetchone()
    assert notnull == (True,), (
        "events.type is nullable; a null argument passes both of "
        "append_step_event's guards, so this constraint is what stops it"
    )

    body = owner_conn.execute(
        "SELECT prosrc FROM pg_proc p JOIN pg_namespace n "
        "ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public' AND p.proname = 'append_step_event'"
    ).fetchone()
    assert body is not None, "append_step_event is absent"
    # The *refusing statement's* operand, not the pattern's presence anywhere
    # in the body — `prosrc` includes the comments, so the previous
    # containment check stayed green whenever any comment quoted the canonical
    # pattern, and a guard widened to `!~ '<shape>' AND lower(p_type) !~ '...'`
    # passed it too. Requiring exactly one `!~` operand reds on both.
    refusing = re.findall(r"!~ '((?:[^']|'')*)'", body[0])
    assert refusing == [EXPECTED_TYPE_SHAPE], (
        f"append_step_event's refusal operands are {refusing!r}, not exactly "
        f"[{EXPECTED_TYPE_SHAPE!r}]; a type the function admits and the column "
        "rejects reaches the caller as an unmapped CheckViolation"
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
    with _probe_database("ced_migration_probe") as probe_url:
        _replay_provisioning(probe_url)

        before = _table_names(probe_url)
        assert before == set(), f"the probe database was not empty: {before}"

        result = _alembic("upgrade", "head", env={"CED_DATABASE_URL": probe_url})
        assert result.returncode == 0, result.stderr

        after = _table_names(probe_url)
        assert EXPECTED_TABLES <= after, (
            f"upgrade head exited 0 but left {sorted(after)} — the "
            "commit-nothing defect this check exists for"
        )


def test_a_migration_blocked_by_a_reader_aborts_rather_than_queueing(
    require_substrate: None,
) -> None:
    """The bounded lock wait `migrations/env.py` sets, observed end to end.

    Revision 0003 takes `ACCESS EXCLUSIVE` on `integration_registry`. With no
    `lock_timeout` that statement queues behind any open reader for as long
    as the reader lives, and because a pending `ACCESS EXCLUSIVE` request
    blocks everything behind it, the whole table stalls with it. The
    behaviour that replaces it has three parts and each is asserted: the
    migration stops, it says contention rather than a schema fault, and it
    leaves the database exactly where it started.

    **The subprocess timeout is the assertion, not a safety net.** Remove the
    bounded wait and this check does not fail on a wrong value — it hangs on
    a reader the check itself is holding, which is precisely the production
    symptom, so the timeout is what turns that symptom into a red.
    """
    with _probe_database("ced_lock_timeout_probe") as probe_url:
        _replay_provisioning(probe_url)

        at_0002 = _alembic("upgrade", "0002", env={"CED_DATABASE_URL": probe_url})
        assert at_0002.returncode == 0, at_0002.stderr
        assert "tools" not in _column_names(probe_url, "integration_registry")

        with psycopg.connect(probe_url) as reader:
            # An ordinary read. `ACCESS SHARE` is the weakest table lock there
            # is and conflicts with nothing except `ACCESS EXCLUSIVE`, so this
            # is the cheapest thing a live system could be doing that revision
            # 0003 has to wait for.
            # The connection is not in autocommit, so the read below opens
            # the transaction and holds ACCESS SHARE until this block exits.
            # An explicit BEGIN here only draws "there is already a
            # transaction in progress" from Postgres.
            reader.execute("SELECT count(*) FROM integration_registry")

            try:
                blocked = _alembic(
                    "upgrade",
                    "head",
                    env={"CED_DATABASE_URL": probe_url},
                    # The shipped default is what this check certifies, so the
                    # runner's own value must not stand in for it.
                    unset=(_LOCK_TIMEOUT_ENV_VAR,),
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                pytest.fail(
                    "alembic upgrade head did not return while a reader held "
                    "ACCESS SHARE — the migration is queueing on the lock "
                    "instead of giving up, which is the stalled deploy "
                    "migrations/env.py's lock_timeout exists to prevent"
                )

            assert blocked.returncode != 0, (
                "the migration succeeded while a reader held ACCESS SHARE, "
                "which revision 0003's ADD COLUMN cannot do"
            )
            # Named, because an operator has to tell this apart from a schema
            # fault: the two need opposite responses, a retry and a fix.
            assert "lock timeout" in blocked.stderr.lower(), blocked.stderr

            # Nothing half-applied. `env.py` runs the whole upgrade in one
            # transaction it commits explicitly, so the abort takes every
            # revision in flight with it. Both halves are read: the recorded
            # revision, and a column 0003 adds — a stamp without the DDL and
            # DDL without the stamp are different failures.
            assert _current_revision(probe_url) == "0002"
            assert "tools" not in _column_names(probe_url, "integration_registry")

        retried = _alembic(
            "upgrade",
            "head",
            env={"CED_DATABASE_URL": probe_url},
            unset=(_LOCK_TIMEOUT_ENV_VAR,),
        )
        assert retried.returncode == 0, retried.stderr
        assert _current_revision(probe_url) == "0003"
        assert "tools" in _column_names(probe_url, "integration_registry"), (
            "the retry exited 0 without applying 0003 — a bounded wait that "
            "makes the migration unrunnable rather than retryable is not the "
            "bargain env.py records"
        )


def test_the_lock_timeout_override_reaches_the_migration_session(
    require_substrate: None,
) -> None:
    """`CED_MIGRATION_LOCK_TIMEOUT` is documented to operators, so it is held.

    `AGENTS.md` § The local substrate tells an operator to reach for this
    variable when a maintenance migration needs a longer window than the
    default. A misspelt name, a misread of `os.environ`, or a value clamped
    on the way to the session would leave that guidance pointing at nothing
    while every other gate stayed green.

    **The reader is retired on a clock that starts when the widening run
    does**, and that is what isolates the variable. Both runs meet a reader
    already holding the lock; the reader then goes away after
    `_RELEASE_AFTER`, which is longer than the 5 s default and far shorter
    than the override. So the default must give up and the override must
    wait it out, and a build that ignores the variable fails the second leg.

    Two earlier versions of this check did not isolate anything. The first
    retired the reader *before* the widening run, so that run succeeded
    whatever the variable did. The second retired it on a fixed deadline
    from the start of the check, so a slow first leg could consume the whole
    window and hand the second leg an uncontended lock.
    """
    with _probe_database("ced_lock_override_probe") as probe_url:
        _replay_provisioning(probe_url)
        assert _alembic("upgrade", "0002", env={"CED_DATABASE_URL": probe_url}).returncode == 0

        holding = threading.Event()
        release = threading.Event()
        retired = threading.Event()

        def hold() -> None:
            with psycopg.connect(probe_url) as reader:
                reader.execute("SELECT count(*) FROM integration_registry")
                holding.set()
                release.wait(timeout=_HOLD_CEILING)
            retired.set()

        keeper = threading.Thread(target=hold, daemon=True)
        keeper.start()
        try:
            assert holding.wait(timeout=30), "the probe reader never took its lock"

            # Leg 1, the control: the shipped default against a reader that
            # outlives it must give up. Without this the second leg could be
            # succeeding because the contention was never real.
            impatient = _alembic(
                "upgrade",
                "head",
                env={"CED_DATABASE_URL": probe_url},
                unset=(_LOCK_TIMEOUT_ENV_VAR,),
                timeout=120,
            )
            assert not retired.is_set(), (
                "the probe reader went away before the default run finished, "
                "so this leg proved nothing about the default's window"
            )
            assert impatient.returncode != 0, (
                "the shipped default applied the migration through a reader "
                "held longer than it — the contention this check needs is not "
                "happening"
            )
            assert "lock timeout" in impatient.stderr.lower(), impatient.stderr
            assert _current_revision(probe_url) == "0002"

            # Leg 2: the same held reader, retired on a timer that starts now.
            # The default would abort inside that window; the override must
            # not, so the variable is the only difference between the legs.
            timer = threading.Timer(_RELEASE_AFTER, release.set)
            timer.start()
            try:
                patient = _alembic(
                    "upgrade",
                    "head",
                    env={"CED_DATABASE_URL": probe_url, _LOCK_TIMEOUT_ENV_VAR: "30min"},
                    timeout=120,
                )
            finally:
                timer.cancel()

            assert patient.returncode == 0, (
                "the override did not widen the window: this run met the same "
                "reader the default gave up on, and gave up too, so the value "
                f"is not reaching the migration session.\n{patient.stderr}"
            )
            assert _current_revision(probe_url) == "0003"
        finally:
            release.set()
            keeper.join(timeout=30)


@pytest.mark.parametrize("disabling", ["0", "0s", "0ms"])
def test_an_override_that_disables_the_bound_is_refused(
    require_substrate: None, disabling: str
) -> None:
    """`0` means *disabled* to Postgres, not *no wait*, and that is the trap.

    An operator reaching for the usual "0 is unlimited" convention, or a
    deploy template filling an empty variable with a zero, would restore the
    unbounded wait the timeout exists to remove — and Postgres would accept
    it silently, because the syntax is valid. The refusal names the variable,
    and it fires before any revision runs.

    Every spelling Postgres normalises to zero is covered, because refusing
    the literal `"0"` alone would be a string test wearing a rule's clothes.
    """
    refused = _alembic(
        "upgrade",
        "head",
        env={_LOCK_TIMEOUT_ENV_VAR: disabling},
        timeout=120,
    )

    assert refused.returncode != 0
    assert _LOCK_TIMEOUT_ENV_VAR in refused.stderr, refused.stderr
    assert "disabled lock timeout" in refused.stderr, refused.stderr


def test_the_disabling_refusal_fires_before_the_migration_takes_a_lock(
    require_substrate: None,
) -> None:
    """Ordering, observed rather than inferred.

    "Refused before any revision runs" is the whole value of the guard: a
    refusal that arrives *after* the upgrade has queued on `ACCESS EXCLUSIVE`
    has already taken the unbounded wait the setting exists to remove, and on
    a populated database that is the stalled deploy, refusal or no refusal.

    Exit code and message cannot see the difference — a guard moved below
    `run_migrations()` still exits non-zero with the same text, because the
    transaction rolls back. What separates them is whether the run *returns*
    while a reader holds the lock. So this holds one and gives the subprocess
    a budget far below any wait it could otherwise sit in.
    """
    with _probe_database("ced_lock_ordering_probe") as probe_url:
        _replay_provisioning(probe_url)
        assert _alembic("upgrade", "0002", env={"CED_DATABASE_URL": probe_url}).returncode == 0

        holding = threading.Event()
        release = threading.Event()

        def hold() -> None:
            with psycopg.connect(probe_url) as reader:
                reader.execute("SELECT count(*) FROM integration_registry")
                holding.set()
                release.wait(timeout=_HOLD_CEILING)

        keeper = threading.Thread(target=hold, daemon=True)
        keeper.start()
        try:
            assert holding.wait(timeout=30), "the probe reader never took its lock"
            try:
                refused = _alembic(
                    "upgrade",
                    "head",
                    env={"CED_DATABASE_URL": probe_url, _LOCK_TIMEOUT_ENV_VAR: "0"},
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                pytest.fail(
                    "the disabling refusal did not return while a reader held "
                    "the lock: the upgrade reached a revision and queued on "
                    "ACCESS EXCLUSIVE before refusing, which is the unbounded "
                    "wait the refusal exists to prevent"
                )

            assert refused.returncode != 0
            assert "disabled lock timeout" in refused.stderr, refused.stderr
            assert _current_revision(probe_url) == "0002"
        finally:
            release.set()
            keeper.join(timeout=30)


def _current_revision(url: str) -> str | None:
    """The revision Alembic records for a database, or `None` if it has none."""
    with psycopg.connect(url) as conn:
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    return None if row is None else str(row[0])


def _column_names(url: str, table: str) -> set[str]:
    """Every column on one table, for asserting a revision did or did not land."""
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        ).fetchall()
    return {row[0] for row in rows}


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


@contextlib.contextmanager
def _probe_database(stem: str) -> Iterator[str]:
    """Create a throwaway database for one check, and reclaim it afterwards.

    **The name carries the process id**, because every check here opens by
    dropping the name it is about to use: a second `pytest` session against
    the same substrate would otherwise drop the first's database mid-check
    and red it with an unrelated message.

    **The drop is forced**, because `DROP DATABASE` is refused while any
    session is connected and these checks hold readers on purpose. Without
    it a reader that outlives its join turns teardown into an `ObjectInUse`
    raised from a `finally`, which replaces whatever actually failed —
    losing the diagnosis and leaking the database for the next run.
    """
    name = f"{stem}_{os.getpid()}"
    _require_local_substrate()
    with psycopg.connect(database_url("migration"), autocommit=True) as admin:
        admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        admin.execute(f"CREATE DATABASE {name}")
    try:
        yield database_url("migration").rsplit("/", 1)[0] + "/" + name
    finally:
        try:
            with psycopg.connect(database_url("migration"), autocommit=True) as admin:
                admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
        except psycopg.Error as exc:  # pragma: no cover - teardown only
            # Never from a bare `finally`: an exception here would mask the
            # assertion that brought us to it.
            warnings.warn(f"probe database {name} was left behind: {exc}", stacklevel=2)


def _replay_provisioning(url: str) -> None:
    """Give a throwaway database the owner and grants the migration expects.

    The roles are cluster-wide, but the schema owner's grants are not, so a
    fresh database has no `ced_owner` to `SET ROLE` to until the provisioning
    file the container init hook runs is replayed into it.

    Comment lines are stripped *before* splitting on `;`. Splitting first
    leaves each comment attached to the statement that follows it, which
    Postgres then tries to parse as SQL.
    """
    init_sql = (REPO_ROOT / "deploy" / "postgres-init" / "01-roles.sql").read_text()
    bare = "\n".join(
        line
        for line in init_sql.splitlines()
        if line.strip() and not line.strip().startswith("--")
    )
    with psycopg.connect(url, autocommit=True) as probe:
        for statement in (s.strip() for s in bare.split(";")):
            if statement:
                probe.execute(_classify_provisioning(statement))


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

    **Refuses rather than resolves, and the difference matters.** An earlier
    version tested whether the string contained
    `@127.0.0.1:55432/`, which cannot constrain where a connection goes: the
    literal can be carried inside a parameter value, and a later `host=`
    keyword overrides a loopback-looking authority. Both shapes passed the
    substring test while resolving off-box, after which this check would have
    run `CREATE`/`DROP DATABASE` there.

    This check does **not** resolve where libpq will land: `conninfo_to_dict`
    applies no environment defaults and reads no service file. What it does is
    refuse whenever anything that could retarget the connection invisibly to
    the DSN is present — `hostaddr` or `service` in the DSN, and `PGHOSTADDR`,
    `PGSERVICE` or `PGSERVICEFILE` in the environment. The round-7 security
    review established that those five are the complete set: `PGHOST` and
    `PGPORT` are overridden by an explicit DSN and fail closed when the DSN
    omits them, `PGSYSCONFDIR` is inert with no service requested, and the
    session-attribute and load-balance variables can only reorder hosts the
    DSN already lists. So the enumeration is closed rather than open-ended,
    which is what distinguishes it from the character denylists rounds 3
    through 5 rejected for the type rule.

    `database_url` honours `$CED_DATABASE_URL`, and the only other precondition
    proves merely that something answers on it. `AGENTS.md` § Development
    workflow requires confirmation before a destructive operation, and a test
    cannot ask — so this fails closed, including when the target cannot be
    established at all.
    """
    from psycopg.conninfo import conninfo_to_dict

    from ced.adapters.postgres.dsn import LOCAL_HOST, LOCAL_PORT

    try:
        resolved = conninfo_to_dict(database_url("migration"))
    except Exception as exc:  # noqa: BLE001 — an unparseable DSN fails closed
        pytest.skip(f"refusing cluster DDL: the target DSN did not parse ({exc})")

    # Any parameter that can redirect the connection is refused outright
    # rather than interpreted. `hostaddr` is the one that defeated the previous
    # version: libpq uses `host` only for authentication and TLS once
    # `hostaddr` is present, so
    # `postgresql://.../ced?hostaddr=<remote>` parses to `host='127.0.0.1'`
    # with the real target in a key this check never read — measured, and it
    # passed the guard. `service=` is refused for the adjacent reason: the
    # service file is not resolved here, so it can supply a `hostaddr` this
    # process never sees.
    #
    # Refusing beats resolving. The tempting alternative — connect and ask the
    # server where it is — does not work: `inet_server_addr()` on the
    # legitimate local substrate returns the container's bridge address
    # (measured as 172.18.0.3), not a loopback, so a guard requiring loopback
    # from the server's own view would refuse the one target this check is for.
    # **The environment, which libpq reads and the parsed DSN never shows.**
    # Round 5 closed the DSN-carried spellings and left these, on a recorded
    # ground that turned out to be wrong: the fix was said to need the
    # effective target resolved, when this guard's own principle — refusing
    # beats resolving — closes it for the same cost as the DSN check three
    # lines down. Measured before the fix: with `PGHOSTADDR` exported,
    # `conninfo_to_dict` reports `host='127.0.0.1'` with no `hostaddr` key at
    # all, every condition below passes, and the `CREATE`/`DROP DATABASE` runs
    # against wherever that variable points. The realistic victim is not an
    # attacker but a developer with one of these set for an unrelated cluster.
    for variable in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"):
        if os.environ.get(variable):
            pytest.skip(
                f"refusing cluster DDL: ${variable} is set, and libpq honours "
                "it at connect time without it appearing in the DSN this "
                "guard parses, so the target cannot be established from the "
                "DSN alone"
            )

    for redirecting in ("hostaddr", "service"):
        if resolved.get(redirecting):
            pytest.skip(
                f"refusing cluster DDL: the DSN carries `{redirecting}`, which "
                "can send this connection somewhere other than the host named "
                "in it, so the target cannot be established from the DSN alone"
            )

    host, port = resolved.get("host"), resolved.get("port")
    if host != LOCAL_HOST or str(port) != str(LOCAL_PORT):
        pytest.skip(
            "refusing CREATE/DROP DATABASE against a non-local target: this "
            f"check only runs against {LOCAL_HOST}:{LOCAL_PORT}, the throwaway "
            f"substrate in deploy/compose.yaml, and this DSN resolves to "
            f"{host}:{port}"
        )


def test_the_policy_role_can_connect_and_is_refused_every_read(
    policy_conn: psycopg.Connection,
    owner_conn: psycopg.Connection,
) -> None:
    """`policy-writer` gets no read at all, per r7's Layer-1 identity table.

    It grants that role "`runs.next_seq` bump + insert `policy.decision` events
    **only**", with no read column — and r4 item 1 chose the definer fence so it
    "gains no table access at all". An earlier version of the schema granted it
    `SELECT` on all six tables, which is what let it read the `lease_epoch` the
    fence compares (ADR-0005). The connection must still open, because the
    worker boot sequence verifies it.
    """
    assert policy_conn.execute("SELECT session_user").fetchone() == ("app_policy",)

    # Read from the catalogue, not from a hand-kept tuple. The tuple listed
    # five of the six tables — `integration_registry` was missing, and it is
    # granted in the same statement as the two that were present, so the one
    # gate that exists to catch a re-grant to this role could not have caught
    # it there. ADR-0005's confirmation signal is "refused `SELECT` on every
    # table"; deriving the list is what makes that literally what runs.
    tables = [
        row[0]
        for row in owner_conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename <> 'alembic_version' ORDER BY tablename"
        ).fetchall()
    ]
    assert len(tables) == 6, (
        f"expected the six application tables, found {tables} — this check "
        "asserts a refusal per table and must not silently cover fewer"
    )

    for table in tables:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            policy_conn.execute(f"SELECT count(*) FROM {table}")
        policy_conn.rollback()
