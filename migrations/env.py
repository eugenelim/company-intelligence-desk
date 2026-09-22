"""Alembic environment. Expand-only, and online-only.

**No downgrade is offered.** Migrations are expand-only by the plan's § Data &
schema: every revision adds, and nothing contracts. A generated `downgrade()`
that silently passes is worse than none, because it makes `alembic downgrade`
look supported while doing nothing — so each revision's `downgrade()` raises,
and the failure names the reason.

**Migrations run as `ced_owner`.** The bootstrap identity connects and then
`SET ROLE`s, so every object a revision creates is owned by the schema owner
rather than by whoever happened to run the migration. Without this, object
ownership would depend on the operator's identity and the `SECURITY DEFINER`
functions in revision 0002 would run with the wrong privileges.

**Migrations wait a bounded time for a lock, then fail.** Revision 0003's
primary-key widening takes `ACCESS EXCLUSIVE` on `integration_registry` and
builds a unique index under it. Without a `lock_timeout` that statement waits
as long as it takes: on a populated live database it queues behind any open
reader, and because a pending `ACCESS EXCLUSIVE` request blocks every request
behind it, the whole table stalls for as long as that one reader lives. On a
`restart: "no"` fleet the visible symptom is a deploy that never finishes and
that somebody unblocks by hand.

A bounded wait fails instead, and that is the better failure. The upgrade runs
inside one transaction this module commits explicitly, so a timeout rolls the
whole thing back and leaves the database exactly at the previous revision —
nothing is half-applied. Migrations are expand-only and re-runnable, so the
operator retries when the table is quiet. Postgres raises `55P03
lock_not_available`, which names contention rather than a schema fault, so the
failure says which of the two it is.

The value is fixed rather than configurable, under the rule the closed sets in
`vocabulary.py` and `roles.py` already follow: one place a reviewer can see it
change. It bounds lock *acquisition* only — a slow index build under a lock
already held is a different problem, and no `statement_timeout` is set here.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, text

from ced.adapters.postgres.dsn import database_url

#: Alembic speaks SQLAlchemy; psycopg3 is the driver the application uses, so
#: the migration path uses the same one rather than a second client library.
_DRIVER_SCHEME = "postgresql+psycopg://"

#: How long a migration waits to acquire a lock before Postgres aborts the
#: statement with `55P03 lock_not_available`. Five seconds is long enough to
#: pass through ordinary short reads and short enough that a deploy blocked by
#: a long-lived one fails while an operator is still watching it.
_LOCK_TIMEOUT = "5s"


def _engine_url() -> str:
    url = database_url("migration")
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return _DRIVER_SCHEME + url[len(prefix) :]
    return url


def run_migrations_online() -> None:
    engine = create_engine(_engine_url(), future=True)
    with engine.connect() as connection:
        connection.execute(text("SET ROLE ced_owner"))
        # `set_config` rather than `SET`, because `SET` takes no bind
        # parameter for its value and this keeps the timeout out of the SQL
        # text. `false` for the third argument makes it session-scoped, so it
        # covers every revision and not only the statement after it.
        connection.execute(
            text("SELECT set_config('lock_timeout', :timeout, false)"),
            {"timeout": _LOCK_TIMEOUT},
        )
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
        # Explicit, and load-bearing. The `SET ROLE` above autobegins a
        # transaction, so alembic's own `begin_transaction` nests inside it and
        # commits nothing on exit. Without this line `alembic upgrade head`
        # exits 0 having rolled every revision back — which it did, once, and
        # is why T3's check asserts the schema rather than the exit code.
        connection.commit()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit(
        "offline mode is not supported: revision 0002 sets function ownership, "
        "which needs a live connection to check. Run `alembic upgrade head` "
        "against the database."
    )

run_migrations_online()
