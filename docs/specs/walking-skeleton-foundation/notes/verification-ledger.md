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

### T4 — the event log appends densely, fenced, and refuses a forged decision

Twenty-seven hypothesis checks in `tests/event_log`, all green, against the
schema this delivery ships rather than the spike's own.

- **AC-0002 — established.** With the step insert forced to fail by a
  `step_id` that already exists — a real unique violation on the real
  statement — the run row, the step row and the event are all absent, and the
  connection is still usable afterwards. The happy path is asserted alongside
  it so the negative case is not vacuously green. **No failure-injection
  switch ships in production code**; an earlier draft had one in
  `start_run`'s signature and it was removed.
- **AC-0003 — established.** Eight concurrent writers, 25 appends each, on one
  run: 200/200 events, `seq` dense from 1, zero duplicates, `runs.next_seq`
  at 200, zero deadlocks and zero errors. Each writer also runs the claim
  half — `FOR UPDATE SKIP LOCKED` on `steps` — so both paths contend on the
  same rows in the designed order, which is what makes this a lock-ordering
  result and not only an append result.
- **AC-0004 — established.** Three appends at epoch 7 give `seq` 1..3; an
  append at epoch 6 raises `Fenced`; the sequence is still `[1, 2, 3]` and
  `next_seq` is still 3, so the rolled-back attempt consumed no number; and
  the next legitimate append gets 4, not 5. This is the whole reason
  `next_seq` is a row UPDATE.
- **AC-0005 — established, on the shipped schema.** A real `worker`-role
  connection is refused the reserved type with `InsufficientPrivilege`, and the
  message names `app_worker` and not `ced_owner` — `session_user`, which is
  spike P1's finding, pinned. The worker is separately refused `EXECUTE` on the
  policy function, which is what makes the split a split rather than one
  function being polite. `api` is refused both a step event and a decision, and
  is restricted to the two run-lifecycle types; **no role holds a direct
  `INSERT` on `events`**, which is what makes every other refusal load-bearing.
  All three roles can still do their own job, asserted separately.
- **r7 change 1 taken the second way, and checked.** `fence_step` is owned by
  `app_worker`, verified in `pg_proc`, so the fence runs at worker's privilege
  rather than the schema owner's. `app_policy` is refused
  `SELECT ... FOR UPDATE` on `steps` directly, which is the check that the
  fence genuinely had to be a function rather than a grant.
- **AC-0006 — established, SQL level only.** A second `tool.invoked` carrying a
  recorded derived key raises `UniqueViolation`, and consumes no sequence
  number. The index's partiality is checked in both directions: the same key
  under a different type is admitted, several keyless events are admitted, and
  the same key in a different run is admitted. The *behavioural* half — a
  duplicate terminating the step — is `walking-skeleton-agent-runtime`'s, per
  r7 change 2's disposition.
- **The lock-ordering rule is shown failing.** Mixed orders on one
  `(run, step)` pair deadlock. A **uniformly** inverted order does **not** —
  asserted, because Phase 0 sharpened the claim that way and a suite reading
  "inverted order deadlocks" would send a reader after the wrong defect. The
  designed order is clean under the same pressure. A structural check also
  reads both append functions out of `pg_proc` and asserts the fence precedes
  the `runs` allocation, so a future edit cannot silently invert it.
- **Argued, not demonstrated:** spike P2 ran with no second locker on `steps`,
  so `append_policy_decision` taking the fence in the same order as the worker
  path preserves P2's proven ordering by argument. What is demonstrated here is
  that a mixed order still deadlocks and the designed one does not.
- **Not established:** the step-scoped event vocabulary is deliberately not
  enumerated in the schema. The database enforces the negative rules — the
  worker path refuses `policy.decision`, the run-lifecycle path accepts only
  `run.requested` and `run.cancelled` — and an enum frozen now would make each
  new sibling event type a migration against a shipped spec.
- **Not established:** nothing in this spec appends a terminal event.
  `append_run_event` admits exactly r7's two names, so `run.completed` and
  `run.failed` have no writer here; the run state machine that produces them is
  `walking-skeleton-evidence`'s. The terminal index and `is_terminal` exist for
  the reader.
- **Not established:** any managed-service behaviour, and any behaviour at the
  1-second default `deadlock_timeout`. Local container at 200 ms.
- **A revision-pinned test was found and fixed.** `test_upgrade_head_is_idempotent`
  asserted `alembic current` started with `"0001"` and broke the moment
  revision 0002 landed. It now compares `current` against `heads`.

### T6 — a run starts over HTTP and is readable

Seventeen checks in `tests/api`, all green, plus one manual end-to-end run of
the shipped binary.

- **AC-0001 — established, over real HTTP.** `POST /runs` returns 201 with a
  run identifier, a step identifier and `seq` 1; `GET /runs/{id}/snapshot`
  returns state `requested` and `as_of_seq` 1; `GET /runs/{id}/events` returns
  the single `run.requested` event with `step_id` and `agent_role` null, which
  is the r7 envelope on the run-lifecycle path. The coordinator step exists,
  is `runnable`, and carries `pool_class = 'default'`.
- **The harness runs the real server, not an in-process client.** `uvicorn`
  starts the app on a loopback port and the tests drive it with
  `urllib.request`. An in-process client short-circuits the server, so it
  cannot catch a route the server declines to mount or a status the framework
  rewrites on the way out. It also avoids `httpx`, which the plan's dependency
  list does not carry.
- **Manual QA — the shipped artifact, not the test harness.** `./.venv/bin/ced-api`
  was started and driven with `curl`: `POST /runs` → 201 with a UUID,
  `GET .../snapshot` → `{"state":"requested","as_of_seq":1}`,
  `GET .../events` → the one `run.requested` event, and an unknown run → 404
  `{"detail":"no such run"}`. Recorded because a passing unit gate is not
  evidence that the entry point works.
- **A defect was found by doing that.** `run()` hardcoded port 8000, which is
  occupied on this machine; the server reported `[Errno 48]` and shut down
  cleanly, but there was no way to move it. It now reads `CED_API_HOST` and
  `CED_API_PORT`, defaulting to loopback 8000. Two deployables share one
  developer machine, so this was going to be needed regardless.
- **AC-0009 — established, and it caught real drift on its first run.** The
  served `/openapi.json` route table equals the committed contract's: every
  path, method, `operationId`, parameter with its location and required-ness,
  request-body requiredness, and declared response status. The hand-authored
  contract **under-declared 422** on both GET routes, which the surface really
  does serve and which the AC-0001 tests separately assert. The contract was
  corrected; the implementation was right.
- **The contract check is shown failing.** Three mutations of a *copy* of the
  served document — a removed route, a renamed query parameter, and a renamed
  `operationId` — each make the comparison unequal. The mutation is applied to
  the copy rather than to the application, so no mutation switch ships.
- **A setup check is reported separately:** `test_the_contract_file_describes_three_routes`
  guards against both sides of the comparison being empty, which is how a
  contract test most often becomes decorative. It cannot fail on the
  application.
- **Not established, and deliberately so.** The comparison covers the route
  table, not the whole document. FastAPI's generated schema section has a shape
  that is the framework's business; asserting on it would fail on every
  framework upgrade while catching no real drift.
- **Not established:** the events route serves a cursor projection only. Its
  reconnect semantics, the `Last-Event-ID` preference over `after=`,
  keepalives and stream termination are `walking-skeleton-evidence`'s, and
  nothing here exercises them.
- **Not established:** connection pooling. Each request opens a short-lived
  connection, which is honest for a spec with no deployment; r7 § Risks records
  managed-service pooling as untested and this does not change that.
- **One dependency added through the Ask-first boundary.** `pyyaml==6.0.3`,
  test-only, so AC-0009 can read the hand-authored contract; there is no YAML
  parser in the standard library. Owner decision 2026-09-18. No `src/` code
  imports it, which the dependency-direction gate does not police and the
  manifest records.

### T5 — a killed worker loses at most 150 seconds

Four checks in `tests/fault_injection`, all green, driving real containers at
r7's real timings. The suite takes 201 seconds; compressed timings would
demonstrate the mechanism and not the number, and the number is the criterion.

- **AC-0010 — established.** `docker kill` (SIGKILL) on the worker holding the
  step. **Observed: 59.5 s to reacquisition**, with `lease_epoch` advancing
  1 → 2, which is what fences the dead worker out for good. Read from the
  `steps` row, not from a log line: a log line records what a worker believed,
  the row records what happened.
- **The 59.5 s is one observation, not the bound.** 150 s is the worst case —
  TTL 60 + poll 30 + heartbeat 20 — and this run landed well inside it because
  the surviving worker's poll happened to fall shortly after the lease expired.
  A single measurement below a bound does not establish the bound; what is
  established is that recovery happened with no operator action and inside it.
- **AC-0011 — established, and distinct.** `docker stop -t 30` (SIGTERM).
  **Observed: 29.8 s**, inside one 30-second poll interval. A third check
  asserts the drain is *faster* than the 150 s host-loss path, because a drain
  that happened to take 150 s would satisfy AC-0010's bound while telling an
  operator nothing about whether the graceful path works at all.
- **Established: exactly one owner at a time.** With both workers live and
  polling the same class, a fresh step is claimed at epoch 1 by one of them,
  and 25 seconds later the owner and epoch are unchanged while
  `lease_expires_at` has moved forward — so the heartbeat renewed rather than
  the lease being re-taken.
- **Established: the boot sequence verifies both roles before claiming.** Both
  containers log `worker connection verified as app_worker` and `policy
  connection verified as app_policy` before `ready`. A worker that claimed
  before it could finish a step would manufacture a lease expiry and a
  150-second recovery for a problem a readiness check catches in milliseconds.
- **SUBSTITUTED — and this is the important one.** AC-0010's *"no operator
  action"* holds because **a second worker was already running**, not because
  anything replaced the killed one. `restart: "no"` keeps the victim dead so
  the recovery observed is the survivor's. A deployed ECS service with a
  desired count would replace the task; **nothing here does, and nothing here
  measures that replacement or its notice period.** The test restarts the
  container itself, afterwards, so the next check starts from two again.
- **Not established:** anything about Fargate. These are local containers on
  one Docker host. Task replacement timing, the notice period, and the
  behaviour of a killed host rather than a killed process are all untested.
- **Not established:** cancellation. There is no cancellation token and no
  `step_deadline` here — `worker-runtime.md` § The pool owns both, and the
  evidence spec measures them. The heartbeat does read run state in the same
  statement that renews the lease, so the signal a cancelled run would arrive
  on exists; nothing in this spec produces a cancelled run.
- **Not established:** the object store. The boot sequence checks both database
  connections and **not** MinIO. Nothing in this spec reads or writes an
  object, and an S3 client in `worker/` would put the AWS SDK outside
  `adapters/`, which the dependency-direction gate forbids.
- **Not established:** a real step body. The injected body sleeps. That is what
  keeps this suite free of a credential and of spend, and it means nothing here
  exercises a fenced worker abandoning an in-flight model call.

### T7 — the record says what this spec established and what it did not

- **Established.** `python3 .agents/skills/work-loop/scripts/lint-spec-status.py
  --root . --all` is green across all three specs. The script is committed at
  that path, so a clean clone can run it, and `AGENTS.md` names it alongside the
  other gates.
- `docs/architecture/README.md` gains a § What is built table naming the six
  subsystems, where each one lives, and the design section that governs it —
  which is the Durable Outputs closeout condition for Current architecture.
- `spikes/README.md` gains a Phase 1 section separating **what was
  established** (eleven criteria with their measured numbers), **what was
  substituted** (five items, each a real stand-in rather than a weaker version
  of the same thing), and **what was NOT established** (twelve items).
- `AGENTS.md` § Project overview said *"Nothing in it is built yet"*, which
  stopped being true. Corrected in place, with a pointer to the new § What is
  built. `AGENTS.md` is in T2's pinned `Touches`, so this stays inside the
  plan's touched set.
- **Excluded, with the reason named.** `docs/architecture/overview.md` is still
  the unfilled seed template, and the architecture README calls it "read this
  first". That is a pre-existing condition this change did not create, and
  neither T7's nor any other task's pinned `Touches` names it. The README now
  says the file is an unfilled seed and points at § What is built as the
  current map, so a reader is not misled. Filling or deleting it is a separate
  change and has no owner in this spec.
- **The Phase 0 heading was renamed** from "What these results do not
  establish" to "What the Postgres spike results do not establish", because the
  Phase 1 section now cites it and an unqualified heading would read as
  covering both.

### Simplify pass, and one arithmetic finding

- **`retry_on_deadlock` had no production caller.** r7 § Event log specifies
  *"Deadlock (40P01) is retried with backoff"*, and the spec's Always-do says to
  implement what r7 specifies — so it stays, and all three append paths now go
  through it. A retry is safe because a deadlocked append rolled back whole and
  consumed no sequence number, so the second attempt is the first append.
- **Two classes named `Fenced` meant the same thing**, one in `event_log` and
  one in `pool`. The pool now imports the one definition.
- **`EventEnvelope.is_terminal` had no caller and was removed.**
  `TERMINAL_EVENT_TYPES` stays, and a new schema test asserts it names exactly
  the three types revision 0001's partial index names. Neither side had a
  caller that would catch a mismatch, and `walking-skeleton-evidence` will rely
  on both.
- **FINDING — r7's 150-second figure is not derivable from its own timings.**
  r7 § Step execution and `worker-runtime.md` § The pool both state:
  *"With TTL = 60 s, heartbeat every 20 s and poll interval 30 s, worst-case
  reacquisition is 150 s."* The mechanism gives a worker dying immediately
  after a renewal one full TTL of valid lease, then at most one poll interval
  before the survivor finds it claimable: **60 + 30 = 90 s**. No arrangement of
  60, 20 and 30 reaches 150.

  **Nothing is at risk and nothing was designed around.** The criterion's bound
  is the looser of the two and this implementation is inside both — two
  observations, **59.5 s** and **80.3 s**, the second of which is above 60 and
  so confirms 90 rather than 60 is the ceiling. Both constants are in
  `pool.py` under their own names, `DERIVED_REACQUISITION_BOUND_SECONDS` and
  `CRITERION_REACQUISITION_BOUND_SECONDS`, with the disagreement written at the
  definition. The test asserts the criterion's bound and prints both.

  Reconciling the architecture's arithmetic belongs to the **r8 consistency
  pass r7's own header already names as outstanding**, not to this spec, which
  is forbidden from designing around a ratified decision. Surfaced to the owner
  rather than silently adopted.
