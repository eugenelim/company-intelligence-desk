"""What the containment suite shares: the ceiling, the record, the mutations.

Three things live here because more than one module needs them and a second
copy of any of them would be a second thing to keep true.

1. **The ceiling AC-0213 uses**, which AC-0218 also uses, so that a
   canonicaliser refusing every input cannot pass both.
2. **Readers over `worker-runtime.md` § 4**, so the criteria that carry an
   amendment trigger keyed to that document's content actually red when the
   document changes. A row or a clause restated here would test the copy.
3. **The mutations AC-0216 needs**, which live in the suite because the spec's
   first `Never do` refuses a disable switch inside a shipped security
   control. They patch the module-level rule tuples for the duration of one
   `with` block and put them back afterwards.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ced.domain.containment import canonicaliser
from ced.domain.containment.canonicaliser import CanonicalisationRule, UrlUnderReview
from ced.domain.containment.ceiling import CeilingEntry, declare
from ced.domain.containment.predicates import HostInDomain, PathWithin, SchemeIn, Within

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
WORKER_RUNTIME: Final[Path] = (
    REPO_ROOT / "docs" / "architecture" / "pydantic-ai-worker-runtime" / "worker-runtime.md"
)

#: The § 4 sub-section every criterion in this spec cites.
_SECTION_HEADING: Final[str] = (
    "### Why a prefix predicate is not safe on an interpreted argument"
)

#: The root the `fs-path` half of the ceiling is bounded by. Not a real
#: directory: every case that needs one on disk builds it under `tmp_path`.
#: Canonicalising an `fs-path` resolves symlinks against the host filesystem,
#: so a machine that *did* carry `/evidence` — as a symlink above all — would
#: change what these cases mean. `test_the_evidence_root_is_not_on_this_host`
#: is what stops that being silent.
EVIDENCE_ROOT: Final[str] = "/evidence"


@dataclass(frozen=True)
class UnsafePrefixRow:
    """One row of r5's unsafe-prefix table, as the document states it."""

    ceiling: str
    value: str
    callee_sees: str


def _section() -> str:
    """Return the text of the § 4 sub-section, up to the next heading."""
    text = WORKER_RUNTIME.read_text(encoding="utf-8")
    after = text.split(_SECTION_HEADING, 1)
    assert len(after) == 2, f"{WORKER_RUNTIME} no longer carries {_SECTION_HEADING!r}"
    return after[1].split("\n### ", 1)[0]


def unsafe_prefix_rows() -> tuple[UnsafePrefixRow, ...]:
    """Return every row of the unsafe-prefix table, read from the document.

    Parsed rather than restated. AC-0213 says a row added upstream is an
    amendment trigger, and a trigger nothing reads is a sentence.

    **Every body row of the table comes back**, whatever shape its ceiling
    cell is written in. Filtering on the shape the two original rows happen to
    use would let a row stating its ceiling some other way pass through
    unnoticed, which is the trigger failing to fire in exactly the case it
    exists for. The suite is what decides it cannot classify a row.
    """
    body = _section().split("| Ceiling | Value that passes | What the callee sees |", 1)
    assert len(body) == 2, "the unsafe-prefix table's header row is no longer there"
    rows: list[UnsafePrefixRow] = []
    for line in body[1].splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        assert len(cells) == 3, f"unsafe-prefix table row is not three cells: {line!r}"
        rows.append(
            UnsafePrefixRow(
                ceiling=cells[0].strip("`"),
                value=cells[1].strip("`"),
                callee_sees=cells[2],
            )
        )
    return tuple(rows)


def canonicaliser_clauses() -> str:
    """Return the "What the canonicalizer must do" paragraph, whitespace-flattened.

    One string rather than a parsed list, because the document states the
    rules as prose. Every rule's `clause` has to appear inside it, and the
    paragraph itself is pinned, so an upstream edit reds rather than passing
    quietly.
    """
    section = _section()
    start = section.index("**What the canonicalizer must do**")
    paragraph = section[start:].split("\n\n", 1)[0]
    return re.sub(r"\s+", " ", paragraph.replace("*", "")).strip()


#: A URL the ceiling below admits, for the argument a case is not about.
#: `evaluate` requires a call to supply every argument the entry constrains,
#: so a case aimed at one argument passes a known-admitted value for the
#: other — which is also what makes a refusal attributable to the case.
GOOD_URL: Final[str] = "https://www.sec.gov/evidence/report.pdf"

#: A path the ceiling below admits, on the same terms.
GOOD_PATH: Final[str] = "/evidence/filings/report.txt"


def sec_ceiling() -> CeilingEntry:
    """Return the ceiling AC-0213 refuses against and AC-0218 is admitted by."""
    return declare(
        "fetch_filing",
        {
            "url": (
                "url",
                (
                    SchemeIn(frozenset({"https"})),
                    HostInDomain("sec.gov"),
                    PathWithin("/evidence/"),
                ),
            ),
            "path": ("fs-path", (Within(EVIDENCE_ROOT),)),
        },
    )


def url_call(value: object) -> dict[str, object]:
    """Return a complete call whose `url` is `value`."""
    return {"url": value, "path": GOOD_PATH}


def path_call(value: object) -> dict[str, object]:
    """Return a complete call whose `path` is `value`."""
    return {"url": GOOD_URL, "path": value}


@contextmanager
def _patched(
    url_rules: tuple[CanonicalisationRule[UrlUnderReview], ...],
    fs_rules: tuple[CanonicalisationRule[str], ...],
) -> Iterator[None]:
    original_url = canonicaliser.URL_RULES
    original_fs = canonicaliser.FS_PATH_RULES
    canonicaliser.URL_RULES = url_rules
    canonicaliser.FS_PATH_RULES = fs_rules
    try:
        yield
    finally:
        canonicaliser.URL_RULES = original_url
        canonicaliser.FS_PATH_RULES = original_fs


@contextmanager
def rule_disabled(name: str) -> Iterator[None]:
    """Run the block with one canonicalisation rule removed, and only that one.

    A removal, for every rule. Nothing here substitutes a different step for
    the one it takes out: a mutation that replaces a rule with a miswrite
    measures the miswrite, and AC-0216 asks what happens when the rule is not
    there.
    """
    with _patched(
        tuple(rule for rule in canonicaliser.URL_RULES if rule.name != name),
        tuple(rule for rule in canonicaliser.FS_PATH_RULES if rule.name != name),
    ):
        yield


@contextmanager
def decode_and_dot_segments_transposed() -> Iterator[None]:
    """Run the block with the two ordered rules swapped and every rule present.

    This is the mutation AC-0216 cannot reach: it disables rules and never
    reorders them, so a refactor that keeps the whole rule set and transposes
    these two ships green under that criterion alone.
    """
    names = ("percent-decode-then-refuse-residual", "remove-dot-segments")
    rules = list(canonicaliser.URL_RULES)
    first, second = (next(i for i, rule in enumerate(rules) if rule.name == n) for n in names)
    rules[first], rules[second] = rules[second], rules[first]
    with _patched(tuple(rules), canonicaliser.FS_PATH_RULES):
        yield
