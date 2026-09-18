"""The dependency-direction rule, as data plus an AST walker.

Two rules, no more, taken verbatim from `walking-skeleton-foundation`
§ Boundaries — Never do:

  * no `pydantic_ai` import outside `agents/` and `adapters/`
  * no AWS SDK import outside `adapters/`

The walker reads the AST rather than the text. A grep over source lines finds
neither `importlib.import_module("boto3")` nor `__import__("boto3")`, and finds
the word `boto3` inside a comment or a docstring — so it would be both
incomplete and noisy, in the two directions that matter for a gate.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "ced"

#: Callables whose first positional argument names a module at runtime.
_DYNAMIC_IMPORTERS = frozenset({"import_module", "__import__"})


@dataclass(frozen=True)
class Rule:
    """One forbidden-import rule.

    `distributions` are matched against the *root* of a dotted module path, so
    `botocore.session` matches `botocore`. `allowed_layers` are the immediate
    subdirectories of `src/ced/` where the import is permitted.
    """

    label: str
    distributions: frozenset[str]
    allowed_layers: frozenset[str]


RULES: tuple[Rule, ...] = (
    Rule(
        label="pydantic_ai",
        distributions=frozenset({"pydantic_ai"}),
        allowed_layers=frozenset({"agents", "adapters"}),
    ),
    Rule(
        label="AWS SDK",
        # `aiobotocore` is named because it is the async path to the same
        # authority, and a rule that names only the sync client is a rule with
        # a documented hole.
        distributions=frozenset({"boto3", "botocore", "aiobotocore"}),
        allowed_layers=frozenset({"adapters"}),
    ),
)


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    rule: str
    module: str
    layer: str

    def __str__(self) -> str:
        return (
            f"{self.path}:{self.line}: {self.rule} import {self.module!r} "
            f"in layer {self.layer!r}"
        )


def _layer_of(path: Path) -> str:
    """Return the layer a source file belongs to.

    A file directly under `src/ced/` (`__init__.py`, say) has no layer; it is
    reported as `<package root>`, which no rule allows. That is deliberate:
    the package's own top level is not a place for a framework import.
    """
    relative = path.relative_to(PACKAGE_ROOT)
    return relative.parts[0] if len(relative.parts) > 1 else "<package root>"


def _imported_modules(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """Yield `(line, dotted-module)` for every import this file performs."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            # `from . import x` has module None and is never a third party.
            if node.module is not None and node.level == 0:
                yield node.lineno, node.module
        elif isinstance(node, ast.Call):
            name = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else node.func.id
                if isinstance(node.func, ast.Name)
                else None
            )
            if name in _DYNAMIC_IMPORTERS and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    yield node.lineno, first.value


def violations(package_root: Path = PACKAGE_ROOT) -> list[Violation]:
    """Return every forbidden import under `package_root`, in file order."""
    found: list[Violation] = []
    for path in sorted(package_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        layer = _layer_of(path)
        for line, module in _imported_modules(tree):
            root = module.split(".")[0]
            for rule in RULES:
                if root in rule.distributions and layer not in rule.allowed_layers:
                    found.append(
                        Violation(
                            path=path.relative_to(package_root.parents[1]),
                            line=line,
                            rule=rule.label,
                            module=module,
                            layer=layer,
                        )
                    )
    return found
