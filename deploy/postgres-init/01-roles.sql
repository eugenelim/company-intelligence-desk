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

CREATE ROLE app_api    LOGIN PASSWORD 'local_only_not_a_secret';
CREATE ROLE app_worker LOGIN PASSWORD 'local_only_not_a_secret';
CREATE ROLE app_policy LOGIN PASSWORD 'local_only_not_a_secret';

-- No role may create objects in `public`; the schema is owned and granted
-- explicitly. Without this every login role could create a shadowing object.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
ALTER SCHEMA public OWNER TO ced_owner;
GRANT USAGE ON SCHEMA public TO app_api, app_worker, app_policy;

-- The bootstrap superuser runs migrations and must be able to act as the
-- owner, so that every object a migration creates is owned by `ced_owner`
-- rather than by the superuser. `migrations/env.py` issues `SET ROLE`.
GRANT ced_owner TO postgres;
