"""Reading role configuration out of Postgres, and refusing a record that lies.

The seams are
`docs/architecture/role-configuration-seams/role-configuration-seams.md` § 2:
`load_role(role_name, version)` for one role and its pinned registry rows, and
`list_roles()` and `list_integration_tools()` for the enumeration AC-0233 makes
by reading the tables rather than from a list held in a suite.

**`decode_role_record` is where every record-shape refusal lives, and
`load_role` calls it.** `load_role` opens its own query and so cannot be handed
a record, which is why the offline criteria are decided against the decode seam
directly. A `load_role` that parsed inline and never called that seam would
ship with every one of those criteria green and the production path unguarded,
so the delegation below is the point and not an implementation detail; the
substrate round-trip drives a malformed record through the real `load_role` to
hold it.

**Refuse, never coerce, and name what failed.** A loader that repaired a
malformed `ceiling` into `[]` would silently reclassify an analysis role as
quarantined, because role class is derived from that emptiness. An operator
reading the failure is the reason each message carries the key, the value or
the row that caused it.

Raw SQL through psycopg3, matching `event_log.py`: the boundary is the SQL, and
these are plain reads against tables both `app_api` and `app_worker` hold
`SELECT` on from revision 0001.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import psycopg

from ced.adapters.postgres.dsn import database_url

__all__ = [
    "TRUST_CLASSES",
    "IntegrationTool",
    "LoadedRole",
    "RoleLoadError",
    "RoleRef",
    "decode_role_record",
    "list_integration_tools",
    "list_roles",
    "load_role",
]

#: The closed set `integration_registry.trust_class` may hold.
#:
#: `worker-runtime.md` r5 § 4's table has four rows in its Declared column:
#: `admitted-types`, `admitted-types` + reference output, `free-text`, and
#: `absent → Not registrable`. **Two of those four are storable values.**
#: "`admitted-types` + reference output" is a rule that applies when
#: admitted-types output contains references — r5 splits the admitted set by
#: whether a minting authority exists — and not a third string anyone would
#: write into a `text NOT NULL` column. `absent` is the table's own name for
#: not being registrable, so it names no value either.
#:
#: The shipped column carries no CHECK and this spec's migration adds none, so
#: the membership test is the loader's and it fails closed: every non-member is
#: refused, including a casing variant and a typo. AC-0203's separate rule
#: refuses the single literal `free-text` on a non-quarantined role, which is a
#: denylist; this is the allowlist underneath it.
TRUST_CLASSES = frozenset({"admitted-types", "free-text"})

#: The columns the role record carries. Selected by name rather than with `*`
#: so a column added by a later revision does not change this record's shape
#: silently.
_ROLE_COLUMNS = (
    "role_name",
    "version",
    "ceiling",
    "pool_class",
    "instructions",
    "model_settings",
    "output_schema_ref",
    "display_name",
    "owner_scope",
)

#: The registry columns. `config` is deprecated and unread — revision 0003's
#: docstring records why it is still there — so it is not selected.
_INTEGRATION_COLUMNS = (
    "integration_name",
    "version",
    "trust_class",
    "kind",
    "adapter_ref",
    "connection_ref",
    "credential_scope",
    "arg_schema",
    "ceiling_fragment",
    "pool_classes",
    "tools",
    "owner_scope",
)


class RoleLoadError(Exception):
    """A stored record cannot be turned into something the compiler may read.

    Distinct from a compile failure. This is the record disagreeing with its
    ratified shape — a missing `model_id`, a `ceiling` that is not an array, a
    `trust_class` outside the closed set, a registry row contributing no tools
    — and it is decidable without a pool configuration or a model. A compile
    failure is the role disagreeing with the pool or with its own bindings.
    """


@dataclass(frozen=True)
class LoadedRole:
    """One role record and the registry rows its `ceiling` pins.

    Both are plain mappings: the compiler takes `role` and `integrations`
    directly, and shaping them into a second type here would put a translation
    between the stored record and the guard that reads it.
    """

    role: Mapping[str, Any]
    integrations: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class RoleRef:
    """A role's identity, which is the pair and never the name alone."""

    role_name: str
    version: int


@dataclass(frozen=True)
class IntegrationTool:
    """One tool on the registry's whole surface.

    The integration's version travels with the name because a ceiling entry
    pins `(integration_name, integration_version)` and there is no "current
    version" concept to fall back on.
    """

    integration_name: str
    integration_version: int
    tool_name: str


def _row_label(record: Mapping[str, Any]) -> str:
    """Name a registry row for a refusal message.

    Uses whatever the row actually carries rather than asserting the key is
    present: this renders a row too malformed to identify properly instead of
    raising a second, less informative error while reporting the first.
    """
    return (
        f"integration_registry row "
        f"({record.get('integration_name')!r}, {record.get('version')!r})"
    )


def _check_integration_record(record: Mapping[str, Any]) -> None:
    """Apply the registry-row refusals, naming the row that failed.

    Shared by `decode_role_record` and `list_integration_tools` so the rule
    holds on the bound subset and on the whole-registry read alike. AC-0273
    states it unqualified, and the row no role binds is the one a bound-only
    guard would miss: it fails nowhere and instead shrinks the tool surface
    AC-0233 believes it enumerated.

    **The element check below is beyond AC-0273**, which enumerates exactly
    the four whole-array shapes above it, and it ships with no criterion of
    its own by owner decision of 2026-09-22. It is here rather than deferred
    because the array's shape and its contents are read on the same line: a
    row storing `[1]` clears all four shapes and reaches
    `IntegrationTool(tool_name=1)` against a field declared `str`, so the
    first observation of a malformed row is a wrongly typed value inside
    AC-0233's enumeration instead of a refusal naming the row.
    """
    # AC-0266. Membership, not a substring or a case-fold: a near-miss of a
    # real member is exactly the value that must be refused.
    trust_class = record.get("trust_class")
    if trust_class not in TRUST_CLASSES:
        raise RoleLoadError(
            f"{_row_label(record)} declares trust_class {trust_class!r}, "
            f"which is not a member of {sorted(TRUST_CLASSES)}"
        )

    # AC-0273. Absent, null, not an array, or an empty array. The column is
    # nullable with no default so the omission arrives here rather than as a
    # row the database made valid on the way in.
    tools = record.get("tools")
    if tools is None:
        raise RoleLoadError(f"{_row_label(record)} has no tools; the column is required")
    if not isinstance(tools, list):
        raise RoleLoadError(
            f"{_row_label(record)} has tools of type {type(tools).__name__}; "
            f"an array of tool names is required"
        )
    if not tools:
        raise RoleLoadError(
            f"{_row_label(record)} has an empty tools array; a row contributing "
            f"no tools is not registrable"
        )

    # Beyond AC-0273. The four shapes above judge the array; this judges what
    # is in it. Refused rather than coerced, and rather than skipped: a
    # loader that dropped the bad entry would shrink the tool surface
    # silently, which is the defect AC-0273 exists to close one level up.
    # The position is in the message because a row may carry many entries and
    # the operator has to find the one that failed.
    for position, tool_name in enumerate(tools):
        if not isinstance(tool_name, str):
            raise RoleLoadError(
                f"{_row_label(record)} has tools[{position}] of type "
                f"{type(tool_name).__name__}; every entry must be a tool name "
                f"string"
            )


def decode_role_record(
    role_record: Mapping[str, Any],
    integration_records: Sequence[Mapping[str, Any]],
) -> LoadedRole:
    """Validate a stored role and its pinned registry rows, or refuse.

    The pure seam. Every record-shape refusal lives here, which is what lets
    each one be decided offline against a record rather than against a
    database. `load_role` queries and then calls this.
    """
    role_label = f"role {role_record.get('role_name')!r} version {role_record.get('version')!r}"

    # AC-0251, load half. The compile-time half — a `model_id` absent from the
    # pool's allowed set — is the compiler's and needs a pool configuration
    # this seam is deliberately not given.
    model_settings = role_record.get("model_settings")
    if not isinstance(model_settings, Mapping):
        raise RoleLoadError(
            f"{role_label} has model_settings of type "
            f"{type(model_settings).__name__}; a JSON object is required"
        )
    if model_settings.get("model_id") is None:
        raise RoleLoadError(f"{role_label} omits model_settings.model_id")

    # AC-0262. `[]` is the canonical empty ceiling and role class is derived
    # from that emptiness, so a coerced value would quietly promote or demote
    # the role. Refused, never repaired.
    if "ceiling" not in role_record:
        raise RoleLoadError(f"{role_label} has no ceiling")
    ceiling = role_record["ceiling"]
    if not isinstance(ceiling, list):
        raise RoleLoadError(
            f"{role_label} has a ceiling of type {type(ceiling).__name__}; "
            f"an array is required and `[]` is the empty ceiling"
        )

    for record in integration_records:
        _check_integration_record(record)

    return LoadedRole(role=role_record, integrations=tuple(integration_records))


def _connect() -> psycopg.Connection[Any]:
    """Open the read connection these three seams share.

    `app_worker`, because compilation happens at step start in the worker.
    Revision 0001 grants `SELECT` on both tables to `app_api` and `app_worker`,
    so the narrower of the two that actually compiles is the one used.
    """
    return psycopg.connect(database_url("worker"))


def _ceiling_pins(role_record: Mapping[str, Any]) -> tuple[tuple[str, int], ...]:
    """Read the `(integration_name, integration_version)` pairs a ceiling pins.

    Tolerant on purpose: this runs *before* `decode_role_record` has passed
    judgement, so a malformed ceiling yields no pins and the refusal still
    comes from the decode seam with its own message. Raising here would move
    the refusal off the seam the criteria are decided against.
    """
    ceiling = role_record.get("ceiling")
    if not isinstance(ceiling, list):
        return ()
    pins: list[tuple[str, int]] = []
    for entry in ceiling:
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("integration_name")
        version = entry.get("integration_version")
        if isinstance(name, str) and isinstance(version, int):
            pins.append((name, version))
    return tuple(dict.fromkeys(pins))


def load_role(role_name: str, version: int) -> LoadedRole:
    """Read one role and the registry rows its ceiling pins, then decode.

    The query selects only the pinned `(integration_name, integration_version)`
    pairs: a ceiling entry is the only way a version is selected, and there is
    no "current version" row to fall back on. A pin that matches no row is not
    refused here — an unresolved binding is a compile error, AC-0260's, and
    refusing it at load time would move a compile failure into the loader.
    """
    with _connect() as conn:
        role_row = conn.execute(
            f"""
            SELECT {", ".join(_ROLE_COLUMNS)}
              FROM agent_role
             WHERE role_name = %s AND version = %s
            """,
            (role_name, version),
        ).fetchone()
        if role_row is None:
            raise RoleLoadError(f"no agent_role row for {role_name!r} version {version}")
        role_record = dict(zip(_ROLE_COLUMNS, role_row, strict=True))

        pins = _ceiling_pins(role_record)
        integration_records: list[Mapping[str, Any]] = []
        if pins:
            integration_rows = conn.execute(
                f"""
                SELECT {", ".join(_INTEGRATION_COLUMNS)}
                  FROM integration_registry
                 WHERE (integration_name, version) IN (
                           SELECT * FROM unnest(%s::text[], %s::integer[])
                       )
                 ORDER BY integration_name, version
                """,
                ([name for name, _ in pins], [v for _, v in pins]),
            ).fetchall()
            integration_records = [
                dict(zip(_INTEGRATION_COLUMNS, row, strict=True)) for row in integration_rows
            ]

    return decode_role_record(role_record, integration_records)


def list_roles() -> tuple[RoleRef, ...]:
    """Every role in `agent_role`, read from the table.

    AC-0233 enumerates by reading the registries rather than from a list held
    in the suite, so this returns identities and not records: the caller loads
    each one through `load_role`, which is where the refusals are.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role_name, version FROM agent_role ORDER BY role_name, version"
        ).fetchall()
    return tuple(RoleRef(role_name=row[0], version=row[1]) for row in rows)


def list_integration_tools() -> tuple[IntegrationTool, ...]:
    """Every tool on the registry's whole surface, read from the table.

    **Spans every row, not the subset some role binds.** AC-0233 enumerates the
    whole tool surface, and AC-0273's rule is applied to each row here as well
    as in the decode seam — an unbound row whose `tools` is null is absent from
    any role's pinned rows, so a bound-only guard would let it contribute
    nothing while this enumeration reported itself complete.
    """
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT {", ".join(_INTEGRATION_COLUMNS)}
              FROM integration_registry
             ORDER BY integration_name, version
            """
        ).fetchall()

    tools: list[IntegrationTool] = []
    for row in rows:
        record = dict(zip(_INTEGRATION_COLUMNS, row, strict=True))
        _check_integration_record(record)
        for tool_name in record["tools"]:
            tools.append(
                IntegrationTool(
                    integration_name=record["integration_name"],
                    integration_version=record["version"],
                    tool_name=tool_name,
                )
            )
    return tuple(tools)
