# RFC-0001 — review record

Supporting material for [`0001-initial-project-charter.md`](../0001-initial-project-charter.md).
Not the contract; the RFC body is. This exists so the reviews the RFC relies on
are checkable rather than asserted.

Two rounds of the `new-rfc` pre-handoff gate ran on 2026-09-09, each dispatching
three independent reviewers with no shared context: an adversarial reviewer, a
security reviewer scoped to the trust model, and a fresh reader given the RFC and
forbidden from opening any other file.

## Round 1 — gate failed

**Adversarial:** 7 blockers. The decisive one: the RFC claimed the foundation
intents hold technology open, when they ratify a closed constraint set including
the agent runtime, the production host, and the model-access posture. The RFC's
central justification was therefore false. Also found: an internal contradiction
about whether architecture had run; the design doc uncited as the source of its
own amendments; no principle carrying the concrete example `CONVENTIONS.md` § 1
requires; `## Domain` both decided and open; and a Risks mitigation citing text
`CONVENTIONS.md` § 1 does not contain.

**Security:** 3 blockers, "not safe to ratify". The agent-privilege exclusion was
hollowed by two qualifiers — "unrestricted" permitted *restricted* shell and
infrastructure control, and "production" carved out development agents. No
tenancy posture existed while the mission implied a workbench. And principle 3's
auto-publish rested on a gate the charter never characterised: verification
establishes provenance, but the architecture's unmitigated reference-selection
channel means an adversary supplying only *resolvable* evidence produces output
that trips no flag — where the adversary is the company under analysis, authoring
the filings the system ingests.

**Fresh reader:** declined to sign off. Undefined vocabulary; process bookkeeping
addressed to the author as the document's third block; six unnamed intents
carrying a third of the argument.

## Round 2 — gate failed again

**Adversarial:** 6 blockers. The decisive one: the proposed charter **restated
three ratified constraints**, which is precisely what the RFC's own Option C was
rejected for — and both copies differed from the ratified wording, downgrading
"open-source reference implementation" to an intention and widening the
privilege floor beyond what was ratified. The recommended option was not the
option implemented. Two further findings were prior blockers relabelled rather
than closed (the options axis) or reintroduced in a new location (tenancy,
decided in the charter while its owning intent still holds it open).

**Security:** 1 blocker. Extending the agent-privilege clause to bind development
agents made it **false at ratification** — the agents that produced this RFC used
network browsing and shell execution under interactive grants where the model
authors the arguments. A scope exclusion the project visibly violates cannot
reject a request.

**Fresh reader:** "not without changes, but small ones". Confirmed the round-1
architecture contradiction, edit-count inconsistency, and conventions paraphrase
were fixed. Remaining: the six intents still unnamed after two revisions; the
security review credited with seven charter provisions but unlocatable; and a
gap — the charter invites cloud portability while AWS is ratified in the intents,
so the charter alone would let a contributor accept work the constraints forbid.

## What the security review contributed to the charter

These clauses originate from the round-1 security review and survive into the
current text:

| Clause | Finding it answers |
| --- | --- |
| Principle 1's untrusted-input posture | Verification is provenance, not resistance to adversarial selection |
| Principle 3's reserved-criteria clause | "Flagged" was definable by ordinary PR, narrowing a reserved principle |
| Principle 3 naming the self-approval default | "Humans retain control" was satisfiable by the requester approving their own output |
| Principle 5's static-credential exception | The principle asserted short-lived credentials while the design introduces one static credential |
| Principle 5's human-held-authorship invariant | Nothing stopped a runtime identity authoring its own authority |
| The security-pattern fitness exclusion | The charter claimed fitness for patterns rated `[moderate]` on self-evaluated evidence |

Two security findings were **not** applied to the charter and are recorded here
instead:

- **Tenancy.** The reviewer asked for a tenancy exclusion. Adding one closed a
  question `portable-identity-first-runtime` still holds open, in the repo's
  slowest-to-amend document. Routed back to that intent.
- **The decidable fragment admits string prefixes**, so an argument the callee
  *interprets* — a URL, a path — accepts an attacker-chosen suffix while passing
  containment as sound. Architecture-level; unapplied. Recorded in the design
  doc's follow-on work.

## Process finding worth keeping

Round 2's regression rate was the signal, not its blocker count. Two blockers
were prior findings relabelled or reintroduced, which is a different failure from
the architecture review loop — where four rounds produced zero regressions
because each round elaborated new material rather than repairing the same
surface. The response was to stop patching and strip the RFC's wrapper back,
rather than run a third round with the same instrument on the same material.
