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
- **Nothing about the agent layer.** This suite exercises none of it, and that
  is still true. What has changed is the state of the code beneath the claim:
  `src/ced/agents/` was empty when this was written and is not now. The role
  compiler, the toolset stack and the quarantine boundary are built by
  `walking-skeleton-role-compilation` — see § Phase 1 — role compilation and
  the quarantine boundary below, which carries its own limits. Still unbuilt
  after that spec: the decision point's predicate, the containment fragment and
  the provider call.
- **The framework pin moved without re-running spike 7.** ADR-0002 records
  2.45.0 on the strength of an offline probe and the vendor's additive-minor
  policy; spike 7's 10/10 ran under 2.44.0 and was not re-run.
- **The layout had no independent review.** The RFC route was waived, so
  ADR-0003 plus one test is the whole review the five top-level directories
  received.
- **`mypy` does not check the tests.** It runs over `src/ced` only, and `ruff`
  skips the vendored agent packs, `spikes/` and `tools/`.

## Phase 1 — role compilation and the quarantine boundary

Not a spike. `walking-skeleton-role-compilation` is delivered code with an
acceptance suite, recorded here for the same reason the foundation delivery is:
this is where the repository keeps the answer to *what do we actually know*.
The same standard applies — **a check that cannot fail is not evidence** — so
setup and controls are reported apart from the hypothesis checks below.

All checks green except one pre-existing failure that belongs to no spec here,
`test_no_top_level_directory_is_unrecorded` on `.github`, which is open in
`workspace.toml`. The count is deliberately not stated: `pytest` reports it,
and a tally written down here goes stale. No model provider is called, no cloud
credential is used, and the spend is **$0.00**.

Run it with the commands in [`AGENTS.md`](../AGENTS.md) § Build and test
commands. Per-check detail, every falsification run, and the limits of each
layer are in
[`docs/specs/walking-skeleton-role-compilation/notes/verification-ledger.md`](../docs/specs/walking-skeleton-role-compilation/notes/verification-ledger.md).

### What this established

| Claim | Criteria | Evidence |
| --- | --- | --- |
| No tool is reachable beside the wrapped stack | AC-0201 | The constructed `Agent` holds exactly one toolset besides the framework's own `_AgentFunctionToolset`, and it is the decision point. A decorator-registered tool and a second entry in `toolsets=[…]` each fail the build |
| The stack's composition is walked, not trusted | AC-0202 | The chain is traversed on a real `CompiledRole.stack` through `WrapperToolset.wrapped` — decision point, step events, trust class, function tools. Separately, the structural checker rejects seven hand-built wrong compositions and accepts the ratified one. Order is never a caller's parameter: the compiler builds the chain and calls the checker |
| A role that violates a settled decision fails the build, not the call | AC-0203, AC-0204, AC-0205, AC-0206, AC-0219, AC-0251, AC-0258, AC-0260, AC-0262, AC-0266, AC-0267, AC-0269, AC-0273 | Each guard is decided by a refusal on a real record. The closed-set guards — output-contract name, `trust_class`, settings keys — are written as allowlists, so a typo fails closed instead of being admitted by default. `thinking` is observed as `False` in the **resolved request parameters** a stub model receives, not on the settings mapping the compiler wrote |
| The pool's own spend bound is checked before it can claim work | AC-0265, AC-0270 | `validate_pool_config` runs with no database and refuses a deployment that leaves any of the four token ceilings unset or names no allowed model id. Three of the four `UsageLimits` token fields default to `None`, which is unlimited, so a configuration that parses is not a configuration that bounds |
| The cost ceiling is applied before the request, not after | AC-0246 | The per-request bound is read on the pre-request path. AC-0206 is a different question — whether a role may widen — and is green either way |
| Every call is refused, across the whole tool surface | AC-0233 | Every role-and-tool pair from both registries is driven against the migrated database. No tool body runs, and at least one pair is refused **at the decision point** as distinct from one refused earlier at resolution, named pair by pair |
| A denial is terminal from the first refusal this repository raises | AC-0234, AC-0259 | The raised type is `ToolCallDenied`, and it is neither `ModelRetry` nor a subclass — measured against `ModelRetry` as resolved through `ced.adapters.framework_contract`, the same object production code imports |
| An operator can tell a bad role file from a runtime fault | AC-0261 | `role.load.failed` and `role.compile.refused` are appended for real against the migrated database and read back, which is the only proof they clear both the append function's shape check and the table CHECK. The event type is decided by the raised exception type and never by a caller |
| The quarantined role is a construction, not a declaration | AC-0219 | A role is quarantined exactly when its `ceiling` is empty. The compiled agent carries no domain tools, the `reference-selection` output contract, and zero tool-retry and output-validation-retry budgets. Guarded in both directions, so one ceiling entry cannot silently promote it |
| The model never produces a reference | AC-0238, AC-0250 | The deterministic pipeline mints the candidate set from the recorded Apple 10-Q **before** the agent runs and then seals it. 684 candidates, one per distinct non-nil inline-XBRL numeric fact identity. The baseline is committed and was generated by a different extraction from the one under test — a regular-expression pass over the raw bytes — and the two agree on all 684 |
| Only minted references and admitted types cross the boundary | AC-0220, AC-0221, AC-0268, AC-0274 | Provenance is membership in the minted set, not reference shape. What a minted token may *contain* is a declared alphabet and length, so no part of an admitted reference is the filer's prose, and excluding the token's separator makes it injective over concept and context. Labels are membership in a closed vocabulary, not token shape. Scalars are matched by exact type, not `isinstance`, and a content-addressing value is refused categorically with a named reason the suite reads |

**The guards were broken on purpose and the suite noticed.** Two rounds of
falsification ran against the quarantine layer. Replacing label membership
with a token-shape regular expression reds only the label checks — free prose
still fails while `tariff-refund-tailwind` crosses, which is the hole that
criterion exists for. Replacing provenance with a slash-count shape test reds
only the provenance checks. Removing the seal, and dropping a concept prefix
from the mint, each red a different clause. Full table in the ledger.

**One falsification found a real gap and it was closed.** With the categorical
content-addressing branch disabled, every check stayed green — the value was
still refused, but by an unrecognised-type fall-through rather than by the
branch the criterion asks for. The branch was dead code and the suite could
not see it. It is now load-bearing: the refusal carries a named reason the
suite reads, and a check asserts a *different* refusal does not carry it.

**A second round closed the mint's own gap.** The mint interpolated the
filing's concept name and `contextRef` into a token with no declared
alphabet, so filer-authored prose crossed inside a value the parser admits on
membership alone, and the `/` the token uses as its separator was legal in
both components, so two distinct facts could mint one reference. Both are now
refused against a declared pattern in `vocabulary.py`. **The recorded corpus
could not see either defect** — every identity in it already conforms, so the
committed baseline did not move, and each falsification of the new constraint
left the baseline check green. Full table in the ledger.

### Setup, and the checks that are controls rather than evidence

- **The framework-seam suite is a version tripwire, not a hypothesis.** It
  pins the signatures, dataclass fields and `TypedDict` keys this design rests
  on, against inspected objects and never `hasattr`, so a version bump fails
  the build rather than a runtime.
- **Two checks exist to prove other checks can fail.** One rehearses the
  decision point's admit path with an injected resolver that admits, which
  shows the refusal comes from the resolver being empty rather than from a
  literal someone could invert. One drives a tool body that really runs, which
  shows the spy that reports "no body ran" would notice if one did.
- **The step body is a stub model, not a provider.** `TestModel` and
  `FunctionModel` stand in everywhere. That is what keeps this suite free of a
  credential and of spend.
- **The corpus is a recorded fixture, never a live fetch.** EDGAR returns 403
  to this network — the finding from spike 4 — so the filing is read from
  `spikes/phase-0/fixtures/`.

### What this did NOT establish

**The consolidated limits for this delivery live in
[`verification-ledger.md`](../docs/specs/walking-skeleton-role-compilation/notes/verification-ledger.md)
§ What these checks do not establish and in the per-layer sections beside it.**
They are not duplicated here. What follows is what a reader of this page needs
in order not to believe more than was shown.

- **The boundary holds against the cases written, and nothing here speaks to
  an adaptive adversary.** No structural defence has been tested under an
  unlimited adaptive budget. That is `runtime-architecture.md` r8's own
  accepted limit and nothing in this delivery closes it.
- **The guarantee is "no attacker-authored free *text*", not "no
  attacker-influenced signal".** r8 names selection influence explicitly as
  the thing the split does not remove.
- **The reference-selection channel is unmitigated and unmeasured.** A closed
  vocabulary bounds the alphabet, not the channel. A quarantined agent can
  pass signal into a planning agent's context by *which* of the 684 candidates
  it selects. Minting before the run makes forgery unrepresentable; it says
  nothing about steering, and resolution detects a forged reference rather
  than a steered-but-valid one. No check here measures the channel's capacity.
- **The `free-text` branch ships unexercised.** No Phase 1 role can hold a
  `free-text` integration:
  [ADR-0006](../docs/adr/0006-four-r5-deviations-for-phase-1.md) D3 narrows
  r5 § 4's quarantine-only exemption to unreachable, by deriving role class
  from an empty ceiling. That is the safe posture and it is deliberate. It
  also means the quarantine criteria establish the **admitted-types** path
  only.
- **No tool body executes anywhere, by contract.** The decision point ships
  with its position and no predicate, and refuses every call until
  `walking-skeleton-authority-containment` supplies one. So the stack's
  composition is asserted by construction and never demonstrated end to end
  here, and `StepEventToolset.call_tool` and `TrustClassToolset.call_tool` are
  never reached.
- **A disabled authorization boundary is nearly invisible.** Falsification
  run: with the decision point's admit test replaced by `if False:` — the
  boundary admitting everything — "no tool body executed" **stays green**,
  because the step-event layer below refuses next for a different reason. Only
  the assertion that a pair is refused *at the decision point* notices. A
  reader should not read "no body ran" as evidence the boundary works.
- **`thinking=False` is not shown to reach a provider.** What is shown is the
  value in the resolved request parameters a stub model receives. Downstream
  of the compiler, three framework paths on the pinned 2.45.0 drop or never
  assign it, and upstream an executor passing `model_settings` to `Agent.run`
  beats the compiled value. The obligation is carried as a property — the
  value the model reads on the executor's own run path is `False` — and is
  `walking-skeleton-step-lifecycle`'s, with a register entry. Residual harm is
  bounded rather than absent: no provider call is issued here.
- **Which guard refused is not recoverable from the event log.** The refusal
  names the failing role and its stage. The `events` envelope has no column
  for the guard and this delivery writes no payload object.
- **A rejected parse is not attributable in the log.** r5 § 2 wants
  `tool.completed` to carry the parse outcome. With no outcome column and no
  payload object, a raising parse leaves `tool.invoked` with no completion
  beside it, so a reader can tell the call started and did not finish, and no
  more.
- **The version pin is guarded against drift, not against a seam change.** A
  virtualenv that does not carry the pinned release fails the offline gate, at
  collection-adjacent speed and naming both versions. It is **not** established
  that any seam row notices a one-release downgrade: on 2.44.0 exactly one
  assertion reded, the version identity itself, and the other twenty-six
  passed. That is the expected result — the probe found 2.44.0 and 2.45.0
  agree on every seam this design rests on — and reaching for a release far
  enough back to break a seam would be choosing the evidence.
- **Nothing about tables, sections or filer-authored text.** The mint derives
  one candidate per numeric fact identity. Parsed table cells with their
  coordinates and section boundaries, both of which r8 § 4 puts in the
  eventual pipeline, are not derived, and nothing is minted from the 98
  `ix:nonNumeric` elements that carry filer-authored text.
- **Nothing about a provider, a cost, or a latency.** No model is called, so
  no number on this page bounds a real step. Every provider-touching claim is
  `walking-skeleton-step-lifecycle`'s.

## Phase 1 — authority containment

Not a spike. `walking-skeleton-authority-containment` T1 is delivered code with
an acceptance suite, recorded here for the reason the two deliveries above are:
this is where the repository keeps the answer to *what do we actually know*.
The same standard applies — **a check that cannot fail is not evidence** — and
this delivery spent most of its review rounds on exactly that, so the limits
below are longer than the claims.

All checks green except the same pre-existing failure that belongs to no spec
here, `test_no_top_level_directory_is_unrecorded` on `.github`, which is open
in `workspace.toml`. The count is deliberately not stated: `pytest` reports it.
No model provider is called, nothing reaches the database, no cloud credential
is used, and the spend is **$0.00**. Every criterion is offline.

Run it with the commands in [`AGENTS.md`](../AGENTS.md) § Build and test
commands. Per-check detail, every falsification run, the seam decisions this
delivery was asked to settle in code, and the limits of each layer are in
[`docs/specs/walking-skeleton-authority-containment/notes/verification-ledger.md`](../docs/specs/walking-skeleton-authority-containment/notes/verification-ledger.md).

### What this established

| Claim | Criteria | Evidence |
| --- | --- | --- |
| The documented bypasses are refused over the parsed value | AC-0213 | Every row of `worker-runtime.md` § 4's unsafe-prefix table, **read from the document rather than restated**, is refused against a ceiling expressing the same intent over parsed components. A row added upstream that the suite cannot classify is a failure, not a skip. The userinfo row this delivery filed back into that table is one of the three |
| The caller receives the canonical value | AC-0214 | The admitting result carries a parsed `CanonicalUrl`, not a string, so the consumer has no route back to the original — no userinfo, no default port, no dot segments. Asserted at the consumer, which is a **test double**; see the limits below |
| A domain argument that is a public suffix is unauthorable | AC-0215 | Resolved against the bundled dataset, not a hand-kept list, over every character the IDNA encoder turns into a label separator — derived from the codec rather than enumerated, after three rounds in which an enumerated list was extended and bypassed twice |
| A prefix is expressible only where the callee does not parse | AC-0217 | Refused on all six interpreted domain types and accepted on `opaque-string`. The implementation states r5's rule, so a type added later inherits the refusal instead of needing the criterion reworded |
| A `url` argument must constrain its host | AC-0240 | Refused at authoring time. What that does and does not bound is in the limits below |
| A ceiling entry constrains every argument it names | AC-0316, AC-0317 | The declaration is refused naming both the entry and the argument; an entry installed directly, bypassing the authoring surface, denies at evaluation. The two cannot share a case, because the first makes the second's input unreachable through the front door |
| An input the fragment cannot decide raises | AC-0315 | Three shapes driven separately — an unrecognised declared domain type, an ambiguous parse, a predicate that cannot be evaluated against the value — because one combined case would pass on a fragment that raises for one and answers "inside" for the other two. The raised type is this package's own, deriving from no builtin error class an ordinary bug produces, which is what lets the consumer's handler be narrow by type |
| The positive path admits | AC-0218 | A canonical in-ceiling `url` and an in-root `fs-path` against the same ceiling AC-0213 refuses against. Every other criterion here is a refusal, and a fragment that refused everything would satisfy all of them |
| Containment between two predicates agrees with set containment | property test | `contains` answers symbolically over predicate arguments; the oracle answers extensionally by running a universe of concrete values through the real canonicaliser. All ten constructors are generated, and the expected set is read from the authoring surface so a constructor added to the fragment reds until it is covered |

### Setup, and the checks that are controls rather than evidence

- **The mutation evidence is produced by patching in the test process.** The
  canonicaliser ships no disable switch; the spec's first `Never do` refuses
  one inside a shipped security control.
- **Every claim above was checked by deleting the thing it rests on.** Each
  canonicalisation rule, each boundary comparison, each guard, each arm of the
  containment relation, and each bound was removed or stubbed in turn and the
  suite re-run. **Two rules are the exception**,
  and deliberately: deleting `drop-default-ports` or `lowercase-host-not-path`
  admits nothing, which is the whole of why AC-0216 is unmet below. The
  canonicaliser implements r5's six clauses as ten named rules, each
  recording the clause it comes from, so these two rules are the same two
  clauses the limit below counts. Those two
  carry a fail-closed proof — the rule does its job, its removal admits
  nothing the full pipeline refuses, and its removal leaves every other
  rule's case refused — rather than a red. Three review rounds were spent on
  checks that passed and could not fail; the ledger names each.
- **A structural check reads the code rather than its behaviour.** Every value
  interpolated into any message the fragment produces must pass through the
  one function that bounds it, enforced by a scan over the package's syntax
  tree, because four call-site repairs in a row each left a sibling path open.

### What this did NOT establish

**The consolidated limits live in
[`verification-ledger.md`](../docs/specs/walking-skeleton-authority-containment/notes/verification-ledger.md).**
What follows is what a reader of this page needs in order not to believe more
than was shown.

- **One criterion is not met.** AC-0216 asks, for every canonicalisation rule
  r5 names, an input the canonicaliser refuses and that is *admitted* when
  that one rule is disabled. Two of the six clauses cannot supply one, and
  that is proved rather than unfound: no predicate in r5's `url` row ranges
  over a port, so dropping a default port cannot change any decision, and a
  ceiling's host argument is already case-folded when compared, so removing
  host-folding can only shrink what is admitted. Those two carry a
  fail-closed proof instead. The criterion is unchecked with a deferral
  anchor, T1's `Done when` is unmet, and an amendment is owed to the owner.
- **Three refusals go beyond the criteria and are not ratified.** A `url`
  argument must carry a scheme-constraining predicate; a call must supply
  every argument the entry constrains; and a `within` root that is relative
  or the whole filesystem is refused. Each closes a default-allow, each fails
  closed, and each is recorded in the spec's § Follow-ons for the owner to
  ratify or reverse — the two `within` refusals under one entry, because one
  decision settles both. A fourth change of the same shape — only this
  package's two exception types leave evaluation — is **not** a strengthening
  and has no entry: AC-0315 already fixes the seam's signal as a raise, so a
  builtin escaping was a defect against it.
- **AC-0214 asserts at a test double, and no production consumer exists.**
  What is established is that the fragment *emits* the canonical value and
  hands over a parsed object. That the real consumer declines to re-parse the
  original is `walking-skeleton-policy-decision-point`'s to show.
- **Nothing here decides a call.** The fragment is a library; no decision
  point installs it, so the successor to this delivery's claim is that the
  predicate exists, not that the boundary works. The role-compilation
  section above says the decision point "refuses every call until
  `walking-skeleton-authority-containment` supplies one" — the fragment now
  exists and the decision point still refuses every call, because installing
  it is a different spec's.
- **The public-suffix dataset is a 2019-12-21 snapshot with no refresh path.**
  `publicsuffix2` has shipped no release since, so suffixes delegated after
  that date — the platform suffixes anyone can register under — answer "not a
  public suffix" and are authorable. The plan named dataset ageing as a risk
  and assumed a version bump would make it visible; none exists.
- **AC-0240 requires a host predicate to be present and constrains neither
  the host it names nor the address it resolves to.** `host_eq` over the
  link-local metadata address satisfies it. The scheme strengthening inherits
  the identical limit. Both gaps are unowned, and the egress proxy cannot own
  the address-level one: r8 § 4 specifies it as a hostname allowlist with no
  private-range or metadata block, so it shares the blind spot. DNS rebinding
  is unowned for the same reason. What bounds the exposure today is that
  Phase 1 registers no URL-taking tool, which is a fact about the catalogue
  and not a control.
- **`fs-path` confinement is decided against a snapshot the callee
  re-resolves.** `realpath` runs non-strict, so a component that does not
  exist at decision time resolves lexically; created later as a symlink out
  of the root, the admitted path points elsewhere when the callee opens it.
  Handing the resolved path on narrows the window rather than closing it.
- **No predicate ranges over a URL's query.** An admitted URL reaches its
  consumer with an unbounded model-chosen query, which on an allowed host is
  an outbound channel the ceiling does not describe. That follows r5's
  ratified fragment and is recorded rather than changed here.
- **AC-0216 proves rule presence, not rule order.** Disabling one rule at a
  time cannot see a refactor that keeps every rule and transposes two. A
  separate pinned case holds the one ordering the design rests on, and a
  `Never do` states it; neither is a criterion.
- **Nothing about an adaptive adversary.** The fragment refuses the cases
  written and the generated predicate space, and says nothing about a bypass
  nobody has written down. Six review rounds each found a spelling the
  previous round's fix did not reach — an IDNA separator, then an NFKC
  equivalent, then a `]` placed before the userinfo boundary — which is
  evidence about how that search goes, not a bound on what remains.
- **Nothing about a provider, a cost, or a latency.** No model is called and
  nothing reaches the database, so no number here bounds a real step.

