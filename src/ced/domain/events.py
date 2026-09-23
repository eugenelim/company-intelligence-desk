"""The event envelope, the reserved type, and the derived idempotency key.

Pure rules. Nothing here opens a connection — the two append paths live in
`ced.adapters.postgres.event_log`, and the database, not this module, is what
refuses a forged policy decision.

This module holds the vocabulary both sides agree on. **"Agree" means checked,
not asserted**, and the three shared names are checked in three different ways:

  * `RESERVED_EVENT_TYPE` — behaviourally, by `tests/event_log/test_privilege_split.py`,
    which passes this constant into the database and asserts the refusal.
  * `RUN_LIFECYCLE_TYPES` and `TERMINAL_EVENT_TYPES` — structurally, by
    `tests/schema/test_migration_applies.py`, which reads the migration's
    function body and the partial index out of the catalogue and compares them
    against these values.

Review round 1 added the second of those, because `RUN_LIFECYCLE_TYPES` was
re-declared independently in the migration with nothing joining the two.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final
from uuid import UUID

#: The one event type the worker's general write path refuses, and the only
#: type the policy path writes. r7 § Identity — two layers.
RESERVED_EVENT_TYPE: Final = "policy.decision"

#: Appended before any step exists, with `step_id` and `agent_role` null.
#: r7 § Event log names exactly these two on the run-lifecycle path.
RUN_REQUESTED: Final = "run.requested"
RUN_CANCELLED: Final = "run.cancelled"
RUN_LIFECYCLE_TYPES: Final = frozenset({RUN_REQUESTED, RUN_CANCELLED})

#: r7 § Event log — liveness and termination: a terminal event closes the
#: stream. `expired` is a run *state* and is deliberately not here: it is
#: non-terminal and an approver can reopen it.
#:
#: Nothing in `walking-skeleton-foundation` appends one — `append_run_event`
#: admits only the two run-lifecycle types, and the run state machine that
#: produces terminal events is `walking-skeleton-evidence`'s. The set is here
#: because revision 0001's partial index names the same three types, and
#: `tests/schema` asserts the two agree so they cannot drift apart.
TERMINAL_EVENT_TYPES: Final = frozenset({"run.completed", "run.failed", RUN_CANCELLED})

#: The step-scoped type carrying a derived idempotency key. Named because the
#: partial unique index in revision 0002 is scoped to it.
TOOL_INVOKED: Final = "tool.invoked"

#: The step-scoped type closing a tool invocation. r5 § 2 names the pair
#: `tool.invoked` / `tool.completed` on the observability layer, and says
#: `tool.completed` records the parse outcome so a rejected result is
#: attributable rather than merely absent. It carries no unique index, so it
#: is not named by a migration — it is here because its partner is, and a
#: second home for half a pair is how the two drift.
TOOL_COMPLETED: Final = "tool.completed"

#: A stored role record the loader refuses, appended at the **load** stage.
#: `role-configuration-seams.md` § 3: a record the loader rejects is appended
#: with its own event type rather than as a step fault, so an operator can
#: tell a bad role file from a runtime fault without attaching a debugger.
#:
#: **The spelling is constrained by `events_type_is_canonical`**, revision
#: 0001's CHECK `^[a-z0-9]+(\.[a-z0-9]+)+$`: each dot-separated segment is
#: lowercase ASCII alphanumerics only. `role.load_failed` — the spelling two
#: ratified drafts carried — fails it on the underscore, and so would
#: `role-load-failed`. `tests/compiler/test_refusal_is_readable.py` decides
#: this against the shipped database rather than against a copy of the
#: pattern, and pairs each admitted type with the rejected underscore
#: spelling so a disabled constraint cannot pass for a satisfied one.
ROLE_LOAD_FAILED: Final = "role.load.failed"

#: A role the compiler refuses, appended at the **compile** stage. Its own
#: type for the same reason and under the same constraint: AC-0261 asks that
#: the refusal be distinguishable by type from a runtime fault, and the
#: envelope carries `agent_role`, which names the role that failed.
#:
#: **Which guard refused is deliberately absent.** The `events` envelope has
#: no column for it and this spec writes no payload object; the spec that
#: opens that write path owns the other half, and the spec's § Follow-ons
#: carries the register entry.
ROLE_COMPILE_REFUSED: Final = "role.compile.refused"

#: The step-scoped **vocabulary** is deliberately not enumerated here or in the
#: schema. `walking-skeleton-policy-decision-point` gives the step-event toolset
#: the behaviour that emits `tool.invoked` and `tool.completed`, and an enum
#: frozen now would make each later type a migration against a shipped spec.
#: What the database enforces instead is the negative rule that matters:
#: the worker path refuses the reserved type, and the run-lifecycle path
#: accepts only the two names above.
#:
#: The **character shape** is constrained, and that is a different thing.
#: `events.type` has carried a CHECK on the character shape since review
#: round 5 (revision 0001); round 5's admitted `_` and `-` as separators and
#: round 6 narrowed it to a dotted run of lowercase ASCII alphanumerics, which
#: is the rule now. Any `foo.bar` name is still
#: admitted without a migration, so the declined decision stands; what the
#: shape buys is that the negative rule above is exhaustive by construction,
#: because no invisible character or homoglyph spelling of a refused name can
#: be stored at all. Two rounds of denylists failed at exactly that.
#:
#: Three named constants for step types lived here with no caller and were
#: removed in review round 1 under `AGENTS.md` § Cut before adding rung 1. The
#: sibling spec adds the names its toolset actually emits.


@dataclass(frozen=True)
class EventEnvelope:
    """One committed event, as r7 § Event log specifies it.

    `seq` is per-run and dense from 1. It is allocated by the append function
    inside the append transaction, so it is read back from the database rather
    than chosen here.
    """

    schema_version: int
    run_id: UUID
    seq: int
    type: str
    principal: str
    step_id: UUID | None = None
    agent_role: str | None = None
    payload_ref: str | None = None
    idempotency_key: str | None = None


def derived_idempotency_key(run_id: UUID, step_id: UUID, tool_call_id: str) -> str:
    """Derive the key for a tool invocation. Never mint one per attempt.

    A key minted per attempt dedups nothing: the retry would carry a new key
    and the partial unique index would admit it. Deriving it from the run, the
    step and the model's own tool-call identifier makes a re-execution of the
    *same* logical invocation collide, which is the property the fence-detection
    window needs: two workers can be inside one step's toolset stack while the
    losing one has not yet noticed, and this is what makes that overlap benign.

    **The overlap's bound is one heartbeat interval only if the renewal fails
    promptly, and nothing here enforces that.** The heartbeat connection sets no
    `connect_timeout` and no `statement_timeout`, so a partitioned-but-alive
    worker can block inside `renew` past its own lease expiry while another
    worker claims and runs the same step — an unbounded window, not a 20-second
    one. Recorded rather than designed around: a timeout is deployment
    machinery this spec puts out of scope, and the idempotency key is what makes
    the overlap survivable at any width.

    **The limit is recorded rather than designed around.** The key is stable
    across a resume from the same message history, and *not* across a
    re-planned retry: a new model turn mints a new `tool_call_id`, so the
    second invocation is a genuinely different logical call and is admitted.
    """
    digest = hashlib.sha256()
    digest.update(str(run_id).encode("utf-8"))
    digest.update(b"\x00")
    digest.update(str(step_id).encode("utf-8"))
    digest.update(b"\x00")
    digest.update(tool_call_id.encode("utf-8"))
    return digest.hexdigest()
