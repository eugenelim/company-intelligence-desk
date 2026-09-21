"""The pin itself: manifest, installed distribution and seam module agree.

ADR-0002 D1 pins `pydantic-ai-slim` exactly. Three places can state that
version and only one of them is enforced by a resolver, so this module asserts
all three name the same release. A downgrade of the environment reds here
first, which is what the recorded downgrade transcript exercises.
"""

from __future__ import annotations

import tomllib
from importlib.metadata import version
from pathlib import Path

from ced.adapters.framework_contract import (
    FRAMEWORK_DISTRIBUTION,
    PINNED_FRAMEWORK_VERSION,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _manifest_pin() -> str:
    """Return the version `pyproject.toml` pins the framework to."""
    manifest = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = manifest["project"]["dependencies"]
    pins = [r for r in requirements if r.split("[")[0].strip() == FRAMEWORK_DISTRIBUTION]
    assert len(pins) == 1, f"expected exactly one {FRAMEWORK_DISTRIBUTION} requirement: {pins}"
    specifier = pins[0].split("]")[-1]
    assert specifier.startswith("=="), f"the framework must be pinned exactly, got {pins[0]!r}"
    return specifier.removeprefix("==").strip()


def test_the_manifest_pins_the_version_the_seam_module_names() -> None:
    assert _manifest_pin() == PINNED_FRAMEWORK_VERSION


def test_the_installed_distribution_is_the_pinned_version() -> None:
    assert version(FRAMEWORK_DISTRIBUTION) == PINNED_FRAMEWORK_VERSION


def test_the_bedrock_extra_is_installed() -> None:
    """The provider seam must be importable, or a contract over it proves nothing.

    No provider is reached: importing the module only proves the `[bedrock]`
    extra of the pin resolved.
    """
    from pydantic_ai.models.bedrock import BedrockConverseModel

    assert BedrockConverseModel.__module__ == "pydantic_ai.models.bedrock"
