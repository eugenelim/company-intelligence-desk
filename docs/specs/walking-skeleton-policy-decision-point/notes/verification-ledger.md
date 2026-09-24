# Verification ledger — the policy decision point

Execution observations for
[`spec.md`](../spec.md) and [`plan.md`](../plan.md). The plan's
`Touches`, `Tests` and `Done when` are the contract; this file records what
running the work taught, including what the checks do **not** establish.

## T1 — what the authorization suite establishes

Four files under `tests/authorization/`. Three carry a module-level
`substrate` marker; `test_ceiling_compilation.py` is pure and runs offline.
**No count is written here on purpose** — a tally in prose drifts from what it
counts and no gate reads it, which is exactly how an earlier draft of this
section came to state three figures that were each wrong. Read the number
`pytest` prints.

The fifteen criteria are green against the Compose substrate, and
`walking-skeleton-role-compilation`'s AC-0234 is green in the same run.

## Mutation proof — every guard was shown failing

A check that cannot fail is worse than none, because the claim stops anyone
looking. Each guard below was deleted or inverted in turn and the suite re-run;
every one reds, and the suite is green again with the guard restored. The
mutations were applied to the working tree and reverted, so nothing here ships.

| Guard removed or inverted | Outcome |
| --- | --- |
| Ceiling entries built directly instead of through `declare` | 9 failed |
| An unrecognised predicate kind dropped rather than refusing the entry | 2 failed |
| An absent required payload key filled from the constructor's default | 1 failed |
| The public-suffix refusal removed | 1 failed |
| A resolver lookup miss falls through instead of denying | 1 failed |
| The `policy.decision` recorded after the tool body runs | 6 failed |
| The denial handler widened around the delegation | 10 failed |
| The entitlements conjunct not consulted | 1 failed |
| The current epoch re-read inside the append | 2 failed |
| Both identities read from the call's arguments | 1 failed |
| No fenced termination after a failed append | 3 failed |
| Abandon whenever the append raised `Fenced` | 2 failed |
| The duplicate-invocation handler removed | 1 failed |
| An unbound decision point admits rather than refusing | 1 failed |
| The decision point denies unconditionally | 8 failed |
| The trust-class layer returns the raw result unparsed | 2 failed |
| `app_worker` granted `INSERT` on `agent_role` | 1 failed |
| The non-string-`kind` refusal removed (round 1 repair) | 3 failed |
| `app_policy` granted `DELETE` on `entitlements` (round 1 repair) | 1 failed |

The failure counts above are what each mutation produced on the run that
proved it, and they are evidence of a mutation reding rather than a figure to
reconcile against a later suite.

**The epoch re-read is worth its own line.** Written as an uncommitted read on
the worker connection it did not merely fail — it *wedged*, because the open
transaction takes a `runs` row lock the policy connection's `next_seq` bump then
waits on. The mutation recorded above commits after reading, so it fails the
criterion legibly instead. Both directions prove the guard; only one is
readable.

## What AC-0239's second worker does and does not establish

The criterion requires a real second worker holding a later epoch, and it gets
one: `a_second_worker_claims` opens its **own** connection, runs the shipped
`claim_one` with its **own** `worker_id`, and asserts the epoch advanced. The
fence that then refuses the evicted worker's append is the shipped one, not an
injected failure.

**What it is not is a second operating-system process.** A Compose worker
container would additionally establish that the takeover survives process
boundaries, connection pooling and the real poll loop's timing. A
function-level second worker establishes the part the criterion is about — that
the epoch the decision point holds is stale, and that the database is what
notices — and nothing about scheduling. The distinction matters because the
defect AC-0239 exists to catch is a decision point re-reading the epoch, which
is invisible to process topology and fully visible here.

**The lease is expired by hand**, with an `UPDATE` moving `lease_expires_at`
into the past, because `claim_one`'s recovery predicate is
`state = 'leased' AND lease_expires_at < now()` and the TTL is 60 seconds. The
takeover itself is not shortened: it is a real `claim_one` against that
predicate. What is skipped is only the waiting.

## A defect the work found in a seam this task added

`read_run_principal` originally left an open transaction on the worker
connection, because a bare `SELECT` on a non-autocommit connection begins one.
That transaction holds a `runs` row lock, and the **policy** connection's
`next_seq` bump then blocks on it — so the decision append waited forever on
the read that prepared it, and the step wedged rather than failing. Found by the
first run of the suite hanging; diagnosed from `pg_locks`. The seam now commits
after reading, which is the discipline `renew` and `release` already keep.

Recorded here rather than in the plan because it is an execution observation:
the plan's design was right and its implementation had a defect on first
writing.

## What the compile-path checks do not establish

Both limits are inherent and are recorded rather than repaired.

- **The drift claim rests on somebody re-reading the fragment.** Nothing
  mechanical notices a refusal added to `ced.domain.containment.ceiling` after
  `tests/authorization/test_ceiling_compilation.py` was written. The eight
  checks cover the refusals `declare` holds that `evaluate` does not repeat, as
  that module stands on 2026-09-23.
- **The no-canonical-form refusal is a union over causes.** It fires for every
  `ContainmentUndecidable` the canonicaliser can raise, so the check on
  `within("")` discharges the *site* rather than the cause set.

## What the offline gate lost

`pytest -m 'not substrate'` gave no signal on this spec's criteria before this
task, and now gives less: the retired case in
`tests/compiler/test_decision_point_refuses.py` was the one check in the
repository that drove an admitting resolver through the decision point and
asserted delegation, and it ran offline. Its replacement is AC-0318, which
carries the `substrate` marker like everything else here.

`tests/authorization/test_ceiling_compilation.py` partly offsets this — the
offline checks over the decode and the compiler's wiring, including one that
holds `compile_role` installs the decoded ceiling. What no offline check can
reach is an admitted call reaching a tool body, because binding a step context
needs a database once AC-0209 requires the append.

## The identity path has no shipped caller yet

AC-0319 holds that the acting role and the initiating principal are read from
the claimed step and its run, and that a call carrying different values changes
neither the decision nor the recorded event. The read itself is shipped:
`read_run_principal` on `events.principal` of the run's `run.requested` row, and
`Lease.agent_role` from the claim.

**No step executor assembles a `StepContext` from them**, because that path is
`walking-skeleton-step-lifecycle`'s and does not exist. The suite's fixture
assembles it from the same two shipped reads. So what is established is that
the decision point cannot take either identity from the call; what is not is
that the only production assembler does it this way, there being none.

The entitlements half has the same shape, and **no separate entitlements
compile path was built**: `load_entitlements`
(`src/ced/adapters/postgres/roles.py`) is the shipped read, `compile_ceiling`
decodes what it returns — `entitlements.ceiling` and `agent_role.ceiling` are
the same decidable fragment and the same decoder — and the resolver that
produces is bound when a step binds, which nothing yet does. An earlier draft
of this line named a `compile_entitlements` that exists nowhere in the tree.

## The pre-EXECUTE audit gap, closed by recording

`.context/reviews/89569ab1-1e41-4540-adf4-1794dc4a5d8f/` holds six raw
pre-EXECUTE review artifacts and five adjudications.
`3-pre-execute-security-reviewer-adjudication.md` does not exist: that round's
Blocker — the exact-decode requirement now in T1's `Tests` — was taken after the
session reproduced its witness directly, without dispatching the adjudicator,
under the owner's decision to stop the review loop on the diverging-loop
condition.

The repair only tightened a control, and the criterion set was unchanged. The
artifact set is asymmetric and this entry is the record of why, so a later
reader finds the gap explained rather than discovers it.

## T2 — the grep gate reached two files no task could edit

T2's gate greps `src/ tests/ docs/` for the literal
`walking-skeleton-authority-containment` and refuses any hit attributing a moved
criterion or the decision point to that spec. Two architecture documents carried
such a hit and sat in no task's `Touches`:
`docs/architecture/role-configuration-seams/role-configuration-seams.md`, whose
seam table says that spec "builds the decision point's predicate", and
`docs/architecture/inspectable-multi-agent-diligence/runtime-architecture.md`
r8 § 10, which names it as owner of the authorization boundary's encoding and
evaluation. Both were correct before the cut of 2026-09-23 and wrong after it.

Surfaced to the owner, who chose on 2026-09-23 to widen T2's `Touches` by
amendment and to correct **ownership only** — no Built or Designed status moves
in r8, because § Durable Outputs routes the current-state map to
`docs/architecture/README.md` and T3 to r5's STATUS header. The plan's Changelog
carries the amendment and the two declined alternatives.

Four further hits were doc-comment corrections in files outside any `Touches`
— `src/ced/agents/toolsets/__init__.py`, `tests/fixtures/registry_seed.py`,
`tests/compiler/test_role_loader.py` and
`tests/compiler/test_compiled_agent_structure.py`. They rode along under the
bundled-fixes carve-out: no behaviour change, no design call, verified by the
gate itself, and none of them a file that defines what an agent may do.

## The cohort baseline had to be rebuilt, and one engine record is missing

The round-5 amendment changed `plan.md`, so its hash no longer matched the
baseline `plan-locked` pinned and `wave-complete` refused with
`schedule check-current`. The engine's own recovery was followed exactly:
`Status: Approved` restored in both artifacts, `loop-cohort reset`, `init`,
`approve-plan`, `schedule`, then the two completed waves' dispatch receipts and
advances replayed, then `Status: Implementing` restored in `spec.md`.
`loop-engine reset` was **not** run, as that recovery text warns.

**One consequence is recorded rather than repaired.** `wave-complete` and
`wave-passed` check the *current* wave's receipts, and the recovery replayed the
cohort pointer to wave 2 before those transitions could be fired for wave 1. So
the engine's transition ledger carries `wave-passed` for wave 0 and not for wave
1, while the cohort — which is the authoritative wave pointer — is at wave 2
with T1 and T2 both accounted for. Nothing downstream reads the missing record:
the final wave fires `wave-complete` then `gates-clean`, and both guards are
satisfied at index 2.

## T3 — what the record now says

`spikes/README.md` gains a section separating what the fifteen criteria
establish from what they do not, with the second list the longer of the two.
`docs/architecture/README.md` § What is built gains a row for the authorization
boundary and loses it from "designed and not built"; r5's STATUS header moves
that one clause and no other.

## Post-gates review round 1 — what was sustained, and what was not

Three reviewers ran against the committed tree: `adversarial-reviewer`,
`security-reviewer` (mandatory — this is the authorization boundary) and
`quality-engineer` (structural change writing persistent state). Each raw
report was persisted and adjudicated independently under
`.context/reviews/89569ab1-1e41-4540-adf4-1794dc4a5d8f/`, and only sustained
findings were acted on.

**The majority were refuted**, which is the reason the adjudication step exists:
of the findings raised, the adjudicators refuted the canonical-value
pass-through as unreachable, a predicate-exception gap already closed by the
sibling's own property test, three observability and timeout asks with no
authority behind them, a mutable-export claim `mypy` already refuses, and the
spec-status finding, which described a step the loop had not yet reached.

### Repaired

- **A stored predicate `kind` that is not a string escaped the decode as a bare
  `TypeError`.** `{"kind": []}` is unhashable, so the membership test that
  classifies a kind raised before it could refuse. `append_role_refusal` files
  neither `TypeError` nor anything but the two role-refusal types, so the role
  failed to compile with the event log silent — the
  `unmapped-refusal-appends-no-event` shape, reached through a column an
  operator writes by hand. The fail direction was already closed; what was
  missing was attributability. Refused by type before the lookup, with checks
  over four non-string shapes, and mutation-proven.
- **AC-0249 attempted two of the write verbs a grant can confer.** A later
  `GRANT DELETE` on any of the three configuration tables would have left the
  one check written to notice a grant regression green. The statement set is
  now derived from the grantable write privileges — `INSERT`, `UPDATE`,
  `DELETE`, `TRUNCATE` — and granting `DELETE` on `entitlements` reds it, which
  it did not before.
- **The erratum note now names the rest of the cut's casualties.**
  `walking-skeleton-role-compilation` is Shipped and frozen and its `spec.md`
  and `plan.md` still attribute AC-0208, AC-0235 and the decision point's
  predicate to the containment spec. They cannot be edited and a
  `[backlog].open` entry on that path raises `duplicate_membership`, so the
  note that already carries the AC-0233 trigger now carries them too. That is
  what T2's grep gate leaves standing, recorded where a reader of the frozen
  spec will find it.
- **Two § Follow-ons entries were added** — the canonical-value handover, and
  the denial reason as a third field the envelope cannot carry.
- **The ledger's counts are gone.** An earlier draft of this file stated three
  figures about the suite and every one was wrong. They are replaced by the
  shape, because no gate reads a tally and a reader who needs a number should
  read the one `pytest` prints.

### Surfaced to the owner, and decided

- **ADR-0007 lands outside every task's `Touches`.** Sustained as a Blocker:
  the owner's direction settled *what* to do and not whether the commit is
  admissible inside a pinned contract, and the bundled-fixes carve-out refuses
  a ride-along whose resolution moves a governing record. **Decided on
  2026-09-23: extract it.** The layout work is already its own commit and
  becomes the base of the stack with its own description, rather than a sixth
  plan amendment folding repository-layout governance into the task whose
  contract is the authorization boundary.
- **`AGENTS.md` § Development workflow still reads "a sixth still needs the
  RFC"** while ADR-0007 § References lists that section as a waived
  requirement. ADR-0007 D2 preserves ADR-0003 D2's RFC route for a sixth
  *application* directory, so the sentence stays true of the case it was
  written for; what is stale is only that it does not point at the new record.
  `AGENTS.md` is agent guidance, which the carve-out's clause (iv) refuses as a
  ride-along, and it is in no task's `Touches`. **Decided on 2026-09-23: left
  unreconciled, owner eugenelim**, recorded here rather than edited.

## Post-gates review round 2

`security-reviewer` returned **clean on adjudication**: all three of its
findings were refuted. Two are worth recording because acting on either would
have been wrong.

- **A non-mapping ceiling *entry* escapes `compile_ceiling` as `AttributeError`**
  — true, and reproduced. Refuted on authority: T1's pinned `Tests` governs the
  `predicates` decode, which is the element frame *inside* an entry. The entry
  frame belongs to `_CEILING_BINDING_FIELDS` and `decode_role_record`, and
  `workspace.toml` `[backlog].closed` records that decision as
  `ceiling-element-unchecked-yields-no-refusal-event`, closed 2026-09-22 across
  the loader's two ceiling seams. Both stored-ceiling callers guard it, and
  inside `compile_role` a non-mapping entry dies one frame earlier in
  `_bound_integrations`. **The guard was drafted and not applied**: installing
  it would have restated a shipped rule in a second place, which is the drift
  this repository's "one nearby example must not become a rule" refuses.
- **AC-0319's entitlements clause is asserted by nothing** — true, and refuted
  on the criterion's own words: it requires an impersonating call to produce
  the same decision and the same recorded event, which the check drives twice
  including the admit path. Nothing in it requires the entitlements ceiling to
  be looked up *by* the step's principal, and no principal reaches `_decide` at
  all. The fix would have changed the `CeilingResolver` shape T1's `Tests` pins
  unchanged for AC-0234, to serve an assembler that does not exist.

`adversarial-reviewer` sustained one Blocker, against the round-1 repair rather
than against the implementation: **the erratum's enumeration claimed a
completeness the grep gate falsified.** It listed the frozen body's `spec.md`
and `plan.md` and missed the same spec's `notes/verification-ledger.md`, while
asserting twice that it was exhaustive; its section locator for `plan.md` named
§ Tasks, which holds no hit, and omitted four sections that do. It also gave a
false ground — that hits inside the spec cannot be repaired — which is true of
the frozen body and **not** of `notes/`.

Repaired by replacing the enumeration with the **rule**: which criteria moved,
which stayed, where the stale sentences live by file and section, and why each
file is left as it is — the body because `docs/specs/README.md` freezes it, the
sibling's ledger because `docs/architecture/README.md` § What is built states
that a shipped spec's ledger records what one delivery observed on its own
date, and the dated history because correcting it would make the log say
something that was never true. A rule has no line numbers to drift.

**That is the second round in which a repair produced the next round's
finding**, which is the divergence condition this delivery already met once at
the spec stage. The repair above removes the surface rather than restating it,
which is what a third round would otherwise be spent on.
