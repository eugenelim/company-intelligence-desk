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
| 1 | LiteLLM resolves Bedrock credentials from ambient workload identity, preserving streaming and the tool loop | AWS | **passed** |
| 2 | ADK step invocation under an application-owned orchestrator | model | **passed** |
| 3 | Stream resumption across forced disconnects, with concurrent writers | Postgres | not run |
| 4 | Quarantine split preserves analytical quality on a real filing | model | **blocked** — no EDGAR access |
| P1 | `worker` role is refused `INSERT INTO events (type='policy.decision')` | Postgres | **passed** |
| P2 | Concurrent append/claim deadlock ordering | Postgres | **passed** |

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

## Spike 4 — blocked, not failed

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

## What these results do not establish

- Both Postgres spikes ran against a **local container**, not RDS or Aurora.
  Lock behaviour is core Postgres and should carry, but managed-service
  differences — connection pooling, failover, `deadlock_timeout` defaults — are
  untested.
- `deadlock_timeout` here is 200 ms, well below the 1 s default, which makes
  deadlocks surface faster than they would in production.
- Neither test says anything about the *AWS* identity layer. They prove the
  database privilege model, which is where the `policy.decision` split actually
  lives.
