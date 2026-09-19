-- Provisioning, not migration: the roles the application authenticates as, and
-- the schema they share. Runs once, from the Postgres image's init hook.
--
-- The role set is runtime-architecture.md § Identity — two layers, restricted
-- to the identities this spec's code actually uses. Deliberately absent:
--   `policy-author`  human-operated; r7 states no runtime identity holds it
--   `egress-proxy`, `ui`, `ingress`  hold no database authority at all
--   `migration`      stood in for locally by the container's bootstrap
--                    superuser, which is the substitution this file records
--
-- The passwords are local-only literals for a throwaway container on a
-- loopback port. Nothing here is a real credential.

CREATE ROLE ced_owner NOLOGIN;

-- Owns `fence_step`, and nothing else. NOLOGIN and granted to no application
-- role, so no runtime identity can authenticate as it — which is the whole
-- point: a function's owner can always DROP or ALTER it, so the fence must not
-- be owned by the role it constrains. See ADR-0004.
CREATE ROLE ced_fence NOLOGIN;

CREATE ROLE app_api    LOGIN PASSWORD 'local_only_not_a_secret';
CREATE ROLE app_worker LOGIN PASSWORD 'local_only_not_a_secret';
CREATE ROLE app_policy LOGIN PASSWORD 'local_only_not_a_secret';

-- No role may create objects in `public`; the schema is owned and granted
-- explicitly. Without this every login role could create a shadowing object.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO ced_owner;
GRANT USAGE ON SCHEMA public TO app_api, app_worker, app_policy, ced_fence;

-- The bootstrap superuser runs migrations and must be able to act as the
-- owner, so that every object a migration creates is owned by `ced_owner`
-- rather than by the superuser. `migrations/env.py` issues `SET ROLE`.
GRANT ced_owner TO postgres;

-- Revision 0002 assigns `fence_step` to `ced_fence`. Postgres requires the role
-- performing `ALTER FUNCTION ... OWNER TO` to be a member of the incoming
-- owner, so the membership is a provisioning fact and lives here. It grants
-- `ced_owner` nothing it did not already hold: it owns every object already.
--
-- Deliberately NOT `GRANT app_worker TO ced_owner`. An earlier version of this
-- file had it, so `ced_owner` could assign the fence to `app_worker` — and that
-- membership also let the owner-definer functions read an `app_worker` session's
-- temporary tables, which was half of how the `pg_temp` capture reached the
-- real event log. Review round 1 removed both.
GRANT ced_fence TO ced_owner;
