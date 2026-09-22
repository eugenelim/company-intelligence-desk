"""Role records, pool mappings and counting models, for the compiler's tests.

The records here are the shape `decode_role_record` returns: plain mappings
read from `agent_role`, which is what `compile_role` takes. Nothing here
invents a field the migration does not carry.

**The models count their own turns.** Several criteria are about what does
*not* happen after a refusal — no re-prompt over untrusted text, no further
model turn after a denial — and a request count is the only way to observe
that. `TestModel` answers no such question, so these wrap `FunctionModel`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

#: The four integer keys `role-configuration-seams.md` § 5 gives, at values a
#: role may narrow. The flag is pool-owned and always `false` here, per
#: ADR-0006 D1.
POOL_DEFAULT_LIMITS: Mapping[str, int | bool] = {
    "per_request_input_tokens_limit": 4000,
    "input_tokens_limit": 40000,
    "request_limit": 8,
    "tool_calls_limit": 4,
    "count_tokens_before_request": False,
}

#: A model id, not a provider name: nothing here reaches a provider.
STUB_MODEL_ID = "stub:counting"


def a_ceiling_entry(tool_name: str = "fetch_filing") -> dict[str, Any]:
    """One binding, carrying the three fields § 2 fixes plus its predicates."""
    return {
        "integration_name": "filing-archive",
        "integration_version": 1,
        "tool_name": tool_name,
        "predicates": {},
    }


def an_integration(
    *,
    integration_name: str = "filing-archive",
    version: int = 1,
    trust_class: str = "admitted-types",
    tools: Sequence[str] = ("fetch_filing",),
    pool_classes: Sequence[str] = (),
) -> dict[str, Any]:
    """One pinned registry row, in the shape `load_role` hands the compiler.

    The defaults resolve `a_planning_role`'s default ceiling entry: the same
    `(integration_name, integration_version)` pin, and a `tools` array holding
    the tool that entry binds. An empty `pool_classes` is the column's own
    default and means available to every pool class.
    """
    return {
        "integration_name": integration_name,
        "version": version,
        "trust_class": trust_class,
        "kind": "http",
        "adapter_ref": None,
        "connection_ref": None,
        "credential_scope": None,
        "arg_schema": {},
        "ceiling_fragment": {},
        "pool_classes": list(pool_classes),
        "tools": list(tools),
        "owner_scope": None,
    }


def a_role(
    *,
    role_name: str = "analysis",
    ceiling: Sequence[Mapping[str, Any]] = (),
    output_schema_ref: str = "reference-selection",
    settings: Mapping[str, Any] | None = None,
    limits: Mapping[str, Any] | None = None,
    pool_class: str | None = None,
    model_id: str = STUB_MODEL_ID,
) -> dict[str, Any]:
    """A role record. Quarantined by default, because an empty ceiling is.

    `pool_class` defaults to absent, which AC-0258 makes meaningful rather
    than neutral: such a role matches only integrations whose `pool_classes`
    is empty.
    """
    return {
        "role_name": role_name,
        "version": 1,
        "ceiling": list(ceiling),
        "pool_class": pool_class,
        "instructions": "",
        "model_settings": {
            "model_id": model_id,
            "settings": dict(settings or {}),
            "limits": dict(limits or {}),
        },
        "output_schema_ref": output_schema_ref,
        "display_name": None,
        "owner_scope": None,
    }


def a_quarantined_role(**overrides: Any) -> dict[str, Any]:
    """An empty ceiling and the closed-vocabulary contract the class requires."""
    return a_role(role_name="quarantine", output_schema_ref="reference-selection", **overrides)


def a_planning_role(
    *, tool_names: Sequence[str] = ("fetch_filing",), **overrides: Any
) -> dict[str, Any]:
    """A non-empty ceiling, so the derivation makes it not quarantined."""
    return a_role(
        role_name="analysis",
        ceiling=[a_ceiling_entry(name) for name in tool_names],
        output_schema_ref="finding-set",
        **overrides,
    )


def a_pool(
    *, model: Any = None, default_limits: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """The deployment-time configuration, as the plain mapping the seam takes.

    `model_factory` is absent unless a model is given, which is the state the
    approved stub pins: a pool that wired no factory still compiles.
    """
    pool: dict[str, Any] = {
        "default_limits": dict(
            POOL_DEFAULT_LIMITS if default_limits is None else default_limits
        ),
        "allowed_model_ids": [STUB_MODEL_ID],
    }
    if model is not None:
        pool["model_factory"] = lambda model_id: model
    return pool


@dataclass
class CountingModel:
    """A `FunctionModel` that records how many turns the framework asked for.

    `turns` is the number of model requests issued, which is what the two
    "and then nothing further happened" criteria are decided on.
    """

    reply: Any
    turns: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.model = FunctionModel(self._respond)

    def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.turns.append(len(self.turns) + 1)
        return self.reply(info)


class CountsTokensModel(FunctionModel):
    """A model that counts tokens ahead of the request and records the request.

    AC-0246 needs both halves. `Model.count_tokens` raises `NotImplementedError`
    with no override on `TestModel` and on `FunctionModel` alike —
    `tests/contract/test_model_surface.py` pins that — so a model exercising
    the pre-request bound has to implement it. And a settings read would pass
    on a flag that is set and never consulted, so `requests` is what makes
    "before the request was issued" an observation rather than an inference.
    """

    def __init__(self, input_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.requests: list[int] = []
        super().__init__(self._respond)

    def _respond(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.requests.append(len(self.requests) + 1)
        return returns_an_empty_selection(info)

    async def count_tokens(
        self,
        messages: list[ModelMessage],
        model_settings: Any,
        model_request_parameters: Any,
    ) -> RequestUsage:
        """Report a fixed input-token count without reaching a provider."""
        return RequestUsage(input_tokens=self.input_tokens)


def returns_an_empty_selection(info: AgentInfo) -> ModelResponse:
    """Call the output tool with arguments its schema accepts."""
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"references": []})])


def calls_the_only_tool(info: AgentInfo) -> ModelResponse:
    """Ask for the one domain tool the role binds."""
    return ModelResponse(parts=[ToolCallPart(info.function_tools[0].name, {"cik": "0000000a"})])


def returns_a_malformed_output(info: AgentInfo) -> ModelResponse:
    """Call the output tool with arguments its schema rejects."""
    return ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, {"references": "not-a-list"})]
    )
