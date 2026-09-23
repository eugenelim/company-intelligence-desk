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


#: Which arguments of a builder are message *text*. `_refuse` takes an entry
#: name and an argument name as fields it bounds itself — its own body is
#: scanned like any other builder — and only its third argument is a message.
#: Everything not listed here has all of its arguments checked.
_MESSAGE_ARGUMENTS: Final[dict[str, tuple[int, ...]]] = {"_refuse": (2,)}

#: Helpers a message may interpolate directly. Each returns bounded text and
#: is scanned itself, below — an allowlisted helper that nothing checks is
#: the hole the allowlist creates.
_BOUNDED_HELPERS: Final[frozenset[str]] = frozenset({"_describe"})


def _builder_name(node: ast.Call) -> str | None:
    """Return the name a call resolves to, attribute-qualified or not.

    `errors.ContainmentUndecidable(...)` is the same message as
    `ContainmentUndecidable(...)`, and reading only `ast.Name` would skip it.
    """
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _bounded_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and _builder_name(node) in _BOUNDED_CALLS


def _unbounded_in(expression: ast.expr, path: Path) -> list[str]:
    """Return why `expression` is not an acceptable message, if it is not.

    **Rejected by shape, not detected by shape.** An earlier version walked
    for `ast.FormattedValue` nodes, so five ordinary spellings reported
    nothing while interpolating raw: a message built into a local first,
    `%`-formatting, `.format()`, `+` concatenation, and a builder reached as
    an attribute. A rule that lists the shapes it knows is a rule that a new
    shape walks past, which is the mistake this whole check exists to stop
    repeating one level up.
    """
    where = f"{path.name}:{expression.lineno}"
    if isinstance(expression, ast.Constant):
        return []
    if _bounded_call(expression):
        return []
    if isinstance(expression, ast.JoinedStr):
        found: list[str] = []
        for part in expression.values:
            if isinstance(part, ast.Constant):
                continue
            if isinstance(part, ast.FormattedValue) and _bounded_call(part.value):
                continue
            if isinstance(part, ast.FormattedValue):
                rendered = ast.unparse(part.value)
                if (path.name, rendered) in _COMPOSED_ELSEWHERE:
                    continue
                found.append(f"{where}: raw {{{rendered}}}")
            else:  # pragma: no cover — a JoinedStr holds only these two
                found.append(f"{where}: unrecognised f-string part")
        return found
    return [
        f"{where}: a message must be a literal, a bounded call, or an f-string "
        f"whose every interpolation is bounded, not {type(expression).__name__} "
        f"({ast.unparse(expression)[:60]})"
    ]


def _raw_interpolations(path: Path) -> list[str]:
    """Return every message in `path` that is not bounded by construction."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _builder_name(node) not in _MESSAGE_BUILDERS:
            continue
        builder = _builder_name(node)
        positions = _MESSAGE_ARGUMENTS.get(str(builder))
        arguments = [*node.args, *(keyword.value for keyword in node.keywords)]
        if positions is not None:
            arguments = [arguments[index] for index in positions if index < len(arguments)]
        for argument in arguments:
            found.extend(_unbounded_in(argument, path))

    # The helpers the allowlist trusts are scanned too: every string
    # `_describe` can return is a message, and its own f-strings sit outside
    # any builder call, so nothing else would look at them.
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in _BOUNDED_HELPERS:
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Return) and inner.value is not None:
                found.extend(_unbounded_in(inner.value, path))
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
