"""Pre-release check: does the role need the approval gate?

A role that declares ``needs_approval: true`` has its pre-release check fail,
which causes the executor to offer the gated tool to the agent (AC-0302). A
role that does not declare it — or declares it ``false`` — passes cleanly, and
the agent never sees the gated tool, satisfying the "no unconditional approval
gate" boundary.

The check is deliberately minimal: it reads one flag from the role record and
returns a bool. The complexity is not in the check but in what the executor does
with it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["check_prerelease_failed"]


def check_prerelease_failed(role: Mapping[str, Any]) -> bool:
    """Return ``True`` if the role's pre-release check fails (approval needed).

    A failed check causes ``offered_approval_gated_tools`` to return a
    non-empty list. A passing check causes it to return ``[]``, so the agent
    never sees the gated tool (AC-0302).

    The flag is ``needs_approval`` inside the role's ``model_settings`` object.

    **Fail-open is split precisely** (entry 18 adjudication):

    * ``model_settings`` absent (``None``) → **pass**: a role with no
      ``model_settings`` needs no gate, and that is the correct semantics.
    * ``model_settings`` present but not a ``Mapping`` → **refuse**: a value
      that cannot be read as structured configuration is malformed, and silently
      disabling the approval control is the wrong direction.
    * ``needs_approval`` key absent from a valid ``model_settings`` → **pass**:
      the key absent means the role author did not declare a gate.
    * ``needs_approval`` is ``True`` → **fail** (gate applied).
    * ``needs_approval`` is ``False`` → **pass**.
    * ``needs_approval`` present but not a ``bool`` → **refuse**: a non-boolean
      value in a gate field is an authoring error and must not silently disable
      the control.

    **Why inside ``model_settings`` rather than a top-level column.** The
    ``agent_role`` table has no ``needs_approval`` column, and revision 0005
    adds no such column — the flag belongs to the role's behavioural
    configuration, which lives in the JSONB ``model_settings`` object alongside
    ``model_id`` and ``settings``. Adding a top-level column would be a schema
    change outside this revision's enumerated parts.
    """
    model_settings = role.get("model_settings")
    if model_settings is None:
        return False
    if not isinstance(model_settings, Mapping):
        raise ValueError(
            "role model_settings is present but not a mapping; cannot read needs_approval flag"
        )
    flag = model_settings.get("needs_approval")
    if flag is None:
        return False
    if not isinstance(flag, bool):
        raise ValueError(
            f"needs_approval must be a boolean, got {type(flag).__name__!r}; "
            "a non-boolean value in a gate field silently disables the control"
        )
    return flag
