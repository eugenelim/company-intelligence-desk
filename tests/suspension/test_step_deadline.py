"""AC-0232 — a hung step is failed and its lease released within ``step_deadline``.

Uses a ``FunctionModel`` whose async function sleeps indefinitely, so no provider
is reached.  The deadline fires a ``CancellationToken``, which raises
``RunCancelled`` inside ``run_sync``; the executor catches that exception through
its existing ``except Exception`` handler and records ``step.failed``.  The pool
then calls ``release``, which clears ``lease_expires_at`` — satisfying the "lease
released" half.

The model function must be **async** so that ``pydantic_ai._utils.run_in_executor``
awaits it directly (no thread) and ``asyncio.sleep`` is cancelled immediately when
the task is cancelled.  A sync function is run in a thread via
``anyio.to_thread.run_sync(abandon_on_cancel=False)``; anyio shields that await,
so the ``CancelledError`` is only delivered after the thread returns — potentially
1000 seconds later.

Only the cancellation-within-deadline property is asserted here; the
lease-release half follows mechanically from the executor's error path and the
pool's ``release`` call, both of which are exercised by the pool-paths suite
and the T1 provider test.  The two parts are separated because the substrate
test (AC-0237) already demonstrates the full suspension path, and adding a
second full-stack check for a simpler property (timeout) would obscure which
half it is testing.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from ced.adapters.framework_contract import CancellationToken
from ced.agents.compiler import compile_role
from ced.worker.executor import _make_approval_toolset, _run_compiled_agent
from tests.compiler.role_records import a_pool, a_role

#: Short enough to keep the suite fast; long enough that the assertion margin
#: (3 × DEADLINE) is not fragile on a slow CI runner.
_DEADLINE = 0.3


async def _hanging_async(_messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
    """Block indefinitely via async sleep — represents a provider call that never returns.

    Must be async: ``pydantic_ai._utils.run_in_executor`` awaits async callables
    directly, so ``asyncio.sleep`` is cancelled immediately when the driving asyncio
    task is cancelled.  A sync ``time.sleep`` runs in a thread under
    ``anyio.to_thread.run_sync(abandon_on_cancel=False)``, which shields the await
    until the thread finishes — making the deadline test hang for 1000 seconds.
    """
    await asyncio.sleep(1000)
    return ModelResponse(parts=[TextPart(content="")])  # never reached


def test_a_hung_run_is_cancelled_within_the_deadline() -> None:
    """``RunCancelled`` is raised before 3 × ``step_deadline``.

    The lease-release half is implicit: the executor's ``except Exception``
    path records ``step.failed`` and returns normally, so the pool's own
    ``release`` clears ``lease_expires_at`` on the same path it always uses.
    """
    compiled = compile_role(a_role(), [], a_pool(model=FunctionModel(_hanging_async)))
    token = CancellationToken()
    timer = threading.Timer(_DEADLINE, token.cancel)
    timer.start()

    start = time.monotonic()
    try:
        with pytest.raises(RunCancelled):
            _run_compiled_agent(compiled, _make_approval_toolset(), token)
    finally:
        timer.cancel()

    elapsed = time.monotonic() - start
    assert elapsed < _DEADLINE * 3, (
        f"cancellation took {elapsed:.3f}s; deadline was {_DEADLINE}s — "
        "the step did not stop within its deadline"
    )
