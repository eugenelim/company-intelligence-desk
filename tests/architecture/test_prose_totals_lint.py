"""The prose-totals lint catches a drifting total and only that.

`tools/lint-prose-totals.py` exists because six review rounds on
`walking-skeleton-run-state` found the same defect and the fifth *introduced*
one while repairing another: a sentence opens with a count of items enumerated
elsewhere in the file, a later edit grows the list, and nothing reds.

Every case below is taken from the real text that drifted or from the real text
that did not, because a rule calibrated on invented examples would have refused
twenty sound sentences in `docs/architecture/README.md`. The negative half is
therefore load-bearing: a lint that refuses "written with its event in one
transaction" is a lint someone switches off, and then the positive half
protects nothing.

The script is run as a subprocess rather than imported, so what the tests pin
is the gate — exit code and message — not a regex that a broken file walk would
leave unreached.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT = REPO_ROOT / "tools" / "lint-prose-totals.py"

START = "<!-- prose-totals:start -->"
END = "<!-- prose-totals:end -->"


def run(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    """Run the real lint over ``body`` written to a throwaway file."""
    target = tmp_path / "doc.md"
    target.write_text(body, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(LINT), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )


def guarded(*lines: str) -> str:
    return "\n".join((START, *lines, END)) + "\n"


# ── Refused: the three totals that actually shipped and drifted ──────────────

#: Each of these is verbatim from `docs/architecture/README.md` at the commit
#: that carried the defect, trimmed to the sentence that drifted.
DRIFTED = [
    pytest.param(
        "**Which entries were contracted.** Ten were enumerated in\nAC-0329 before the build.",
        "Ten",
        id="total-after-a-stop-inside-bold",
    ),
    pytest.param(
        "Six — marked **(discovered)** below — were found during T2 and T3.",
        "Six",
        id="total-at-line-start-over-a-marker",
    ),
    pytest.param(
        "- **Every row of r8 § 3's table.** Two rows are\n"
        "  committed under a source state r8 does not write.",
        "Two",
        id="total-opening-a-sentence-inside-a-bullet",
    ),
    pytest.param(
        "- **(discovered) Five failure paths leave a run reported `running`.**",
        "Five",
        id="total-behind-a-provenance-marker",
    ),
]


@pytest.mark.parametrize("body,word", DRIFTED)
def test_a_sentence_initial_total_is_refused(tmp_path: Path, body: str, word: str) -> None:
    result = run(tmp_path, guarded(body))
    assert result.returncode == 1, result.stdout
    assert word in result.stdout


# ── Admitted: the cardinals in the same section that quantify nothing listed ──

#: Verbatim from the same section. Each names its own subject in the same
#: sentence, or is a value some other gate reads, so none can drift as a list
#: grows. The lint must leave all of them alone.
SOUND = [
    pytest.param(
        "each written with its event in one transaction.",
        id="one-transaction",
    ),
    pytest.param(
        "the tree collapses r8's two hops into one.",
        id="two-hops-into-one",
    ),
    pytest.param(
        "At the default a producible run emits roughly four events\n"
        "against a ceiling of 200 000.",
        id="a-measured-quantity",
    ),
    pytest.param(
        "The ceiling's finite default is unsourced, as is the cycle cap's three.",
        id="a-configured-value",
    ),
    pytest.param(
        "They need both the unreachable source state and two more event types.",
        id="mid-sentence-cardinal",
    ),
]


@pytest.mark.parametrize("body", SOUND)
def test_a_cardinal_that_counts_no_list_is_admitted(tmp_path: Path, body: str) -> None:
    result = run(tmp_path, guarded(body))
    assert result.returncode == 0, result.stdout


# ── Each predicate is load-bearing ───────────────────────────────────────────


def test_the_guard_bounds_the_rule(tmp_path: Path) -> None:
    """Outside a guarded region the same sentence is admitted.

    Without this the lint would refuse sentence-initial cardinals across every
    markdown file in the repository, which is a different and much larger rule
    than the one adopted.
    """
    unguarded = "Ten were enumerated in AC-0329 before the build.\n"
    assert run(tmp_path, unguarded).returncode == 0
    assert run(tmp_path, guarded(unguarded.strip())).returncode == 1


def test_a_wrapped_sentence_is_not_a_sentence_start(tmp_path: Path) -> None:
    """A cardinal opening a *line* mid-sentence is admitted; opening a sentence is not.

    Both bodies are verbatim from `docs/architecture/README.md`, which
    hard-wraps its prose. Without this distinction the rule refused "...owes
    the CHECK and enum widening as well as the\\ntwo safety constraints both
    tables state", which counts nothing enumerable — and a rule that refuses
    sound prose is a rule that gets waived line by line until it gates nothing.
    """
    wrapped = guarded(
        "The spec that first wires the input tool owes the CHECK and enum",
        "widening as well as the",
        "two safety constraints both tables state.",
    )
    assert run(tmp_path, wrapped).returncode == 0, run(tmp_path, wrapped).stdout

    starts_sentence = guarded(
        "The spec that first wires the input tool owes the CHECK and enum.",
        "Two safety constraints both tables state are also owed.",
    )
    result = run(tmp_path, starts_sentence)
    assert result.returncode == 1, result.stdout
    assert "Two" in result.stdout


#: Every spelling of the provenance marker that appears in, or could plausibly
#: be written into, the guarded residual lists. The first is the one
#: `docs/architecture/README.md` actually uses, and it escaped the first
#: version of `_LEAD` — the pattern wanted the closing `**` where the prose has
#: a space, so a total behind it passed inside the live region.
MARKER_SPELLINGS = [
    pytest.param("- **(discovered)** Two rows are committed.", "Two", id="marker-bolded"),
    pytest.param("- (discovered) Three rows are committed.", "Three", id="marker-bare"),
    pytest.param(
        "- **(discovered) Four rows are committed.**", "Four", id="marker-inside-bold"
    ),
    pytest.param("- **Five rows are committed.**", "Five", id="no-marker-bolded"),
]


@pytest.mark.parametrize("body,word", MARKER_SPELLINGS)
def test_every_marker_spelling_still_exposes_the_cardinal(
    tmp_path: Path, body: str, word: str
) -> None:
    result = run(tmp_path, guarded(body))
    assert result.returncode == 1, result.stdout
    assert word in result.stdout


def test_a_bullet_whose_lead_is_prose_is_not_a_total(tmp_path: Path) -> None:
    """The permissive lead must not swallow words on its way to a cardinal.

    `- **Every row of r8 § 3's table.** ...` opens with emphasis and a word, so
    nothing sentence-initial follows the marker run; only the real sentence
    start after the stop should be considered.
    """
    body = guarded("- **Every row of r8 § 3's table.** It lists two hops and one state.")
    assert run(tmp_path, body).returncode == 0


def test_a_colon_lead_in_opens_a_sentence(tmp_path: Path) -> None:
    """A colon ends the lead-in, so the total under it is still a total.

    `docs/specs/walking-skeleton-run-state/spec.md` already leads into its
    residual list with a colon. Without this the next line reads as a wrapped
    continuation and its total goes unrefused — the hole that shipped in the
    first version of this gate.
    """
    body = guarded(
        "What the state machine does not commit:",
        "Two rows are committed under a source state r8 does not write.",
    )
    result = run(tmp_path, body)
    assert result.returncode == 1, result.stdout
    assert "Two" in result.stdout


def test_a_non_waiver_trailing_comment_still_ends_a_sentence(tmp_path: Path) -> None:
    """Separates the trailing-comment strip from the waiver branch.

    Both predicates used to red only the waiver test, so one test stood for
    two guards and neither was independently proved. Here the comment is *not*
    a waiver: the line it sits on ends a sentence, so the cardinal below opens
    one and must be refused. Drop the strip and this line reads as a wrap.
    """
    body = guarded(
        "The residual list is rewritten from the tree. <!-- see ADR-0009 -->",
        "Six were found during the build.",
    )
    result = run(tmp_path, body)
    assert result.returncode == 1, result.stdout
    assert "Six" in result.stdout


def test_an_inline_waiver_admits_one_line_and_not_the_next(tmp_path: Path) -> None:
    """The waiver is per line, so it cannot silence a region."""
    body = guarded(
        "Ten were enumerated in AC-0329. <!-- prose-totals: allow -->",
        "Six — marked **(discovered)** below — were found during T2.",
    )
    result = run(tmp_path, body)
    assert result.returncode == 1, result.stdout
    assert "Six" in result.stdout
    assert "Ten" not in result.stdout


def test_an_unclosed_guard_is_refused(tmp_path: Path) -> None:
    """A guard that never closes would silently extend to end of file."""
    result = run(tmp_path, f"{START}\nSome prose.\n")
    assert result.returncode == 1
    assert "never closed" in result.stdout


def test_a_guard_closed_but_never_opened_is_refused(tmp_path: Path) -> None:
    result = run(tmp_path, f"Some prose.\n{END}\n")
    assert result.returncode == 1
    assert "never opened" in result.stdout


def test_a_missing_file_exits_two(tmp_path: Path) -> None:
    """A typo in the gate's argument list must not read as a pass."""
    result = subprocess.run(
        [sys.executable, str(LINT), str(tmp_path / "absent.md")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2


# ── The gate is actually wired to the files it was adopted for ───────────────


def test_the_guarded_regions_exist_and_are_clean(tmp_path: Path) -> None:
    """The rule protects nothing if no file opts in.

    This is the check that would have caught the sixth round's blocker, so it
    asserts both halves: the guard is present in the two artifacts the owner
    adopted it for, and the real files pass.
    """
    readme = REPO_ROOT / "docs" / "architecture" / "README.md"
    spec = REPO_ROOT / "docs" / "specs" / "walking-skeleton-run-state" / "spec.md"
    for path in (readme, spec):
        assert START in path.read_text(encoding="utf-8"), f"{path} is not guarded"

    result = subprocess.run(
        [sys.executable, str(LINT), str(readme), str(spec)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
