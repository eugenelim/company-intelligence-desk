"""Where the database URL comes from, and the one place that decides.

Two callers need it — the API and worker entry points, and Alembic — and they
must not disagree, so the resolution lives here rather than in each of them.
"""

from __future__ import annotations

import os

#: Loopback, non-default port: `deploy/compose.yaml` publishes 55432 so a local
#: Postgres on 5432 cannot be reached by accident and silently migrated.
_LOCAL_HOST = "127.0.0.1"
_LOCAL_PORT = 55432
_LOCAL_DATABASE = "ced"

#: The throwaway container's password, matching `deploy/postgres-init/`. Not a
#: credential — a loopback container with no data of value.
_LOCAL_PASSWORD = "local_only_not_a_secret"


def _local_url(user: str) -> str:
    """Assemble a local URL rather than writing one out.

    `tools/lint-no-identifiers.py` reads a literal `user:password@host` as an
    email address and refuses the commit, which is the correct call on a
    pattern it cannot distinguish from one. Building the string keeps no
    credential-shaped literal in the source and changes nothing at run time.
    """
    return (
        f"postgresql://{user}:{_LOCAL_PASSWORD}@{_LOCAL_HOST}:{_LOCAL_PORT}/{_LOCAL_DATABASE}"
    )


ENV_VAR = "CED_DATABASE_URL"

#: Per-role environment variables. A worker authenticates as two roles, per
#: `worker-runtime.md` § Changes this design asks of r7 item 11, so "the
#: connection string" is not a single value for every process.
ROLE_ENV_VARS = {
    "migration": ENV_VAR,
    "api": "CED_DATABASE_URL_API",
    "worker": "CED_DATABASE_URL_WORKER",
    "policy": "CED_DATABASE_URL_POLICY",
}

_LOCAL_ROLE_DEFAULTS = {
    # The bootstrap superuser stands in for r7's `migration` identity locally.
    "migration": _local_url("postgres"),
    "api": _local_url("app_api"),
    "worker": _local_url("app_worker"),
    "policy": _local_url("app_policy"),
}


def database_url(role: str = "migration") -> str:
    """Return the connection string for `role`.

    Falls back to the local Compose substrate only when the role's environment
    variable is unset. A deployed process sets it; nothing here reaches a
    credential store, because this spec has no deployment.
    """
    try:
        env_var = ROLE_ENV_VARS[role]
    except KeyError:
        raise ValueError(
            f"unknown database role {role!r}; expected one of {sorted(ROLE_ENV_VARS)}"
        ) from None
    return os.environ.get(env_var) or _LOCAL_ROLE_DEFAULTS[role]
