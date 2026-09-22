"""Where the role's `model_id` becomes a framework `Model`, and only here.

`role-configuration-seams.md` § 2 gives this module its job: call the pool's
`model_factory` with the role's `model_id`, **after checking
`CED_POOL_ALLOWED_MODEL_IDS`, which is where AC-0251's compile half is
enforced**. It **selects no implementation** — r5 § 2 R3 keeps the `Model`
implementation deploy-time wiring injected by the pool, so nothing here knows
what a Bedrock model is.

**`RoleCompileError` is declared here and not in `ced.agents.compiler`**,
which is where it reads from. The compiler imports this module, so this module
cannot import the compiler; the refusal type has to sit on the side of that
edge the other can reach. `ced.agents.compiler` re-exports it, so a caller
still catches one named type for every compile refusal.

**`pydantic_ai.models.Model` is named in this module and nowhere else**, which
is a ratified constraint rather than a preference. `PoolConfig` lives in
`src/ced/worker/pool.py`, and `tests/architecture/dependency_direction.py`
admits a `pydantic_ai` name only in `agents/` and `adapters/` — its AST walk
reaches a `TYPE_CHECKING`-guarded import too, so the field cannot be annotated
with the framework type where it lives. It is typed by a `Protocol` declared
in `worker/` instead, and the framework name is written here.

**A pool with no factory compiles an agent with no model.** `Agent.__init__`
takes `model: Model | KnownModelName | str | None = None` on the pinned
2.45.0, so the construction succeeds; the run is what fails. That is the
right split for this spec, which issues no provider call anywhere: a compile
that demanded a wired provider could not be exercised offline at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic_ai.models import Model

__all__ = ["RoleCompileError", "resolve_model"]


class RoleCompileError(Exception):
    """The role record cannot become an agent.

    Distinct from `RoleLoadError`, which is the stored record disagreeing with
    its own shape. This is the role disagreeing with the pool, with its own
    bindings, or with what its derived class requires.
    """


def resolve_model(model_id: str, pool: Mapping[str, Any]) -> Model | None:
    """Resolve the role's model id through the pool's factory, or `None`.

    `pool` is the deployment-time configuration read by key — the fields of
    `PoolConfig`, passed as a plain mapping so this layer never imports the
    worker. `None` comes back when the deployment wired no factory.

    AC-0251's compile half is applied first: a `model_id` absent from
    `allowed_model_ids` is refused before any factory is called, and a pool
    that carries no set at all admits nothing. Fail closed — the set is
    required configuration with no in-code default, so an absent one is a
    deployment that never chose, not one that chose everything.
    """
    allowed = tuple(pool.get("allowed_model_ids") or ())
    if model_id not in allowed:
        raise RoleCompileError(
            f"model id {model_id!r} is not in the pool's allowed set {sorted(allowed)}"
        )

    factory = pool.get("model_factory")
    if factory is None:
        return None
    model = factory(model_id)
    if not isinstance(model, Model):
        raise TypeError(
            f"the pool's model_factory returned {type(model).__name__} for "
            f"model id {model_id!r}; a pydantic_ai Model is required"
        )
    return model
