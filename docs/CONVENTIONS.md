# Conventions

How work is done here, for the parts this repository owns itself.

This file used to carry every convention. Most of them now have a canonical
home closer to the thing they govern, and the rest were describing the pack
catalogue rather than this repository. What is left is the reasoning that has
no better owner.

## Where the rest went

| It used to be here | It now lives in |
| --- | --- |
| Document hierarchy, document lifecycle | [`README.md`](README.md) |
| § 1 Charter — what belongs in it, and what does not | [`CHARTER.md`](CHARTER.md) |
| § 2 ADR — when to write one, status values, the never-edited rule | the `new-adr` skill, § When to invoke and § Lifecycle after acceptance |
| § 3 RFC — when to open one, and what is reserved to it | the `new-rfc` skill, § When to invoke |
| § 4 Specs and plans — metadata contract, low-level design, contract vs. construction tests, `contracts/<type>/` | the `new-spec` skill, `references/spec-and-plan-contract.md` |
| § 5 Current-state docs | [`architecture/README.md`](architecture/README.md) and [`product/README.md`](product/README.md) |
| Work intake, commits, pull requests, privacy | [`../AGENTS.md`](../AGENTS.md) |
| Light and full modes, supervisor mode, work-loop state, model selection, the knowledge base, unattended loops | the `work-loop` skill and its `references/` |
| Pack source-of-truth split, credentialed skills, scaling profiles | nowhere — they described the pack catalogue, not this repository, and are retired |

Section numbers in a frozen record still point here. The RFC lifecycle a
frozen record cites is below; everything else resolves through the table above.

## RFC lifecycle

An RFC moves through:

```
Draft → Open → Final Comment Period → Accepted | Rejected | Withdrawn
```

**Optional `Experimental` status.** An RFC that proposes running an
experiment — using an optional `Experiment / validation` section of the RFC
template — may sit in `Experimental` while the trial runs and
results are pending, instead of being forced to a premature Accept or Reject.
Results live in a linked spike note (or a follow-up RFC / superseding ADR),
not the RFC body; when they land, the RFC moves to `Accepted | Rejected |
Withdrawn`. An `Experimental` RFC is still in-flight (Governance class, not
Frozen). Use it only when an experiment is genuinely running.

Once an RFC is **Accepted**, it produces follow-on artifacts:

- Architectural decisions → one or more ADRs
- Concrete features → specs in `docs/specs/`
- Convention changes → an edit to whichever source owns the rule (the change
  itself, not a copy of it); [`../AGENTS.md`](../AGENTS.md) § Documentation
  routes to the owner

After follow-ons exist, the RFC's job is done. It stays in the repo as history.

**Optional `NNNN-notes/` companion.** An RFC may carry a sibling
`docs/rfc/NNNN-notes/` folder for promoted research and supporting material —
sketches, evidence, a distilled research brief lifted from a sustained
investigation — mirroring the optional `notes/` folder a spec carries. It
is optional and informal; the RFC body remains the contract.

## Why the loop has this shape

The mechanics of the loop live in the `work-loop` skill. This section is the
why, which the skill does not carry.

Skip the loop only when a change is cosmetic, tightly local, behavior-preserving,
*and* obviously verifiable — a one-line authentication, migration,
production-config, or public-interface change is not trivial. For everything
else, follow the **plan → execute → verify → review → iterate** loop.

**Why a loop, not a single pass.** LLM self-assessment is unreliable: agents
declare victory when they *feel* done. Mechanical gates (lint, typecheck,
tests) plus an adversarial review pass replace "feel" with verifiable
termination. The loop keeps going until both kinds of check are satisfied —
or it pauses for human replanning.

Before construction, a caller may use `shaping-reviewer` to test a contract's
scope and observability. That is distinct from the later code-review lenses:
adversarial review checks delivery drift, security review checks threats, and
quality review checks maintainability.

**Why think before acting.** The cost of a wrong start is higher than the
cost of thinking. For high-stakes changes (architectural choices, multi-file
refactors, anything touching shared infrastructure), use your agent's
extended-thinking facility — it catches the wrong assumption *before* it
becomes 14 commits of wrong code. For routine work, skip the ceremony; the
discipline is "match thinking depth to stakes," not "always think hardest."

**Why iterate, not retry-from-scratch.** Most loops converge: gates fail,
review surfaces a finding, the next pass fixes it. Restart-from-scratch
loses the planning context. We do it the other way only when fresh context
is the *point* — an unattended, fresh-session-per-iteration loop (see the
work-loop skill).

**Why a hard iteration cap.** Without one, you're hoping. The implementation and review retry caps live as data in `state.json` and are enforced by the `work-loop` skill's `scripts/loop-cohort.py` through `loop-cohort check --phase gates-failed` and `--phase review`; if you hit one, the task is bigger than you thought — pause for human replanning, then stop, re-plan, or split. A cap never declares the accepted intent complete or creates follow-on work automatically.

**Why capture learnings.** A loop that finishes without updating *some*
doc, skill, or note has wasted what it learned. The next agent (or a
human) will pay for it again. The work-loop skill enumerates where each
kind of learning belongs.

### Phase-slice planning

Each journey phase ships its capability and its guide together. A phase whose tooling ships without its guide is not a complete slice — the guide is part of what makes the capability independently usable. Deferring all guides to a terminal documentation wave is an anti-pattern: it accumulates authoring debt, makes earlier phases incompletely documented, and often results in guides that are never written.

**What counts as a guide for a phase:** a Diátaxis artifact in `guides/` that covers the capability the phase introduces. The guide need not be comprehensive — it should orient the user to the capability and link to the reference for the rest.

**Enforcement:** the `author-delivery-brief` skill extends the shippability test to include guides; the `new-rfc` skill requires that when an RFC covers multiple phases, each phase's guides ship with that phase — not in a terminal wave.

## Common rationalizations

These are rationalizations to refuse, whether they arise before the work-loop
loads or while it is running.

| The lie | The rebuttal |
| --- | --- |
| "We'll update the spec after the PR." | Spec drift is a bug, not follow-up work — update spec and code in the same PR. See [`AGENTS.md` § Development workflow](../AGENTS.md#development-workflow) and the spec lifecycle rule in the `new-spec` skill's
`references/spec-and-plan-contract.md`. |
| "I'll verify this manually, just this once." | Verification mode — TDD, goal-based, or manual QA — is declared in the plan task, not improvised at the keyboard. If manual QA is the right mode, write it down; if it isn't, pick TDD or a goal-based check. See the PLAN phase in the `work-loop` skill. |
| "I can fix this while I'm here." | Out-of-scope changes need a separate PR or an explicit note in the plan. Scope creep is the most common cause of failed adversarial review. See [`AGENTS.md` § Development workflow](../AGENTS.md#development-workflow). |
| "This decision doesn't need an ADR — it's obvious." | If you're making it, it isn't obvious to the next person. Writing an ADR now costs less than someone re-litigating the decision in six months. See the `new-adr` skill § When to invoke. |
| "Low-risk, so I'll skip the work-loop." | Load `work-loop` and write its trio anyway — light mode is lean, not absent. The discipline is the point, not the length. |
| "I don't need a spec, I understand the task." | An eligible direct-light request keeps its plan in the active session; it does not persist a spec. If the work needs durability or any risk trigger fires, use `new-spec` for the durable spec and plan. |
| "I'll grep the codebase as I go." | Verify APIs before you start writing, not while you're writing. |
| "I'll match the surrounding code's pattern." | Check the root `AGENTS.md` guidance first; local style may already conflict with the repository's documented convention. |

