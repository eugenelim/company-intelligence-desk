# Spec: Walking skeleton — authority containment

- **Status:** Shipped <!-- Draft | Approved | Implementing | Shipped | Archived -->
- **Owner:** eugenelim
- **Plan:** [`plan.md`](plan.md)
- **Constrained by:** [`runtime-architecture.md`](../../architecture/inspectable-multi-agent-diligence/runtime-architecture.md) r8, [`worker-runtime.md`](../../architecture/pydantic-ai-worker-runtime/worker-runtime.md) r5, [ADR-0001](../../adr/0001-pydantic-ai-as-the-agent-framework.md), ADR-0002 (version pin, created by the foundation spec)
- **Brief:** none
- **Descends from:** `runtime-architecture.md` § 10 Rollout, Phase 1
- **Discovery:** none
- **Contract:** none — this spec exposes no interface surface; it is a domain library, reached through the decision point `walking-skeleton-policy-decision-point` builds
- **Shape:** service

> **Spec contract:** this document defines what "done" means. The implementing
> PR must match this spec, or update it. Verification must be derivable from it.
>
> **Not every section is contract.** `Agent Rules`, `Testing Strategy` and
> `Acceptance Criteria` are what a completion gate reads, and an amendment
> changes them. `Outcome`, `What Changes`, `Durable Outputs`, `Follow-ons` and
> `Assumptions` are working material, corrected in place as the work teaches,
> without an amendment and without a review round. A review finding against
> working material is advisory — it cannot block, because nothing gates the text
> it cites. Marking the tiers is the spec's job; honouring them when a finding
> is adjudicated is the reviewing surface's.
>
> **A recorded threat, fail direction, or residual gap may sit in any section,
> but removing one always takes an amendment.** § Follow-ons exists to record a
> known gap, so restricting where such a statement may live would forbid that
> section its purpose; what needs gating is deletion, not placement. A control's
> *operative* definition is different and belongs in `Agent Rules` or
> `Acceptance Criteria`.

## Outcome

An engineer can see a tool argument that passes a string prefix check, but means
something else to the code that parses it, refused as outside the acting role's
ceiling. Success is that the refusal is decided over the parsed value rather
than the raw string, and that a predicate a reviewer cannot decide is rejected
when the role is authored rather than when the call fires.

## What Changes

- The containment fragment, deciding whether an argument value falls inside a ceiling over parsed components — a new domain library under `src/ced/domain/containment/`.
- The canonicaliser each domain type runs before that decision — the same package.
- The fragment's declaration surface, which refuses what a reviewer cannot decide: an unrecognised domain type, an argument with no predicate, a predicate argument with no canonical form, a prefix predicate on an interpreted type, a predicate outside its type's row, a domain argument that is a public suffix, a `url` argument with no host-constraining predicate and one with no scheme-constraining predicate or a scheme the egress path cannot carry, and a `within` root that is relative or the whole filesystem. Of those, the public-suffix refusal is AC-0215's and the host-constraining refusal is AC-0240's; the **scheme** refusal and the **`within`-root** refusal are beyond the criteria and ratified separately, as is the call-completeness denial at evaluation, which is not a declaration refusal and so is not on this list. § Follow-ons records all three.
- The containment suite and its property test over generated predicate pairs — `tests/containment/`.
- The userinfo bypass row, added to the unsafe-prefix table — `docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md` § 4.

## Durable Outputs

| Semantic role | Applicability | Destination | Owner | Expected evidence | Closeout condition |
| --- | --- | --- | --- | --- | --- |
| Decision rationale | Applicable — the r5 containment table omits a bypass this spec's criteria carry | `docs/architecture/pydantic-ai-worker-runtime/worker-runtime.md` § 4, "Why a prefix predicate is not safe on an interpreted argument" | work-loop | The userinfo row added to the unsafe-prefix table | The criterion's referenced table is complete |
| Current architecture | Applicable — `docs/architecture/README.md` § What is built is the current map and this spec changes it | `docs/architecture/README.md` § What is built | work-loop | The containment fragment moved out of "designed and not built" | The section names what exists after this spec and nothing it does not |
| Reusable learning | Applicable — this spec produces the containment evidence Phase 2 plans against | `spikes/README.md` | work-loop | A section stating what was established **and what was not** | Hypothesis checks reported separately from setup |
| Current architecture — the `worker-runtime.md` marker | Not applicable — r5's STATUS header names the *authorization boundary* as unbuilt, and that clause is only true once the decision point ships; [`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/spec.md) owns it | — | — | — | — |
| Interface compatibility | Not applicable — no interface surface; the API belongs to the foundation spec | — | — | — | — |
| User-facing promise | Not applicable — nothing user-facing is deployed until Phase 2 | — | — | — | — |

## Agent Rules

The three-tier guard that keeps an implementing agent inside the lines.
*Always do* applies without asking; *Ask first* requires human sign-off
before proceeding; *Never do* is a hard rule, even under time pressure.

### Always do

- Treat r8 and r5 as ratified. Implement what they specify; where implementation shows one wrong, stop and say so rather than designing around it.
- Record what a check does **not** establish alongside what it does.

### Ask first

- Any change to a ratified decision. The plan gives every DR decision this spec constructs a disposition, so this boundary is enforceable rather than aspirational.
- Adding a dependency beyond those in the plan's § Dependencies & integration.
- Relaxing a criterion because it is expensive to demonstrate.

### Never do

- **No test-only bypass surface inside a shipped security control.** Mutation evidence is produced by patching in the test process, never by a switch the production canonicaliser carries.
- **No canonicaliser that normalises before it decodes.** Percent-decoding runs before dot-segment removal; the reverse order admits an encoded traversal, which a probe confirmed on 2026-09-18. AC-0216 cannot see a transposition that keeps every rule, so this rule and T1's pinned transposition case are the only things holding the order.
- **No `pydantic_ai` import in this spec's code.** The containment fragment is a pure domain library with no framework dependency; the repository-wide rule confining `pydantic_ai` to `agents/` and `adapters/` still applies.

## Testing Strategy

Every criterion sits in exactly one group.

- **TDD (AC-0213, AC-0214, AC-0215, AC-0216, AC-0217, AC-0218, AC-0240, AC-0315, AC-0316, AC-0317)** — all of it, because all of it is a compressible invariant with a cheap oracle and no provider in the loop. The criteria additionally carry a *property test* over generated predicate pairs, because the claim is set-theoretic containment over a fragment rather than behaviour at chosen values.

No criterion here calls a provider, and none reaches the database: the fragment
is a pure domain library, so the whole suite runs under
`pytest -m 'not substrate'`. This spec needs no cloud credential and carries no
spend.

## Acceptance Criteria

Obligations come from `worker-runtime.md` § 10 Rollout criterion 8 — the
containment property test with interpreted arguments — which covers AC-0213,
AC-0214 and AC-0215. Obligations **beyond** it are tabled below, and the
approval gate rules on each rather than inheriting it.

| Obligation | Criteria | Why it is here | If cut |
| --- | --- | --- | --- |
| Require a host predicate on a `url` argument | AC-0240 | AC-0215 and AC-0217 narrow a predicate's *form*; neither requires a `url` argument to carry any host constraint at all. A ceiling of `scheme_in{https}` alone is well-formed, satisfies AC-0316 — it does constrain the argument — and admits every host, including the link-local instance-metadata address. This criterion is the `url`-specific strengthening of AC-0316: some predicate is not enough, it has to be one that constrains the host. **AC-0240 requires a host-constraining predicate to be present. It does not constrain which host that predicate admits, and it does not reach the address the host resolves to.** r5 § 4 makes `host_eq(h)` expressible, so `host_eq("169.254.169.254")` satisfies this criterion and still authorises the metadata endpoint; § Follow-ons records that neither gap is owned | A `url` argument ships with no host constraint whatever, which is a strictly larger hole than the one the remaining gaps leave |
| Prove each canonicalisation rule is load-bearing | AC-0216 | r5 criterion 8 asks for the table rows, the adapter assertion and the public-suffix refusal. It does not ask whether any individual rule in § 4, "Why a prefix predicate is not safe on an interpreted argument"'s "What the canonicalizer must do" list actually carries weight, and a rule nobody's case exercises is indistinguishable from an absent one. **The criterion asks for weight, not for one shape of evidence.** r5's framing sentence — "because each omission is a known bypass" — holds for the traversal, encoding and ambiguity clauses and not for the two that normalise: no predicate in r5's `url` row ranges over a port, and a ceiling's host argument is already case-folded when compared, so removing either can admit nothing. Implementation showed that, so the criterion takes the fail-closed form for those two rather than a demand for evidence that cannot exist | A canonicaliser can lose a rule in a refactor with every test still green — or, with the first wording, a rule that cannot produce an admitting case gets one manufactured, which is what the first implementation attempt did |
| Narrow the decidable fragment at authoring time | AC-0217 | This is the narrowed decidable fragment amendment, which narrows the ratified fragment; it is a design change this spec implements rather than a § Rollout criterion | A prefix predicate stays expressible on an interpreted type, which is the one unsound constructor the change exists to remove |
| Admit the positive path | AC-0218 | Every other containment criterion is a refusal, and a canonicaliser that refuses all input satisfies all of them | The fragment ships correct by being useless, and nothing catches it |
| Constrain every argument a ceiling entry names | AC-0316, AC-0317 | r5 § 4 defines the fragment as "a conjunction of independent per-argument predicates", and a conjunction over a subset is **vacuously true on every argument outside it**. AC-0240 rescues one case — a `url` with no host constraint — and nothing rescues the rest: an `fs-path` with no `within(root)` admits `/etc/passwd`, and an argument the entry simply omits is decided *inside* by every criterion here. AC-0315 does not reach it, because the fragment can decide such an argument; it just decides wrongly. Two criteria because the failure modes and remedies differ: AC-0316 refuses the declaration, AC-0317 denies at evaluation for an entry that reached the database by some other route — the same relationship `walking-skeleton-role-compilation`'s AC-0233 has to AC-0235 | A default-allow sits under the whole fragment: every criterion is green and a ceiling constrains only the arguments somebody remembered to name |
| Deny at the seam an input the fragment cannot decide | AC-0315 | The fragment is consumed across a spec boundary: [`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/spec.md) installs it and decides what to do with what it returns. Every other criterion here is an authoring-time refusal or a decided call, so an input that reaches evaluation and cannot be decided — an unrecognised domain type, an ambiguous parse, a predicate the fragment cannot evaluate — has no stated answer. Returning "inside" or passing the value through is then a valid implementation, and on the far side of the seam nothing catches it: that spec's AC-0236 fires only on a raise, its AC-0235 needs a missing ceiling entry, and its AC-0207 needs a decidable entry to fall outside of. **This criterion fixes the seam's signal as a raise**, which is what makes AC-0236 the receiving control rather than an assumption about one | A fail-open default sits at the authorization boundary, owned by neither spec, in exactly the shape the AC-0217 follow-on predicts |

**Containing an interpreted argument**

- [x] **AC-0213.** Every row of `worker-runtime.md` § 4, "Why a prefix predicate is not safe on an interpreted argument"'s unsafe-prefix table is refused, plus the userinfo case `https://www.sec.gov@attacker.example/`, which a prefix check admits while the parsed host is `attacker.example`. A row added to that table upstream is an amendment trigger for this criterion.
- [x] **AC-0214.** The adapter observes the canonical value rather than the original string, asserted at the adapter rather than at the validator.
- [x] **AC-0215.** Declaring a domain-containment predicate whose argument is a public suffix is refused at authoring time, resolved against a public-suffix dataset rather than a hand-kept list.
- [x] **AC-0216.** For every canonicalisation rule `worker-runtime.md` § 4, "Why a prefix predicate is not safe on an interpreted argument" names under "What the canonicalizer must do", the suite establishes that the rule carries weight, in whichever of two forms the rule admits. **Where omitting the rule can admit a value the canonicaliser otherwise refuses**, the suite holds such an input: refused as the canonicaliser stands, and admitted when that one rule is disabled by patching the canonicaliser **in the test process**. Disabling one rule reds that rule's case and leaves the others passing. **Where omitting the rule can admit nothing**, the suite instead holds four things: that the rule performs its normalisation; that removing it admits nothing the full pipeline refuses, over a universe the suite **demonstrates the rule acts on** — the values are written down, and what makes them evidence is a check that the rule changes the canonical form of more than one of them, so a universe the rule never touches reds instead of passing vacuously; a recorded reason naming why no admitting input exists; and **a check that derives that reason from the fragment** rather than asserting it — named per rule, so a rule entering this form without one is refused by the suite rather than admitted by its author. A ground that rests on two facts needs both derived: case-folding qualifies only if the predicates are insensitive to host case *and* the declaration surface folds a ceiling's host argument, and a check that assumes the second establishes neither. Only two grounds admit a rule to this form, and both are properties of the predicate table rather than of the canonicaliser: **no predicate ranges over the component the rule normalises**, which is why `drop default ports` qualifies, or **the normalisation is monotone against an already-canonical ceiling argument**, so that removing it can only shrink the admitted set, which is why case-folding a host qualifies while `host_eq` and `host_in_domain` do range over the host. A rule with no evidence in either form is what this criterion refuses. **A rule added to that list upstream, or a predicate constructor added to the fragment, is an amendment trigger for this criterion** — the second because the weaker form's grounds are claims about which components a predicate reads.
- [x] **AC-0240.** Declaring a `url`-typed argument with no host-constraining predicate is refused at authoring time.
- [x] **AC-0217.** Declaring a prefix predicate on an argument whose domain type is `url`, `fs-path`, or `content-locator` is refused, and the same predicate on `opaque-string` is accepted.
- [x] **AC-0218.** A canonical in-ceiling `url` and an in-root `fs-path` each evaluate to an admitting result against the same ceiling AC-0213 uses. The tool-body half of the positive path is [`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/spec.md)'s AC-0318, because no tool body runs in this spec.
- [x] **AC-0316.** Declaring a ceiling entry that names an argument and attaches no predicate to it is refused at authoring time, and the refusal names both the entry and the unconstrained argument.
- [x] **AC-0317.** Evaluating a ceiling entry against a call that supplies an argument the entry attaches no predicate to denies, asserted against an entry installed directly rather than through the authoring surface.
- [x] **AC-0315.** Evaluating a ceiling entry the fragment cannot decide — an argument whose declared domain type the fragment does not recognise, an argument whose parse is ambiguous, or a predicate it cannot evaluate against the given value — raises, and returns neither an admitting nor a passthrough result. Asserted at the fragment's evaluation entry point for each of the three cases.

## Follow-ons

The first group is criterion-wording defects a spec-stage shaping or security
review found. Most sit in text this spec carries unchanged from the deleted
`walking-skeleton-agent-runtime`; the AC-0240 entry is the exception and is a
defect in text this spec authored. They were left unreworded by owner decision of
2026-09-20, so the wording stays comparable against the parent's; each needs an
amendment rather than an in-place correction. The parent directory is gone, so
that comparison is no longer possible against the parent itself — what the
decision now preserves is that the wording was not quietly changed after the
defects were found. § Assumptions records the criterion-level provenance.

- eugenelim: this spec § Acceptance Criteria — **AC-0213 double-counts the row its own task files upstream.** T1 amends the r5 unsafe-prefix table to add the userinfo row, after which the criterion's "plus the userinfo case" names a row already in the table and its own amendment trigger fires on the change the task made.
- eugenelim: this spec § Acceptance Criteria — **AC-0216 proves rule presence, not rule order.** Disabling one canonicalisation rule at a time cannot see a refactor that keeps every rule and transposes percent-decode with dot-segment removal, which the plan's own probe records as load-bearing. Held in the interim by this spec's `Never do` rule on canonicaliser ordering and T1's pinned transposition case, neither of which is a criterion.
- eugenelim: this spec § Acceptance Criteria — **AC-0217 hand-enumerates three of seven domain types.** r5 states the rule at the level of "not parsed by their consumer"; adding an interpreted type later leaves the criterion green and the fragment unsound.
- eugenelim: this spec § Acceptance Criteria — **AC-0240 requires a host predicate and constrains neither the host it names nor the address it resolves to.** `host_eq("169.254.169.254")` satisfies the criterion and authorises the instance-metadata endpoint. Two distinct gaps sit behind it and neither is owned. A value-level constraint — refusing a link-local, private-range or metadata host at authoring time — belongs to this fragment and has no criterion. Address-level confinement belongs to a control that does not exist: r8 § 4 specifies the egress proxy as a *hostname* allowlist plus a token bucket, with no private-range or metadata block anywhere in r8 or r5, so the proxy shares the identical blind spot and cannot be the owner. DNS rebinding is unowned for the same reason. Phase 1 registers no URL-taking tool, which is what bounds the exposure today rather than any control.
- eugenelim: this spec § Acceptance Criteria — **a `url` argument's scheme is unconstrained by any criterion.** AC-0240 requires a host-constraining predicate and nothing requires a scheme-constraining one, so `file://sec.gov/etc/passwd` satisfies `host_eq("sec.gov")` while every resolver ignores that authority — the predicate AC-0240 forces to be present decides nothing about what the callee opens. T1 refuses such a declaration at authoring time, fail-closed and beyond any criterion. Found by the implementation security review of 2026-09-23. **Ratified by eugenelim on 2026-09-23**: the refusal stands, on the grounds that it closes a default-allow of the class AC-0316 and AC-0317 already close, and that it fails at authoring time where an author sees it rather than as a denied call in production. **Requiring a scheme predicate's presence does not close the `file:` case those grounds name** — `scheme_in{file}` satisfies presence — so the refusal bounds the set as well: a `url` argument may name only `https`. r8 § 2's trust table states the scheme for this system's one egress edge — "Ingestion job | Egress proxy → SEC | scheduled fetch | HTTPS" — and r8 § 3 and § 4 describe that proxy as a *hostname* allowlist with a token bucket, naming no scheme set. An earlier wording of this entry admitted `http` too, citing an "HTTP allowlist" in r8 § 4 that r8 does not contain. That is the one place this fragment constrains a predicate's *value* and not only its presence, and it is deliberate, because a control whose recorded grounds name a case it admits is worse than no control. AC-0240's host-value gap is left as it is, recorded above. Neither refusal is carried by a criterion.
- eugenelim: this spec § Acceptance Criteria — **a call may omit an argument the ceiling constrains, and no criterion decides what happens.** AC-0316 and AC-0317 close an argument no predicate ranges over; the mirror — a predicate no argument arrives for — is unowned, and deciding only the arguments a call supplies makes an empty call an admission against any ceiling. T1 denies an incomplete call, fail-closed and beyond any criterion, which also means AC-0218's two admitting values travel in one call rather than two. Found by the implementation security and quality reviews of 2026-09-23. **Ratified by eugenelim on 2026-09-23**, with the consequence stated as the fragment actually behaves, because an earlier wording gave advice the code denies. `evaluate` denies in **both** directions: an argument the entry constrains and the call omits, and an argument the call supplies that the entry attaches no predicate to. So an entry that declares only the arguments it will always receive does not merely leave an optional argument unconstrained — it **denies every call that supplies one**. There is no declaration shape in the shipped fragment that admits a genuinely optional argument. The remedy when that binds is an explicit optional marker on the declaration, which does not exist yet and which [`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/spec.md) would own; it is **not** relaxing either direction, and the omitted-argument direction in particular is what stopped an empty call being an admission against any ceiling.
- eugenelim: this spec § Acceptance Criteria — **`within(root)` has no analogue of AC-0215's public-suffix refusal, and no criterion says a root must be absolute.** `within("/")` is present, satisfies AC-0316, and admits `/etc/passwd`; `within("")` and `within("relative/dir")` resolve against whatever directory the worker started in, so the declaration's text does not say what it admits and two workers enforce different ceilings from one role record. T1 refuses all three, beyond any criterion. **Ratified by eugenelim on 2026-09-23**, on the same grounds as the scheme refusal above. A general rule for a root too shallow to bound anything is still not attempted and has no owner.
- eugenelim: `publicsuffix2` — **the bundled public-suffix dataset is a 2019-12-21 snapshot with no refresh path.** The distribution has shipped no release since, so suffixes delegated after that date — the platform suffixes anyone can register under, `pages.dev` and `vercel.app` among them — answer "not a public suffix" and are authorable, which is the outcome AC-0215 exists to refuse. The plan's § Risks names dataset ageing and assumed a version bump would make it visible; no bump exists. `PUBLIC_SUFFIX_DATASET_AS_OF` and a test now make the snapshot's date visible. Choosing a dataset with a refresh path is an Ask-first dependency change. **Owner decision of 2026-09-23: the dependency stays, and the gap is recorded rather than triggered.** Nothing in Phase 1 registers a URL-taking tool, so nothing can reach the gap today — and **that is a fact about the catalogue, not a control**, exactly as the AC-0240 entry above says of its own bound. An earlier wording of this entry called the record a trigger a reader of the queue would meet. It is not one: integrations are data in this design, so registering a URL-taking tool is an operator insert that opens no pull request and passes no backlog entry, and `workspace.toml` states that an entry's `summary` is non-semantic and must not determine dispatch. Replacing or refreshing the suffix source is owed before a URL-taking tool is registered; the only place that can be enforced is the path that compiles a ceiling from a registry row, which [`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/spec.md) owns and this spec does not. Recorded in `workspace.toml` `[backlog].open` against `src/ced/domain/containment/ceiling.py` as `public-suffix-dataset-has-no-refresh-path`, and unowned until that spec takes it.
- eugenelim: this spec § Acceptance Criteria — **`fs-path` confinement is decided against a `realpath` snapshot the callee later re-resolves.** `realpath` is non-strict, so a component that does not exist at decision time resolves lexically; if it is later created as a symlink out of the root, the admitted path points elsewhere when the callee opens it. Handing the resolved path on narrows the window to the gap between decision and open rather than closing it. Unowned; closing it needs an open-then-verify at the callee, which is the decision point's surface.
- eugenelim: `worker-runtime.md` r5 § 4 — **no predicate ranges over a URL's query component.** An admitted `https://www.sec.gov/evidence/x?q=…` reaches the adapter with an unbounded model-chosen component, which on an allowed host is an outbound channel the ceiling does not describe. This follows the ratified fragment, so it is recorded rather than changed here.
- eugenelim: this spec § Acceptance Criteria — **no explicit symlink case.** r5 requires normalisation to resolve symlinks, but AC-0213's enumerated cases are all name-only, so CWE-59 confinement escape rests on an implementer reading one prose clause as a listed rule.

**Deliberately not carried here.**

- eugenelim: `worker-runtime.md` r5 § 4 — **`may_exist`, the first of its three containment gates and the authoring-time one.** Designed, not built. The charter holds the substrate single-author in operation until the governance gaps are *built*, and this is one of them; a single operator authors every role here, which is the condition that makes deferring it safe. The spawn-time gate `may_run` is [`walking-skeleton-policy-decision-point`](../walking-skeleton-policy-decision-point/spec.md)'s follow-on, beside the call-time gate that spec builds.

## Assumptions

- Product: the skeleton carries one analysis role with a single registered tool, over the recorded fixture rather than a live corpus — the thinnest agent set that exercises every criterion — and nobody has confirmed it (settled by: the approval gate).
- Process: six of this spec's ten criteria descend from `walking-skeleton-agent-runtime`, whose directory was deleted on 2026-09-20. AC-0240 was authored on 2026-09-20 in the spec this one was cut from, and AC-0315 on 2026-09-23; neither has a parent there. **The enumeration is recorded here because the parent is gone and cannot be re-derived.** Carried across with their wording unchanged: AC-0213, AC-0214, AC-0215, AC-0216, AC-0217, AC-0218. Authored new on 2026-09-20: AC-0240. Authored new on 2026-09-23: AC-0315, closing a fail-open seam the cut created, and AC-0316 and AC-0317, closing a default-allow that predates the cut and survived three review rounds. None has been re-derived against the parent, and with the parent deleted none now can be; the four defects in § Follow-ons are what review found in the carried text without reworking it.
- Process: eugenelim approves both the spec and the plan gates. **This is self-approval, labelled rather than presented as review.** The project is single-operator and the author is the approver; what independent scrutiny these artifacts had came from forked-context reviewer agents and not from a second person. `worker-runtime.md` carries the same qualification in its Reviewers field, and it applies here for the same reason.
