#!/usr/bin/env python3
"""Refuse a prose total over a list the same document enumerates.

Six review rounds on `walking-skeleton-run-state` found the same defect: a
sentence opens with a count of items that live somewhere else in the file, a
later edit grows the list, and the count goes stale with nothing to catch it.
The last occurrence was introduced by the commit that removed the one before
it, in a region whose own text claimed the class had been swept.

The rule this enforces is narrow on purpose. Inside a guarded region, a
**sentence-initial cardinal** is refused -- "Ten were enumerated in AC-0329",
"Six -- marked (discovered) below", "Two rows are committed under a source
state r8 does not write". A cardinal anywhere else in the sentence is not:
"written with its event in one transaction", "collapses r8's two hops into
one", "emits roughly four events", "the cycle cap's three". Those quantify a
thing the sentence itself names or a value a gate elsewhere reads, and none of
them drifts when a list grows.

Guard a region with a pair of HTML comments, which render as nothing:

    <!-- prose-totals:start -->
    ...prose whose totals would drift...
    <!-- prose-totals:end -->

Waive one line, when the cardinal genuinely counts nothing enumerable, by
ending it with `<!-- prose-totals: allow -->` and saying why in the text.

**What this does not catch, stated so nobody reads the gate as wider than it
is.** Only spelled cardinals `one` through `twenty` are matched, so a digit
(`10 were enumerated`) passes. Only a bare cardinal is matched, so a determiner
or a prepositional lead-in in front of it passes (`All ten were enumerated`,
`Of these, six are marked`). Only a *sentence-initial* position is matched, so
a cross-reference total mid-sentence passes (`the five paths above`) -- the
form that has actually shipped here, repeatedly, and the reason the guarded
regions still need reading. Table cells are not parsed. Widen the rule before relying
on it for any of these.

With no arguments this walks `docs/**/*.md` only, which is where the guarded
regions live. A guard placed in any other file -- AGENTS.md, a root README, a
skill -- is not read unless that path is passed explicitly, and an unclosed
guard there is not reported either.

Exit 0 when clean, 1 on any refusal or malformed guard, 2 on a missing file.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CARDINALS = (
    "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    "fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty"
)

START = "<!-- prose-totals:start -->"
END = "<!-- prose-totals:end -->"
ALLOW = "<!-- prose-totals: allow -->"

#: What may sit between a sentence boundary and the cardinal: markdown emphasis,
#: a list bullet, and the `(discovered)` provenance marker the residual lists use.
_LEAD = r"(?:[-*+]\s+)?(?:\*{1,2}|_{1,2})?(?:\((?:discovered)\)\s*)?(?:\*{1,2})?"

#: A cardinal opening a line, or opening a sentence after terminal punctuation.
_AT_LINE_START = re.compile(rf"^\s*{_LEAD}({CARDINALS})\b", re.IGNORECASE)
#: The terminal stop is often inside emphasis -- `**...table.** Two rows` -- so
#: the closing marker may sit between the stop and the space.
_AFTER_STOP = re.compile(
    rf"[.!?](?:\*{{1,2}}|_{{1,2}})?\s+{_LEAD}({CARDINALS})\b", re.IGNORECASE
)


#: A line that may begin a sentence: a bullet, or anything following a blank
#: line or a line that ended one. Prose here is hard-wrapped, so a cardinal at
#: the start of a *line* is usually mid-sentence -- "...as well as the\ntwo
#: safety constraints both tables state" is not a total, and refusing it would
#: teach the reader to waive the rule rather than obey it.
_IS_BULLET = re.compile(r"^\s*[-*+]\s")
#: A colon counts: this prose leads into an enumeration with one -- "What the
#: state machine does not commit:" -- and a total on the next line is exactly
#: the form the rule exists for. Without it, such a line reads as a wrap.
_ENDS_SENTENCE = re.compile(r"[.!?:](?:\*{1,2}|_{1,2}|[)\"'’”])*\s*$")

#: A trailing HTML comment -- a waiver, or any other editorial note -- is not
#: part of the sentence. Without stripping it, the line after a waived line
#: reads as a wrap continuation and its own total goes unchecked.
_TRAILING_COMMENT = re.compile(r"<!--.*?-->\s*$")


def _offenders(line: str, previous: str | None) -> list[str]:
    """Return every sentence-initial cardinal in ``line``.

    ``previous`` is the preceding line of the same guarded region, or ``None``
    at its start; it decides whether a line-initial cardinal opens a sentence
    or merely continues a wrapped one.
    """
    prior = _TRAILING_COMMENT.sub("", previous) if previous is not None else None
    opens_line = (
        _IS_BULLET.match(line)
        or prior is None
        or not prior.strip()
        or _ENDS_SENTENCE.search(prior)
    )
    found = []
    if opens_line and (match := _AT_LINE_START.match(line)):
        found.append(match.group(1))
    found += [m.group(1) for m in _AFTER_STOP.finditer(line)]
    return found


def check(path: Path) -> list[str]:
    """Return one message per refusal in ``path``; empty when clean."""
    lines = path.read_text(encoding="utf-8").splitlines()
    problems: list[str] = []
    depth = 0
    opened_at = 0
    previous: str | None = None

    for number, line in enumerate(lines, start=1):
        if START in line:
            if depth:
                problems.append(
                    f"{path}:{number}: guard opened while one from line "
                    f"{opened_at} is still open"
                )
            depth, opened_at, previous = 1, number, None
            continue
        if END in line:
            if not depth:
                problems.append(f"{path}:{number}: guard closed but never opened")
            depth = 0
            continue
        if not depth:
            continue
        if ALLOW in line:
            previous = line
            continue
        offenders = _offenders(line, previous)
        previous = line
        for word in offenders:
            problems.append(
                f"{path}:{number}: sentence-initial cardinal {word!r} in a "
                f"guarded region -- a total here drifts when the list it counts "
                f"grows. Name the items, or point at what enumerates them."
            )

    if depth:
        problems.append(f"{path}:{opened_at}: guard opened and never closed")
    return problems


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv[1:]]
    if not paths:
        paths = sorted(Path("docs").rglob("*.md"))

    problems: list[str] = []
    for path in paths:
        if not path.is_file():
            print(f"lint-prose-totals: no such file: {path}", file=sys.stderr)
            return 2
        problems.extend(check(path))

    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} refusal(s). See {Path(__file__).name} for the rule.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
