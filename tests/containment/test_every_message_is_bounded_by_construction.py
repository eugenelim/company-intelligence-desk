"""No message this package produces may interpolate a value unbounded.

Every text the fragment hands a consumer is recorded: a `Denied` reason
becomes the `policy.decision`, and AC-0315 makes a `ContainmentUndecidable`
the signal the decision point records as a denial too. So an unbounded
interpolation lets one refused call write an event row as large as the caller
cares to make it.

**This is a structural check because four call-site fixes were not enough.**
The bound was installed on the path each round's defect was found on, and
each time a sibling path still interpolated raw — the undecidable messages,
then a caller-supplied argument name, then a set-valued predicate, then a
third-party exception's own text, which embeds the whole netloc it was raised
for. A rule applied by hand to the sites somebody thought of is not a rule.

So this reads the package's own syntax tree and requires that every value
interpolated into a message go through `for_the_record`, which is where the
budget lives. A new raise site cannot pass without it, whether or not anyone
remembers this file exists.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

PACKAGE: Final[Path] = (
    Path(__file__).resolve().parents[2] / "src" / "ced" / "domain" / "containment"
)

#: What may be interpolated into a message directly. `for_the_record` is the
#: budget; `_describe` bounds a predicate and is covered by its own cases;
#: `len` returns an integer.
_BOUNDED_CALLS: Final[frozenset[str]] = frozenset({"for_the_record", "_describe", "len"})

#: Everything that builds a text a consumer records.
_MESSAGE_BUILDERS: Final[frozenset[str]] = frozenset(
    {"ContainmentUndecidable", "CeilingDeclarationRefused", "Denied", "_refuse"}
)

#: The one interpolation exempt from the rule, and why. `_refuse`'s `why`
#: arrives already composed by a caller, and that caller's own
#: interpolations are checked here like any other — bounding `why` again
#: would cut the prose rather than the value.
_COMPOSED_ELSEWHERE: Final[frozenset[tuple[str, str]]] = frozenset({("ceiling.py", "why")})


def _raw_interpolations(path: Path) -> list[str]:
    """Return every message interpolation in `path` that is not bounded."""
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id not in _MESSAGE_BUILDERS:
            continue
        arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
        for argument in arguments:
            for inner in ast.walk(argument):
                if not isinstance(inner, ast.FormattedValue):
                    continue
                value = inner.value
                bounded = (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id in _BOUNDED_CALLS
                )
                exempt = (path.name, ast.unparse(value)) in _COMPOSED_ELSEWHERE
                if not bounded and not exempt:
                    found.append(f"{path.name}:{inner.lineno}: {{{ast.unparse(value)}}}")
    return found


def test_the_scan_finds_the_package_and_its_message_sites() -> None:
    """Setup check: a scan that parsed nothing would pass over anything."""
    modules = sorted(path.name for path in PACKAGE.rglob("*.py"))
    assert modules == [
        "__init__.py",
        "canonicaliser.py",
        "ceiling.py",
        "domain_types.py",
        "errors.py",
        "predicates.py",
    ], modules

    sites = 0
    for path in PACKAGE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in _MESSAGE_BUILDERS
            ):
                sites += 1
    assert sites >= 20, f"only {sites} message sites found; the scan is not reaching them"


@pytest.mark.parametrize(
    "module", sorted(path.name for path in PACKAGE.rglob("*.py")), ids=lambda name: name
)
def test_no_message_interpolates_a_value_unbounded(module: str) -> None:
    raw = _raw_interpolations(PACKAGE / module)
    assert not raw, "unbounded interpolations in a recorded message:\n  " + "\n  ".join(raw)
