"""AC-0263 — usage limits are in force during a step run: identity and enforcement.

**Identity:** a tool inside the executor's injected toolset reads
``RunContext.usage_limits`` during the run.  The test asserts that value is
the identical object ``compile_role`` resolved — not a value the test itself
supplied to ``run_sync``.  The distinction matters because ``RunContext.usage_limits``
is always the caller's own object (measured ``is`` → ``True``); a test that
passes the limits and reads them back asserts a tautology.  Here the test
calls ``_run_compiled_agent``, which is the executor's code path, so the test
never touches ``agent.run_sync`` directly.

**Enforcement:** a run driven past one of the resolved thresholds
(``request_limit = 0``) raises ``UsageLimitExceeded``.  This is a
framework-regression guard: on the 2.45.0 pin enforcement and identity are
inseparable (the framework enforces against the very object it exposes), but
a future pin that accepts a limits object and stops applying it would pass the
identity check and red this one.

Note: ``tool_calls_limit = 0`` is not used here because deferred tool
requests (``requires_approval=True``) bypass the ``tool_calls_limit`` check
— the framework intercepts them before counting, so the limit never fires.
``request_limit = 0`` fires before the first model call and is not
intercepted by the approval mechanism.

Neither half reaches a provider.  Both run offline.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai.usage import UsageLimits

from ced.agents.compiler import compile_role
from ced.agents.tools.approval import request_approval
from ced.worker.executor import _make_approval_toolset, _run_compiled_agent
from tests.compiler.role_records import POOL_DEFAULT_LIMITS, a_pool, a_role


def test_usage_limits_identity() -> None:
    """``RunContext.usage_limits`` seen from the run equals ``compiled.limits``.

    The observation tool is in the executor-injected toolset, not the compiled
    stack, so no policy decision point stands between the model call and the
    observation.  ``_run_compiled_agent`` is the executor's own function; the
    test does not call ``agent.run_sync`` itself.
    """
    compiled = compile_role(a_role(), [], a_pool(model=TestModel()))

    captured: list[UsageLimits] = []

    def observe(ctx: RunContext[Any]) -> str:
        """Read and capture the usage limits the executor threaded through."""
        captured.append(ctx.usage_limits)
        return "observed"

    # Build an observation toolset that also includes the real approval tool so
    # TestModel's call_tools='all' triggers suspension after observing.
    toolset: FunctionToolset[Any] = FunctionToolset()
    toolset.add_function(observe)
    toolset.add_function(request_approval, requires_approval=True)

    # _run_compiled_agent is the executor's function — not agent.run_sync.
    # It passes compiled.limits as usage_limits; the test only observes.
    _run_compiled_agent(compiled, toolset)

    assert len(captured) == 1, f"expected one observation, got {len(captured)}"
    assert captured[0] is compiled.limits, (
        "RunContext.usage_limits must be the identical object compile_role resolved, "
        f"got {captured[0]!r} (id={id(captured[0])}), expected id={id(compiled.limits)}"
    )


def test_usage_limits_are_enforced() -> None:
    """A run driven past a resolved threshold is refused by the framework.

    Sets ``request_limit = 0`` so the first model request exceeds the limit
    before any model response arrives.  This is the regression guard: a pin
    that carries limits but never enforces them would pass the identity test
    and red here.
    """
    tight_limits = {**POOL_DEFAULT_LIMITS, "request_limit": 0}
    compiled = compile_role(
        a_role(), [], a_pool(model=TestModel(), default_limits=tight_limits)
    )

    with pytest.raises(UsageLimitExceeded):
        _run_compiled_agent(compiled, _make_approval_toolset())
