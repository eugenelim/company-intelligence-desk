"""AC-0007 — the dependency-direction gate, shown failing and shown passing.

A gate nobody has watched fail is not evidence. Each test here writes a real
forbidden import into the real package tree, asserts the check reports it, and
removes it — so the assertion is about the check's behaviour under violation,
not about the current tree happening to be clean.

The spec's Never-do is specifically *"weakening the test to pass the build is
the failure this gate exists to catch"*, which is why the injected file is a
real module under `src/ced/` and not a fixture tree somewhere the production
walker never looks.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from .dependency_direction import PACKAGE_ROOT, violations

#: Named so a leaked file is obviously test debris rather than product code.
_PROBE_NAME = "_ac0007_violation_probe.py"


#: Writes `source` into `src/ced/<layer>/` and returns the path it wrote.
Inject = Callable[[str, str], Path]


@pytest.fixture
def inject() -> Iterator[Inject]:
    """Write a module into a layer, then remove it however the test ends."""
    written: list[Path] = []

    def _write(layer: str, source: str) -> Path:
        path = PACKAGE_ROOT / layer / _PROBE_NAME
        path.write_text(source, encoding="utf-8")
        written.append(path)
        return path

    try:
        yield _write
    finally:
        for path in written:
            path.unlink(missing_ok=True)


def test_the_tree_is_clean_as_committed() -> None:
    """The committed tree has no forbidden import.

    This one cannot fail on its own merits, so it is not the evidence for
    AC-0007 — it is the control the two injection tests are measured against.
    """
    assert violations() == []


@pytest.mark.parametrize(
    ("layer", "source", "expected_rule"),
    [
        ("domain", "import pydantic_ai\n", "pydantic_ai"),
        ("api", "from pydantic_ai import Agent\n", "pydantic_ai"),
        ("worker", "import pydantic_ai.models\n", "pydantic_ai"),
        ("domain", "import boto3\n", "AWS SDK"),
        ("api", "from botocore.config import Config\n", "AWS SDK"),
        ("worker", "import boto3\n", "AWS SDK"),
        ("agents", "import boto3\n", "AWS SDK"),
    ],
)
def test_a_forbidden_import_is_refused(
    inject: Inject, layer: str, source: str, expected_rule: str
) -> None:
    """AC-0007 — the check fails on a deliberately introduced import."""
    inject(layer, source)

    found = [v for v in violations() if v.path.name == _PROBE_NAME]

    assert found, f"{expected_rule} import in {layer}/ was not reported"
    assert {v.rule for v in found} == {expected_rule}
    assert {v.layer for v in found} == {layer}


@pytest.mark.parametrize(
    ("layer", "source"),
    [
        ("agents", "import pydantic_ai\n"),
        ("adapters", "import pydantic_ai\n"),
        ("adapters", "import boto3\n"),
        ("adapters", "from botocore.config import Config\n"),
    ],
)
def test_a_permitted_import_is_not_refused(inject: Inject, layer: str, source: str) -> None:
    """The rule admits the placements it is supposed to admit.

    Without this half the gate could be a rule that refuses everything, which
    is not a dependency-direction rule — it is a build break.
    """
    inject(layer, source)

    assert [v for v in violations() if v.path.name == _PROBE_NAME] == []


@pytest.mark.parametrize(
    "source",
    [
        'import importlib\n\nimportlib.import_module("boto3")\n',
        '__import__("boto3")\n',
        'import importlib\n\nimportlib.import_module("pydantic_ai")\n',
    ],
)
def test_a_dynamic_import_is_refused(inject: Inject, source: str) -> None:
    """The AST walk catches what a grep over import statements would miss."""
    inject("domain", source)

    assert [v for v in violations() if v.path.name == _PROBE_NAME]


def test_removing_the_violation_makes_the_check_pass_again(inject: Inject) -> None:
    """AC-0007's second half — green once both violations are removed."""
    pydantic_probe = inject("domain", "import pydantic_ai\n")
    aws_probe = inject("worker", "import boto3\n")
    assert len(violations()) == 2

    pydantic_probe.unlink()
    aws_probe.unlink()

    assert violations() == []
