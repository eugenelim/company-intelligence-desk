"""The deployed configuration declares its non-provider id, and still boots.

This is the boot-and-Compose half only. The compile it ends on is admitted
because the deployment wires no `model_factory`, so no model resolves and
there is nothing to interrogate — which is why the carve-out's discriminating
check lives next door and runs against a pool whose factory does resolve.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ced.agents.compiler import compile_role
from ced.worker import pool as pool_module

from ..compiler.role_records import STUB_MODEL_ID, a_quarantined_role

COMPOSE = Path(__file__).resolve().parents[2] / "deploy" / "compose.yaml"

#: The services `tests/fault_injection` needs alive. Both must carry the
#: declaration, not just the one a reader happens to check.
WORKER_SERVICES = ("worker-a", "worker-b")


def _environment(service: str) -> dict[str, str]:
    """The environment Compose gives one service, with anchors resolved."""
    compose: dict[str, Any] = yaml.safe_load(COMPOSE.read_text())
    return {
        key: str(value) for key, value in compose["services"][service]["environment"].items()
    }


def test_both_worker_services_declare_the_stub_and_validate() -> None:
    """Each worker boots with the declaration `stub:counting` needs.

    `validate_pool_config` is what `verify_boot` runs before either
    connection, so a value Compose sets wrongly fails here rather than on a
    machine with the substrate up.
    """
    for service in WORKER_SERVICES:
        config = pool_module.validate_pool_config(_environment(service))
        assert config.non_provider_model_ids == (STUB_MODEL_ID,)


def test_the_deployed_configuration_still_compiles_a_role() -> None:
    """The worker's own configuration compiles the role it admits."""
    config = pool_module.validate_pool_config(_environment("worker-a"))
    compiled = compile_role(
        a_quarantined_role(),
        (),
        {
            "default_limits": config.default_limits,
            "allowed_model_ids": config.allowed_model_ids,
            "non_provider_model_ids": config.non_provider_model_ids,
        },
    )

    assert compiled.agent.model is None
