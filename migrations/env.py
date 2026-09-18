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
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, text

from ced.adapters.postgres.dsn import database_url

#: Alembic speaks SQLAlchemy; psycopg3 is the driver the application uses, so
#: the migration path uses the same one rather than a second client library.
_DRIVER_SCHEME = "postgresql+psycopg://"


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
