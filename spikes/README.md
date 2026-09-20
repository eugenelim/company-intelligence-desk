# Spikes

Throwaway code that produces **evidence, not product**. Nothing here ships, and
nothing here is a delivery slice. Phase 0 spikes exist to falsify architecture
hypotheses *before* the design is ratified, per
[`runtime-architecture.md`](../docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md)
§ Rollout.

A spike that cannot fail is not a spike. Each one below states what would have
falsified it.

## Phase 0 — status

| # | Hypothesis / test | Needs | Result |
| --- | --- | --- | --- |
| 1 | LiteLLM resolves Bedrock credentials from ambient workload identity, preserving streaming and the tool loop | AWS | **passed** — *superseded by 7* |
| 2 | ADK step invocation under an application-owned orchestrator | model | **passed** — *superseded by 7* |
| 3 | Stream resumption across forced disconnects, with concurrent writers | Postgres | **passed** |
| 4 | Quarantine split preserves analytical quality on a real filing | model | **falsified as run** — see below |
| P1 | `worker` role is refused `INSERT INTO events (type='policy.decision')` | Postgres | **passed** |
| P2 | Concurrent append/claim deadlock ordering | Postgres | **passed** |
| 7 | Pydantic AI over Bedrock via ambient workload identity; PDP inside a `WrapperToolset`; message-history round-trip; approval gate across a process boundary | AWS + model | **passed** — 10/10 hypothesis checks |

**Spike 7 is a re-spike, not a new question.** The agent-runtime constraint was
amended from Google ADK to Pydantic AI on 2026-09-17
([`portable-identity-first-runtime`](../docs/product/intents/portable-identity-first-runtime.md)
§ Constraint amendments), which invalidated spikes 1 and 2 — both were passes
*about ADK and LiteLLM specifically*. Spike 7 re-establishes what they
established, against the replacement, and adds the two claims ADK could not
make. Spikes 3, 4, P1 and P2 are framework-independent and stand unchanged.

## Running the Postgres spikes

```bash
cd phase-0
docker run -d --name ced-spike-pg \
  -e POSTGRES_PASSWORD=spike_only_not_a_secret -e POSTGRES_DB=ced \
  -p 55432:5432 postgres:17-alpine -c log_lock_waits=on -c deadlock_timeout=200ms
docker exec -i ced-spike-pg psql -U postgres -d ced -v ON_ERROR_STOP=1 < schema.sql

python3 privilege_test.py                  # P1
./.venv/bin/python concurrency_test.py     # P2  (needs psycopg)
```

The passwords here are local-only literals for a throwaway container. Nothing in
this directory is a real credential.

## P1 — the privilege split holds

7/7 assertions. The invariant under test, from § Identity — two layers: *the
database role that writes a `policy.decision` event is not the role that
performs the worker's general writes, and no runtime identity holds both.*

Postgres has no row-value-level grant, so the split is built by revoking direct
`INSERT` on `events` from everyone and exposing two `SECURITY DEFINER` functions
with **disjoint** `EXECUTE` grants. `app_worker` is refused the table, refused
the reserved event type by its own append path, and refused the policy function;
`app_policy` is refused the general append path. Both can still do their own
job, which matters — a split that also blocks the legitimate path proves
nothing.

**Finding: `SECURITY DEFINER` misattributes the caller.** The first version
raised `... (role %)` using `current_user`, which inside a definer function is
the *definer* (`ced_owner`), not the caller. An audit trail built on that would
name the wrong principal every time. Now uses `session_user`, which correctly
reports `app_worker`. Cheap to fix here; expensive to discover in a log during
an incident.

## P2 — lock ordering is load-bearing, and more precisely than stated

3/3 claims. Under 8 concurrent writers × 25 appends:

- **Sequence integrity.** 200/200 events, `seq` dense from 1 with zero
  duplicates. This is the concrete reason the design rejects `bigserial`: a
  per-run counter updated inside the append transaction is undone by rollback,
  so a rolled-back append leaves no hole, while a `bigserial` allocation
  survives rollback and does.
- **The designed order does not deadlock.** Zero deadlocks, zero errors.
- **Mixed orders do deadlock.** 12 observed.

**Finding: a uniformly inverted order does *not* deadlock.** The first attempt
made every writer take `runs` before `steps` and produced zero deadlocks — all
writers serialize on the same `runs` row, so no cycle can form. The hazard is
strictly one path inverting *against* another. The design already says this
("inverting the order **against the worker path**"), and the test now
demonstrates the distinction rather than a weaker claim: a rule that cannot be
shown failing is not a rule.

## Spike 1 — ambient workload identity holds

7/7, under a least-privilege role rather than under Admin. Ambient credential
resolution with no static key, streaming, and the tool-call loop all work
through LiteLLM to Bedrock, and a model outside the policy is refused — which is
what makes the scope meaningful rather than decorative. Cost $0.002.

**Finding: cross-region inference profiles change the shape of least privilege.**
A `us.`-prefixed profile routes to other regions, and authorization for the
underlying foundation model is evaluated in the **routed** region. Established by
running three policy variants against the same call:

| Tightening | Result |
| --- | --- |
| Region-pinned inference-profile ARN | allowed |
| Region-pinned foundation-model ARN | **denied** |
| `aws:RequestedRegion` equality condition | **denied** |

Both failing tightenings look obviously correct. A team applying them would read
the denial as a permissions bug and widen the wrong thing.

**Finding: these models are not invocable by raw model id.** Bedrock requires an
inference profile. The design already carries `inference_profile` in the producer
tuple, so the shape was anticipated; the spike establishes it is mandatory.

## Spike 2 — ADK sits under application control

4/4. The application drives each step; ADK does not own the outer loop.

The load-bearing check is the second: a tool call is **denied on argument
value** — same tool, one ticker allowed and another refused — and denied
*before* it executes. That is the seam the policy decision point occupies. If
ADK executed tools without an interceptable hook, argument-value authorization
would have nowhere to stand and `policy.decision` could not commit before the
action.

Checks 3 and 4 are a pair: step context is supplied by the application and
answered without a tool call, and a session with no prior turn does not know the
earlier fact. Without check 4, check 3 could pass on ADK quietly carrying state.

## Spike 3 — resumption holds under concurrent writers

4/4. Across **9 forced mid-stream disconnects** while four writers appended
concurrently: 160 events delivered, 160 distinct, covering 1..160 with zero
duplicates and monotonic order across every resume boundary.

The concurrency is what makes this worth running. A resumable stream over a
quiescent log is easy; resuming correctly *while appends continue* is the claim.

The client deliberately sent a **stale `after=0`** on every reconnect while
supplying the correct `Last-Event-ID`. Delivery had no duplicates, which is the
observable consequence of the server preferring `Last-Event-ID` over the query
parameter — the behaviour § Event log and stream mechanism specifies because
EventSource re-requests the original URL on reconnect. Had the server trusted
`after=`, every resume would have replayed from zero.

## Spike 4 — falsified as run, and usefully so

Run against a real Apple 10-Q filed 2026-07-31, on 30,000 characters of MD&A.
The same question was put to the same analyst model twice: once over the full
prose, once over **only** what survived the quarantine boundary — 6 observations,
2,029 characters, **6.8% of the prose**. Cost $0.022.

**The hypothesis does not hold at n=1.** Closed-vocabulary classification lost
distinctions a diligence reader depends on. Three losses, with different causes.

### 1. Causality cannot cross a closed vocabulary

The baseline found: *"Products gross margin expanded 560 bps YoY, driven partly
by tariff refunds — a non-recurring tailwind that inflates reported
profitability."*

The vocabulary contains `margin_expansion`. It has no way to carry *why*, and
"non-recurring tailwind that inflates reported profitability" **is** the
diligence judgement — the reader's question is not whether margin moved but
whether the move is repeatable. A label plus a scalar cannot express it, and no
enlargement of the label set fixes this: the content is an argument, not a
category.

### 2. The anchor-resolution check systematically drops tabular facts

Two of eight observations were rejected because their anchors did not resolve.
Both were **substantively true**, and the reasons differ:

| Dropped | Anchor the agent emitted | Reality |
| --- | --- | --- |
| `tax_rate_change` | `"effective tax rate 17.9 % 16.4 %"` | `effective tax rate`, `17.9` and `16.4` all appear — as **separate table cells**. The contiguous string does not exist |
| `margin_expansion` | `"Products gross margin percentage increased"` | The phrase appears **nowhere** in the document. Invented |

The first is the structural finding: **financial filings put their most material
quantitative facts in tables, and a verbatim-substring anchor can never resolve
a fact assembled from table cells.** Requiring prose quotes as the reference type
guarantees that the figures a diligence product exists to analyse are the ones
most likely to be dropped.

The second is the forgery risk the design already names — *"a quarantined model
induced to forge a reference"* — occurring here **with no adversary present**,
at 1 in 8, from ordinary paraphrase.

**The fail-closed parser worked.** Both were caught and neither crossed. That is
the mechanism behaving exactly as specified; the cost is that true observations
were dropped with the fabricated one.

### 3. A material legal exposure never crossed

The baseline surfaced the Epic/App Store injunction with Supreme Court review
pending, and separately an explicit management warning that semiconductor, NAND
and DRAM shortages are *expected to intensify*. `litigation_exposure` and
`supply_concentration` are both **in** the vocabulary, so this is not a
vocabulary limit — the quarantined agent simply did not select them under a
"most material" instruction. Selection is itself a channel, which is the
residual `runtime-architecture.md` § Known at ship already records as
unmitigated.

### The construction this spike tested was weaker than it needed to be

The quarantined agent here both *read* the prose and *emitted* the references,
so the parser could only reject bad ones afterwards — a detection control, of
the kind this design rejects everywhere else.

The stronger construction runs a **deterministic semantic pipeline first**:
XBRL facts, parsed table cells with coordinates, section boundaries. The agent
then only **selects and labels among candidates that already resolve**, and
cannot mint an identifier. Forgery stops being a thing to catch and becomes a
thing that cannot be expressed — and the agent's remaining task is small enough
for a light model.

Both failure modes this spike measured are artefacts of the weaker design: the
fabricated anchor could not occur, and the table-cell anchor would carry a cell
coordinate rather than a reconstructed quote. **What it does not fix is
§ Causality above**, plus untagged narrative, selection influence, and
cross-fact inference — see `runtime-architecture.md` § Known at ship.

### What this changes

The losses have identifiable causes, and the largest has a clean fix:
**quantitative claims should cross as XBRL fact references, not prose quotes.**
XBRL facts are already tagged, identified and individually addressable, so they
resolve deterministically — a genuine admitted form for exactly the facts prose
anchors handle worst. SEC publishes them through `companyfacts`, which the
ingestion tiers already reach.

Prose quotes remain right for narrative claims. Causality remains outside the
boundary, and that is a real, recorded cost rather than a bug to fix.

### Limits of this result

n=1: one filing, one section, one hand-written vocabulary of 20 labels, one
quarantined model (Haiku 4.5), one analyst (Sonnet 4.6), one prompt. A different
vocabulary, a stronger quarantined agent, or an XBRL-based reference type could
each move the result. It is evidence that the cost is real and where it falls —
not a measurement of its size.

SEC EDGAR returns **403 "Your Request Originates from an Undeclared Automated
Tool"** from this network, across several user-agent formats that follow SEC's
documented guidance. General egress is fine, so this is SEC's own Akamai edge
refusing this caller, not a local network block. Probing stopped there:
circumventing a deliberate access control is not a spike result.

**This is a deployment finding, not just a spike inconvenience.** § Trust
boundaries specifies the worker reaching EDGAR "via the egress proxy, hostname
allowlist, SEC-compliant user agent, rate limiting". A compliant user agent is
necessary and evidently **not sufficient** — the caller's egress address
matters. A Fargate deployment behind a NAT gateway inherits whatever reputation
that address carries, so this can fail in production having passed in
development.

To unblock: obtain one filing from an unblocked network, once, and record it as
a fixture. That is precisely what § Local development's recorded-fixture replay
exists for, and the fetch adapter then replays it for every subsequent run.

## What the Postgres spike results do not establish

- Both Postgres spikes ran against a **local container**, not RDS or Aurora.
  Lock behaviour is core Postgres and should carry, but managed-service
  differences — connection pooling, failover, `deadlock_timeout` defaults — are
  untested.
- `deadlock_timeout` here is 200 ms, well below the 1 s default, which makes
  deadlocks surface faster than they would in production.
- Neither test says anything about the *AWS* identity layer. They prove the
  database privilege model, which is where the `policy.decision` split actually
  lives.

## Spike 7 — the replacement framework holds, and carries two claims ADK could not

**10/10 hypothesis checks** — H1 4/4, H2 2/2, H3 2/2, H4 2/2. The script prints
13 PASS lines; three of them (`scoped role created`, `role assumed`, `torn
down`) are setup and teardown recorded with a hardcoded result, and by this
directory's own standard a check that cannot fail is not evidence. They are
reported separately rather than folded into the headline.

Same least-privilege construction as spike 1: a scoped role is
created and assumed, and every check runs under those temporary credentials.
Running it as Admin would prove nothing, because an admin can invoke any model.
`pydantic-ai` 2.44.0, Haiku 4.5, cost $0.006.

**H1 — ambient workload identity holds through a different SDK path.** 4/4.
`BedrockConverseModel` is constructed with a model id and *nothing else* — no
provider argument, no credentials, no boto3 client — and resolves the ambient
chain. Streaming and the tool-call loop both survive, and a model outside the
policy is refused with `AccessDeniedException`, which is what makes the scope
meaningful rather than decorative. **LiteLLM is no longer in the model hot
path**, which retires the supply-chain risk `runtime-architecture.md` carried
for it.

**H2 — an authorization hook exists at the right place.** 2/2. A
`WrapperToolset.call_tool` override authorizes on **argument value**: the same
tool with `ticker="ACME"` executes and with `ticker="EVILCORP"` does not. Both
calls are well-typed; only the value differs. This is the check spike 2 made
against ADK, re-made against the seam the design now uses.

**What H2 does not establish.** The override appended to a Python list. No
database, no second connection, no `policy-writer` grant, and no
failed-append-is-a-denial path — which is the part `runtime-architecture.md`
calls load-bearing ("the decision event commits before the action"). H2 proves
the hook exists and sees argument values. It does **not** prove
commit-before-action, which moves to a Phase 1 criterion.

**Finding: a denial must not be a `ModelRetry`, and the framework makes that
distinction available.** An ordinary exception raised inside `call_tool`
propagates out of the whole agent run rather than being handed back to the model
as advice. That is the fail-closed behaviour the design wants — a denial is
terminal, not a hint to try a different argument — but it is a choice the
implementation has to make deliberately, because raising `ModelRetry` instead
would silently convert the authorization boundary into a negotiation. The tool
body did not execute in either case.

**H3 — a message history round-trips and resumes.** 2/2.
`ModelMessagesTypeAdapter` round-trips a run's messages to JSON and back
**byte-identically** on a second dump, and a *fresh* `Agent` — sharing nothing
with the original run but those bytes — resumes from the deserialized history
and answers a question about the earlier turn.

**Scope limit, and it is a real one.** The history under test was **two
messages, no tool calls** — 1,163 bytes. It contained no tool-call parts, no
tool returns, no retry parts and no deferred-approval parts, which is none of
the shapes a real step produces. Byte-identity at that shape does not
generalise to the shape the design depends on, and H4's suspended-approval
history was serialized but never asserted byte-identical. Phase 1 carries the
richer round-trip. This is what replaces ADK's
`BaseSessionService`, the seam `runtime-architecture.md` § Alternatives refused
to depend on because ADK does not present it as a public extension point.

**H4 — the approval gate survives a process boundary.** 2/2. A tool declared
`requires_approval=True` suspends the run and returns `DeferredToolRequests`
naming the pending call and its arguments. The decision is then returned through
`deferred_tool_results` on a **different `Agent` object built from the
serialized history**, and the tool executes. Nothing in-memory from the first
run is required, which is the property the design needs: the approval gate sits
between two separately-leased steps, possibly on two different workers, with
Postgres and an event log in between.

**What this spike does not establish.** Streaming was demonstrated at 2 deltas
on a short response — enough to show the channel is not collapsed to a single
blocking call, not enough to characterise streaming behaviour under a real
multi-minute step. The cross-region inference-profile finding from spike 1 is
**inherited, not re-tested**: it is an IAM property rather than a framework one,
so it should carry over, but this run asserts it rather than demonstrating it.
And nothing here exercises a fenced lease, a real step boundary, or concurrency
— spike 7 is about the framework seam, and the worker pool remains as proven by
spike 3, P1 and P2.

```bash
cd phase-0
python3 -m venv .venv && ./.venv/bin/pip install 'pydantic-ai-slim[bedrock]' boto3
AWS_PROFILE=<an-admin-profile> ./.venv/bin/python pydantic_ai_bedrock_spike.py
```

## Phase 1 — walking skeleton foundation

Not a spike. `walking-skeleton-foundation` is delivered code with an
acceptance suite, and it is recorded here because Phase 0 is where this
repository keeps the answer to *what do we actually know*. The same standard
applies: **a check that cannot fail is not evidence**, so setup checks are
reported apart from hypothesis checks.

All checks green — the count is deliberately not stated here, because it moved three times during review and a stale tally is worse than none; `pytest` reports it. The same goes for the duration: `AGENTS.md` § The local substrate describes the shape and publishes no figure, because four published ranges each excluded a run the same section called normal. Most of that time is the
fault-injection suite running at r7's real lease timings. No model provider is
called, no cloud credential is used, and the spend is **$0.00** — by design:
`walking-skeleton-step-lifecycle` owns every provider-touching claim.

Run it with the commands in [`AGENTS.md`](../AGENTS.md) § Build and test
commands. Per-check detail, including every finding the suite produced while
being built, is in
[`docs/specs/walking-skeleton-foundation/notes/verification-ledger.md`](../docs/specs/walking-skeleton-foundation/notes/verification-ledger.md).

### What this established

| Claim | Criterion | Evidence |
| --- | --- | --- |
| A run starts over HTTP and is readable in `requested` | AC-0001 | 201 with a run id, snapshot `{"state":"requested","as_of_seq":1}`, one `run.requested` event with `step_id` and `agent_role` null. Driven against a real uvicorn server, and separately against the shipped `ced-api` binary by hand |
| The run row, its coordinator step and `run.requested` are atomic | AC-0002 | With the step insert forced to fail by an already-taken `step_id` — a real unique violation on the real statement — all three rows are absent |
| `seq` is dense from 1 under eight concurrent writers | AC-0003 | 200/200 events, dense, zero duplicates, `next_seq` 200, zero deadlocks. Spike P2's shape against the **shipped** schema rather than the spike's |
| A rolled-back append consumes no sequence number | AC-0004 | A stale epoch raises `Fenced`; the sequence stays `[1,2,3]`, `next_seq` stays 3, and the next legitimate append gets 4 |
| The **database** refuses the worker the reserved event type, in any spelling | AC-0005 | A real `app_worker` connection is refused with `insufficient_privilege`, and the message names `app_worker` — `session_user`, which is P1's finding, now pinned on the shipped schema. The worker is also refused `EXECUTE` on the policy function, and no role holds a direct `INSERT` on `events`. **Three review rounds were spent on the "any spelling" half**: a padding denylist was defeated by a tab, then by six invisible characters, then by a Cyrillic homoglyph, which is not whitespace at all. The shipped rule is positive — the canonical form must be a dotted run of lowercase ASCII alphanumerics — and it is enforced by a CHECK on the column as well as by the function, so it holds against direct DML by the schema owner and `COPY`. Verified over 18 spellings |
| A duplicate derived idempotency key is refused | AC-0006 | `UniqueViolation` on the second `tool.invoked`, consuming no sequence number; the index's partiality checked in both directions |
| The dependency-direction gate fails on a real violation | AC-0007 | Seven injected imports each reported, four permitted placements each not reported, three dynamic-import forms caught, and zero findings once removed |
| The identifier lint catches an embedded account id, and not a content hash | AC-0008 | Five embedding shapes exit 1; a hash containing a twelve-digit run exits 0. The real script, as a subprocess, against a throwaway git repository |
| The served routes match the committed contract | AC-0009 | Route table equality against `/openapi.json`, and the comparison shown failing on three mutations of a copy |
| A killed worker's step is reacquired with no operator action | AC-0010 | `docker kill`; reacquired after **59.5 s** and **80.3 s** on two runs, `lease_epoch` 1 → 2 |
| A drained worker surrenders its lease promptly, and its step returns in one poll interval | AC-0011 (amended 2026-09-18) | `docker kill --signal=TERM`, with the clock started at signal delivery. Clause 1: the lease stopped being held after 0.04 s, observed as the surrender itself, against a bound of under one heartbeat. Clause 2: reacquired 19.2 s after that surrender, against one poll interval. End-to-end 19.2 s, reported and not asserted |

Two further results that no criterion asked for and that a reader needs:

- **The lock-ordering rule is shown failing.** Mixed orders on one
  `(run, step)` pair deadlock; a **uniformly** inverted order does not, because
  every writer serialises on the same `runs` row; the designed order is clean
  under the same pressure. Phase 0 sharpened the claim that way and the suite
  carries the sharpening rather than the weaker version of it.
- **`fence_step` is owned by `ced_fence`**, a `NOLOGIN` role granted to no
  application identity, verified in `pg_proc` — so the fence runs far below the
  schema owner's privilege *and* the role the split distrusts cannot `DROP` or
  `ALTER` it. `app_policy` is refused `SELECT ... FOR UPDATE` on `steps`
  directly — and since ADR-0005 D4 it holds no table access at all, so that
  refusal is attributable to holding nothing rather than to the `UPDATE` the
  row lock needs. Either way the fence had to be a function rather than a
  grant. [ADR-0004](../docs/adr/0004-fence-function-owner.md)
  records this as an owner-approved narrowing of `worker-runtime.md` item 1,
  whose preferred option — owning the fence as `worker` — review established as
  unsafe.

### What was substituted

Each of these is a real stand-in, not a weaker version of the same thing.

- **"No operator action" rests on a second worker already running**, not on
  anything replacing the killed one. `restart: "no"` keeps the victim dead so
  the recovery observed is the survivor's. A deployed ECS service with a
  desired count would replace the task; nothing here does.
- **The step body is a sleep, not a model call.** That is what keeps this
  suite free of a credential and of spend, and it means nothing here exercises
  a fenced worker abandoning an in-flight model call.
- **Role creation is a container init hook, not a migration.** In a deployed
  system the roles and their credentials come from whoever owns the database
  instance, and `alembic` authenticates as r7's `migration` identity. Locally
  the bootstrap superuser stands in for both, so **nothing ran as r7's
  `migration` role** and its privileges are unverified.
- **The `migration` identity also creates the login roles**, which a real
  deployment would not let it do.
- **`quay.io/minio/minio` replaces the Docker Hub path**, because
  `docker pull minio/minio` is refused from this network — the same class of
  network-dependent failure as spike 4's SEC 403, and worth recording for the
  same reason.

### What this did NOT establish

**Two lists exist and they cover different things.** This one carries the
Phase-0-facing limits — what the spikes and this suite together do and do not
license a reader to believe about the platform. The delivery's own consolidated
limits, roughly thirty of them across the schema, the worker, the privilege
model and the checks themselves, live in
[`verification-ledger.md`](../docs/specs/walking-skeleton-foundation/notes/verification-ledger.md)
§ What is not established, which is authoritative for anything about this
spec's code. They are deliberately not duplicated here: two copies of a limit
list diverge, and round 8 of this delivery was largely spent on records that
had.

- **Nothing about a managed database.** Both the Phase 0 Postgres spikes and
  this suite ran against a local container with `deadlock_timeout` at **200 ms**,
  well below the 1 s default, which makes deadlocks surface faster than
  production would. Connection pooling, failover and managed-service
  `deadlock_timeout` defaults remain untested, exactly as § What the Postgres
  spike results do not establish records for Phase 0.
- **Nothing about Fargate.** Local containers on one Docker host. Task
  replacement, its timing and its notice period are unmeasured — and the vCPU
  quota being 4000 in the target account is a property of the account, not of
  the design.
- **Nothing about the AWS identity layer.** No cloud credential is used
  anywhere in this suite. What is proven is the *database* privilege model,
  which is where the `policy.decision` split actually lives.
- **The 150-second bound is not established; two observations inside it are.**
  AC-0010 measured 59.5 s and 80.3 s on two runs. Measurements below a bound do
  not prove the bound.

  **And r7's 150 is not derivable from r7's own timings.** A worker dying
  immediately after a renewal leaves one full TTL of valid lease, then at most
  one poll interval before the survivor finds the step claimable: 60 + 30 =
  **90 s**. No arrangement of 60, 20 and 30 reaches 150. The criterion is the
  looser of the two, so this implementation is inside both, and the 80.3 s
  observation confirms 90 rather than 60 is the real ceiling. Reconciling the
  architecture's arithmetic belongs to the r8 consistency pass r7's header
  already names as outstanding — not to this spec, which is forbidden from
  designing around a ratified decision.
- **`append_policy_decision`'s lock ordering is argued, not demonstrated.**
  Spike P2 ran with no second locker on `steps`, so the claim that the policy
  path preserves P2's proven ordering rests on it taking the fence in the same
  order. What *is* demonstrated is that a mixed order still deadlocks.
- **No terminal event has a writer here.** `append_run_event` admits exactly
  r7's two names, so `run.completed` and `run.failed` cannot be appended by
  anything in this spec. The run state machine that produces them belongs to
  `walking-skeleton-evidence`.
- **Nothing about the stream.** The events route serves a cursor projection.
  Reconnect semantics, the `Last-Event-ID` preference over `after=`, keepalives
  and stream termination are all the evidence spec's, and Phase 0 spike 3 is
  still the only evidence for any of them.
- **Nothing about cancellation.** No cancellation token, no `step_deadline`.
  The heartbeat reads run state in the same statement that renews the lease, so
  the signal exists; nothing here produces a cancelled run.
- **Nothing about the object store.** MinIO is reachable and nothing reads or
  writes an object. The worker's boot sequence checks both database connections
  and deliberately not the object store, because an S3 client in `worker/`
  would put the AWS SDK outside `adapters/`.
- **Nothing about the agent layer.** `src/ced/agents/` is empty. The role
  compiler, the policy decision point, the containment fragment, the quarantine
  boundary and the provider call are all unbuilt, and `pydantic-ai` is pinned in
  the manifest and imported by no code — it is there so the
  dependency-direction gate has something real to forbid.
- **The framework pin moved without re-running spike 7.** ADR-0002 records
  2.45.0 on the strength of an offline probe and the vendor's additive-minor
  policy; spike 7's 10/10 ran under 2.44.0 and was not re-run.
- **The layout had no independent review.** The RFC route was waived, so
  ADR-0003 plus one test is the whole review the five top-level directories
  received.
- **`mypy` does not check the tests.** It runs over `src/ced` only, and `ruff`
  skips the vendored agent packs, `spikes/` and `tools/`.
