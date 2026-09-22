"""Close `agent_role` and `integration_registry` to the shapes r5 ratifies.

Revision ID: 0003
Revises: 0002
Created: 2026-09-21

The delta is
`docs/architecture/role-configuration-seams/role-configuration-seams.md` § 5,
ratified 2026-09-21. Revision 0001 created both tables empty and said a sibling
spec would fill them; this is that sibling's schema half. Six compile-time
guards read attributes no column carried.

**Every added column is nullable or defaulted, and that is a constraint rather
than a preference.** `ALTER TABLE … ADD COLUMN … NOT NULL` without a default
errors on a non-empty table, which is why revision 0002's `owner_scope`
widening used `NOT NULL DEFAULT 'default'`. Both tables are empty today, so
there is no backfill; the defaults exist so the `ADD COLUMN` succeeds and so a
populated table would take the same statements unchanged.

**`integration_registry.tools` is the one exception: nullable with no
default.** § 5 states the reason and it is not an oversight to repair. A
default of `'[]'` would make every row inserted without it *born valid and
unloadable* — valid to the database, refused by the loader, and contributing
nothing to the tool surface AC-0233 enumerates through
`list_integration_tools()`. Nullable-with-no-default makes the omission visible
where it happens.

**The primary-key widening is not a plain `ADD COLUMN`.** `DROP CONSTRAINT`
then `ADD PRIMARY KEY` over columns that already exist rewrites no heap: it
takes an `ACCESS EXCLUSIVE` lock on `integration_registry` and builds a unique
index under it. On today's empty table that is instant. On a populated one the
operator-facing cost is the lock, not a rewrite — every read and every write
against the table waits for the index build. Acquiring that lock is bounded rather than
indefinite — `migrations/env.py` sets a `lock_timeout` and records what
happens when it fires. Either way a failure here leaves the old single-column
key in place and the revision unapplied, never a table with no key at all.

**No grants.** Revision 0001 already carries
`GRANT SELECT ON agent_role, integration_registry, entitlements TO app_api,
app_worker`, and a column added to a table inherits the table-level grant.
Adding one here would widen nothing and would suggest the existing grant is
per-column, which it is not.

`config` is left in place, unread and deprecated, superseded by the shaped
columns below. Dropping it is a later contract change, and there is nothing to
migrate out of it: the table is empty.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── `agent_role`: what the six compile-time guards read ─────────────────
    # r5 § 6 gives the record as `model_settings → model id, temperature,
    # max_tokens, usage limits`. The shape is
    #   {"model_id": str,
    #    "settings": {"max_tokens": int, "temperature": float,
    #                 "thinking": False},
    #    "limits":   {"per_request_input_tokens_limit": int,
    #                 "input_tokens_limit": int, "request_limit": int,
    #                 "tool_calls_limit": int}}
    # `model_id` is required and a record without it fails to load; the default
    # below exists only so the `ADD COLUMN` succeeds, never as a usable value.
    op.execute("""
        ALTER TABLE public.agent_role
            ADD COLUMN model_settings jsonb NOT NULL DEFAULT '{}'::jsonb
    """)

    # A closed-set name, not r5 § 4's content hash: the hash needs the
    # object-store write path `walking-skeleton-step-lifecycle` introduces, and
    # ADR-0006 D2 records the deviation. The set has two members here,
    # `reference-selection` and `finding-set`; the compiler owns membership,
    # because a CHECK would need a migration every time a sibling spec adds a
    # member and the compiler must refuse a non-member in any case.
    op.execute("""
        ALTER TABLE public.agent_role
            ADD COLUMN output_schema_ref text NOT NULL DEFAULT 'finding-set'
    """)

    # Read by nothing in this spec. Taken now because r5 § 6 ratifies it and
    # the column is free on an empty table.
    op.execute("ALTER TABLE public.agent_role ADD COLUMN display_name text")

    # ── The `ceiling` entry shape, and a correction to revision 0001 ────────
    # **No DDL change: the column already exists.** Revision 0001 created
    # `ceiling jsonb NOT NULL`, and what this revision settles is the shape of
    # its entries, which is a loader-and-compiler contract rather than a
    # column:
    #
    #     [{integration_name, integration_version, tool_name, predicates}]
    #
    # The canonical empty value is `[]`. `{}`, `null`, an absent key or any
    # other non-array fails to load and is never coerced — role class is
    # derived from the ceiling's emptiness, so coercion would silently
    # reclassify an analysis role as quarantined.
    #
    # **`predicates`' encoding is out of scope here**, along with
    # `arg_schema` and `ceiling_fragment` below. They are read by the decision
    # point's predicate and by r5 § 2 R5's re-verification, both owned by
    # `walking-skeleton-authority-containment`. Only the *binding* fields are
    # fixed here: `integration_name`, `integration_version`, `tool_name`.
    #
    # Revision 0001's comment on this column said the predicate shape was
    # `walking-skeleton-role-compilation`'s. It is not — the predicate half
    # moved to `walking-skeleton-authority-containment` — and the ratified
    # design § 8 assigns that correction to this spec, so 0001's comment was
    # amended in the same change rather than left standing beside this one.
    # Editing it rewrites no history: the text is a SQL comment inside a
    # `CREATE TABLE` string, discarded by Postgres, so nothing about what ran
    # differs. A stale pointer left in the shipped file is the real cost.

    # ── `integration_registry`: r5 § 4's registry block ─────────────────────
    # `version` first, because the widened primary key below needs it. r5 § 4
    # calls the identifier `integration_id`; the shipped column is
    # `integration_name`, and the column name governs.
    op.execute("""
        ALTER TABLE public.integration_registry
            ADD COLUMN version integer NOT NULL DEFAULT 1
    """)

    # Read by `walking-skeleton-authority-containment`, and `arg_schema` by
    # `walking-skeleton-step-lifecycle`'s AC-0248. Their encodings are that
    # spec's; this revision provides the columns r5 § 4 ratifies.
    op.execute("""
        ALTER TABLE public.integration_registry
            ADD COLUMN arg_schema jsonb NOT NULL DEFAULT '{}'::jsonb
    """)
    op.execute("""
        ALTER TABLE public.integration_registry
            ADD COLUMN ceiling_fragment jsonb NOT NULL DEFAULT '{}'::jsonb
    """)

    # Three fields Phase 1 never reads, added nullable. `AGENTS.md`
    # § Cut before adding exempts an explicit accepted requirement, and r5 § 4
    # makes `credential_scope` load-bearing for the least-privilege posture. A
    # registry half-matching its ratified shape is what produced the sibling
    # spec's AC-0248 defect.
    for column in ("kind", "adapter_ref", "connection_ref", "credential_scope"):
        op.execute(f"ALTER TABLE public.integration_registry ADD COLUMN {column} text")

    # Pool-class names. An empty array means available to every class, which is
    # why the default is `'[]'` and not null: the compiler refuses a role whose
    # integrations are not all available to its `pool_class`, and "available
    # everywhere" is the safe reading of a row nobody scoped.
    op.execute("""
        ALTER TABLE public.integration_registry
            ADD COLUMN pool_classes jsonb NOT NULL DEFAULT '[]'::jsonb
    """)

    # **Nullable, with no default.** See the module docstring: the omission has
    # to be visible where it happens, and a `'[]'` default would hide it behind
    # a row the database accepts and the loader refuses.
    op.execute("ALTER TABLE public.integration_registry ADD COLUMN tools jsonb")

    # ── The widened key ─────────────────────────────────────────────────────
    # A ceiling entry's pinned `(integration_name, integration_version)` is the
    # only way a version is selected — there is no "current version" concept,
    # so nothing is ambiguous once a second version of an integration exists.
    # r5 § 4's "a version in use is immutable" needs enforcement this delta
    # does not build; `walking-skeleton-step-lifecycle` owns it, since its
    # AC-0248 depends on it.
    #
    # `DROP CONSTRAINT` then `ADD PRIMARY KEY`, both inside the revision's
    # single transaction. Postgres names the replacement
    # `integration_registry_pkey` again, matching the name it just dropped.
    op.execute("""
        ALTER TABLE public.integration_registry
            DROP CONSTRAINT integration_registry_pkey
    """)
    op.execute("""
        ALTER TABLE public.integration_registry
            ADD PRIMARY KEY (integration_name, version)
    """)


def downgrade() -> None:
    raise NotImplementedError("migrations are expand-only; there is no downgrade path")
