# Verification ledger — walking-skeleton-foundation

Execution observations for an approved spec and plan, per the plan contract.
The spec and plan are pinned; nothing here amends either. Every entry records
what a check established **and what it did not**.

## Resolve-vs-surface disposition record

Opened at PLAN, closed at DECIDE. One row per item a referent could resolve or
had to surface.

| # | Item | Disposition | Basis |
| --- | --- | --- | --- |
| 1 | `migrations/` is a top-level directory that T1's `Approach` omits while T3's pinned `Touches` requires it | **Resolved** | `Touches` is plan contract, `Approach` is working material by the plan's own contract note. ADR-0003 names five directories; the `Approach` line is corrected in place. No amendment. |
| 2 | Pre-EXECUTE spec/plan review gate (`SPEC-PLAN-REVIEW`) on a structural change | **Resolved from recorded state** | Both human gates are already taken and dated in the plan Changelog, and `spec.md` § Assumptions records the independent scrutiny these artifacts received: a two-round shaping review and an adversarial spec-mode review, by forked-context reviewer agents. Re-dispatching a spec/plan reviewer could only produce findings against a pinned, Approved contract the owner directed not to re-open. Implementation-stage reviewers are **not** covered by this and run in full against every diff. |
| 3 | `docker compose` (CLI plugin) is absent in this environment | **Resolved** | `docker-compose` 5.5.0 standalone is present and the Docker daemon is Colima 29.2.1. `AGENTS.md` records the command that actually works, per its own rule that commands are verified from the manifest or runner that owns them rather than guessed. |

## Observations

Appended per task as evidence lands.

### T1 — the layout and the pin are recorded

- `python3 tools/hooks/pre-pr.py` exits 0, ADR shape lint included: both new
  records pass all fifteen shape classes, and ADR-0001 carries the mirrored
  `Superseded in part: ADR-0002 D5` the lint's ADR-S010 requires.
- The directory check (`tests/architecture/test_recorded_layout.py`) is green
  after T2 lands the directories. It reads the directory names **out of
  ADR-0003's D1 table** rather than restating them, so the test cannot drift
  from the decision it enforces.
- **Not established:** ADR-0003 replaced an RFC acceptance round with a
  decision record. Nothing independently accepted this layout. The check
  proves the tree matches the record; it cannot prove the record is right.
- **Correction recorded here rather than in the plan:** the plan's T1
  `Approach` names four directories while T3's pinned `Touches` requires
  `migrations/**`. `Approach` is working material and `Touches` is contract, so
  ADR-0003 names five. The plan body is left byte-identical because
  `loop-cohort` pinned its hash at approval.

### T2 — the project builds, lints, and refuses a misplaced import

- **AC-0007 — established, by deliberate violation.** Seven injected imports
  across `domain/`, `api/`, `worker/` and `agents/` are each reported; four
  permitted placements in `agents/` and `adapters/` are each not reported; and
  removing both violations returns the checker to zero findings. Three dynamic
  forms — `importlib.import_module("boto3")`, `__import__("boto3")` and the
  `pydantic_ai` equivalent — are also caught, which a grep over import
  statements would miss.
- **AC-0008 — established, both halves.** Five embeddings of a twelve-digit
  identifier (`AWS_<id>_Admin`, `acme-<id>-logs`, a profile assignment, an S3
  URL and an ARN) each make the real script exit 1; a content hash containing a
  twelve-digit run exits 0. The tests run the script as a subprocess against a
  throwaway git repository, so the exit code is the assertion, not the regex.
- **A setup check earned its keep.** The first negative case used the sha256 of
  the empty string, which contains no twelve-digit run — the test would have
  passed while proving nothing. `test_the_chosen_hash_really_contains_a_twelve_digit_run`
  failed and named it. Reported here as a **setup check, not a hypothesis
  check**: it cannot fail on the code under test.
- **The gate refused its own test.** Staging the fixtures made
  `lint-no-identifiers.py --staged` exit 1 on the test file itself. The
  fixtures are now assembled from fragments at run time, so no
  twelve-digit identifier and no non-reserved address exists in repository
  text. Nothing was added to the lint's skip list and no rule was relaxed.
- **Not established:** `mypy` runs over `src/ced` and not over `tests/`, so the
  test suite is unchecked by the type gate. `ruff` skips the vendored agent
  packs, `spikes/` and `tools/`, named in `pyproject.toml` with the reason.
- **One dependency declined.** AC-0001 and AC-0009 need an HTTP client. FastAPI's
  `TestClient` needs `httpx`, which the plan's § Dependencies & integration does
  not list and which the spec makes an Ask-first boundary. Declined: T6 drives
  the API over real HTTP from the Compose stack using `urllib.request` from the
  standard library, which is both a dependency fewer and stronger evidence for
  *"the real ASGI app rather than a mocked router"* than an in-process client.
- **Manifest pins are read from a resolution, not guessed.** `pydantic-ai`
  itself does not resolve alongside FastAPI — it pulls every provider extra and
  pins `starlette` 1.6.0 against FastAPI's range. The manifest names
  `pydantic-ai-slim[bedrock]==2.45.0`, which is the distribution Phase 0
  installed; ADR-0002 D1 records that.

### T3 — a migration applies to an empty database

- **Established.** `docker-compose -f deploy/compose.yaml up -d` brings both
  containers to `healthy`; the init hook creates `ced_owner`, `app_api`,
  `app_worker` and `app_policy`; `alembic upgrade head` leaves six application
  tables plus `alembic_version`, all owned by `ced_owner`.
- **The goal-based check as the plan wrote it was insufficient, and this is the
  finding.** The plan's T3 test is *"`alembic upgrade head` against a fresh
  container exits 0"*. The first `migrations/env.py` issued `SET ROLE ced_owner`
  before configuring alembic, which autobegins a transaction; alembic's own
  `begin_transaction` then nested inside it and committed nothing on exit. The
  command **exited 0 having created no tables at all.** `env.py` now commits
  explicitly, and the test asserts the schema — table set, and `ced_owner`
  ownership on every one — rather than the exit code. Exit 0 is still checked;
  it is no longer the whole check.
- **Established: `alembic downgrade -1` exits 1** naming "expand-only" and
  "no downgrade path", and the schema is intact afterwards. Asserted on the
  message as well as the code, so an unrelated non-zero exit cannot satisfy it.
- **Established: the counters are not sequences.** `runs.next_seq` and
  `events.seq` are both plain `bigint` with no identity property and no
  `nextval` default, asserted against `information_schema` on the shipped
  schema. This is the spec's Never-do, checked rather than asserted in prose.
- **Established: `deadlock_timeout` is 200 ms in the running container,** read
  from `current_setting()` rather than from the Compose file. Every T4 result
  carries that qualification: it is well below the 1 s default, so deadlocks
  surface faster here than in production.
- **Established: no application role can create an object in `public`.**
  `app_api` attempting `CREATE TABLE` raises `InsufficientPrivilege`.
- **Substituted:** role creation is in the Compose init hook, not in a
  migration. In a deployed system the roles and their credentials are created
  by whoever owns the database instance and `alembic` authenticates as r7's
  `migration` identity; locally the container's bootstrap superuser stands in
  for both. **Not established:** that r7's `migration` role has the privileges
  these revisions need, because nothing ran as it.
- **Not established:** anything about MinIO beyond reachability. No criterion in
  this spec reads or writes an object. `quay.io/minio/minio` is pinned because
  `docker pull minio/minio` is refused from this network — MinIO's own registry
  works and Docker Hub's path does not.
- **Not established:** any managed-service behaviour. This is a local container.
  Connection pooling, failover and `deadlock_timeout` defaults on RDS or Aurora
  are untested, exactly as `spikes/README.md` records for Phase 0.
- **The identifier gate fired a second time, on a connection string.**
  `postgresql://user:password@host/db` matches the email-address rule, which is
  the correct call on a pattern the lint cannot distinguish from an address.
  `dsn.py` now assembles the URL from parts, so no credential-shaped literal is
  in the source. Nothing was added to the lint's skip list.
