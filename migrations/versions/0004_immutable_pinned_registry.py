"""Enforce r5 § 4's "a version in use is immutable" on integration_registry.

Revision ID: 0004
Revises: 0003
Created: 2026-09-25

Revision 0003 stated in its docstring that ``integration_registry``'s
"a version in use is immutable" clause "needs enforcement this delta does not
build; `walking-skeleton-step-lifecycle` owns it, since its AC-0248 depends on
it."  This revision discharges that obligation.

**The enforcement seam is a database trigger.** The spec (AC-0264) leaves the
seam to the implementation; a trigger is chosen because it enforces at the
database level, where no application path can bypass it.  An application-level
check would be bypassed by a ``psql`` session, making the immutability
application-enforced rather than database-enforced.

**The trigger runs before UPDATE or DELETE on ``integration_registry``.** It
checks whether any ``agent_role.ceiling`` contains an entry whose
``integration_name`` and ``integration_version`` match the row being modified.
If so, it raises an exception with SQLSTATE ``P0001``.  The trigger function
is ``SECURITY DEFINER``-free: it runs as the calling user, which holds
``SELECT`` on ``agent_role`` by the grant in revision 0001, so the check
succeeds without elevated privilege.

**No grants are added.** The trigger fires for any identity that can update
or delete a row, including the bootstrap superuser (``ced_owner``) that runs
migrations.  The test suite demonstrates non-vacuity by using that identity,
which has full table privileges and is therefore refused by the trigger rather
than by a pre-existing permission denial.

**Why UPDATE and DELETE, not INSERT.** A new row with a new
``(integration_name, version)`` is never pinned: no ``agent_role.ceiling`` can
reference it before it exists.  An INSERT is therefore always safe; only
updates to existing data can breach immutability.

**Why the ``@>`` predicate.** ``agent_role.ceiling`` is a JSONB array of
binding objects, each carrying at least ``integration_name``,
``integration_version``, ``tool_name`` and ``predicates``.  The JSONB
containment operator ``@>`` over arrays checks whether any element of the
left-hand array is a superset of the element on the right.  The right-hand
element contains only ``integration_name`` and ``integration_version``, so it
matches any binding entry for that pair regardless of ``tool_name`` or
``predicates``.
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Trigger function ────────────────────────────────────────────────────
    # Owned by ``ced_owner`` (the migration role), which makes it accessible
    # from the trigger context.  ``SECURITY INVOKER`` (the default) means the
    # SELECT on ``agent_role`` runs as the calling user, who has SELECT on that
    # table from revision 0001.
    #
    # The ERRCODE ``P0001`` is Postgres's "raise_exception" class — it is what
    # a bare ``RAISE EXCEPTION`` produces and is the most explicit "application
    # decided to refuse this" signal available.
    op.execute("""
        CREATE OR REPLACE FUNCTION check_integration_registry_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF EXISTS (
                SELECT 1
                  FROM agent_role
                 WHERE ceiling @> jsonb_build_array(
                           jsonb_build_object(
                               'integration_name', OLD.integration_name,
                               'integration_version', OLD.version
                           )
                       )
            ) THEN
                RAISE EXCEPTION
                    'integration (%, %) is pinned by a ceiling and is immutable',
                    OLD.integration_name, OLD.version
                    USING ERRCODE = 'P0001';
            END IF;
            -- For DELETE triggers NEW is NULL; RETURN OLD allows the delete to
            -- proceed.  For UPDATE triggers RETURN NEW allows the update.
            -- COALESCE handles both operations in one RETURN statement.
            RETURN COALESCE(NEW, OLD);
        END;
        $$
    """)

    # ── Trigger ─────────────────────────────────────────────────────────────
    # BEFORE UPDATE OR DELETE, FOR EACH ROW: fires once per modified row so
    # the trigger can inspect the OLD values and raise before any change lands.
    # BEFORE (not AFTER) so the check runs before the row is written to disk.
    op.execute("""
        CREATE TRIGGER prevent_pinned_registry_rewrite
        BEFORE UPDATE OR DELETE ON integration_registry
        FOR EACH ROW EXECUTE FUNCTION check_integration_registry_immutable()
    """)


def downgrade() -> None:
    raise NotImplementedError("migrations are expand-only; there is no downgrade path")
