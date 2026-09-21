"""§ Grounding probe rows 4, 7 and 12 — the model surface.

Row 4's second half (a reasoning part type exists) is asserted in
`test_message_history.py`, where the part is round-tripped rather than merely
named.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.bedrock import BedrockConverseModel
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.settings import ModelSettings


def _never_called(messages: object, info: object) -> ModelResponse:
    """A `FunctionModel` body that must not run: counting happens before the request."""
    raise AssertionError("the model was asked for a response, not a token count")


def test_model_settings_declares_thinking() -> None:
    """Row 4, first clause. DR8 turns thinking off, so the key has to exist to be set.

    `ModelSettings` is a `TypedDict`: the key is read off its optional-key set,
    because an instance is a plain dict and would accept any key at runtime.
    """
    assert "thinking" in ModelSettings.__optional_keys__
    assert "thinking" not in ModelSettings.__required_keys__


def test_the_bedrock_model_requires_only_a_model_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Row 7. ADR-0001 D2 rests on the model id being the whole construction input.

    Ambient AWS configuration is pointed at empty paths so the assertion is
    about the framework and not about the developer's machine. A region is the
    provider's own deployment-time input, not a second constructor argument.
    No network call is made: constructing a client does not reach a provider.
    """
    required = [
        name
        for name, parameter in inspect.signature(
            BedrockConverseModel.__init__
        ).parameters.items()
        if name != "self" and parameter.default is inspect.Parameter.empty
    ]
    assert required == ["model_name"]

    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "credentials"))
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    model = BedrockConverseModel("anthropic.claude-3-5-sonnet-20240620-v1:0")
    assert model.model_name == "anthropic.claude-3-5-sonnet-20240620-v1:0"
    assert model.system == "bedrock"


def test_counting_tokens_ahead_of_a_request_is_unimplemented_on_the_test_models() -> None:
    """Row 12. AC-0246's stub exists because neither shipped test model can count.

    A settings read would pass on a flag that is set and never consulted, so
    the criterion needs a counting stub. This pins why: the base class raises,
    and neither `TestModel` nor `FunctionModel` overrides it.
    """
    assert "count_tokens" in vars(Model)
    assert "count_tokens" not in vars(TestModel)
    assert "count_tokens" not in vars(FunctionModel)

    models: tuple[Model, ...] = (TestModel(), FunctionModel(_never_called))
    for model in models:
        with pytest.raises(NotImplementedError):
            asyncio.run(model.count_tokens([], None, ModelRequestParameters()))
