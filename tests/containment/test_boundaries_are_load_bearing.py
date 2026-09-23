"""The boundary checks in the three containment relations, mutation-proved.

`_in_domain`, `_within_path` and `Within`'s prefix test each carry a
label-or-segment boundary — `host == domain or host.endswith("." + domain)`
rather than `host.endswith(domain)`, and the separator-terminated prefix
rather than a bare one. Delete any of the three and the fragment admits a
sibling name: `attackersec.gov` under a ceiling of `sec.gov`,
`/evidence-secret/x` under one of `/evidence/`.

**Every other case in this suite stays green when they are deleted.** That
was the state this module was written to fix: the three comparisons that
decide containment had no input on either side of a boundary, so the checks
that make them containment rather than substring matching were unpinned.
They are the same "passes a string check, means something else to the
callee" shape the whole spec exists to refuse, one level in from the
canonicaliser.
"""

from __future__ import annotations

import pytest

from ced.domain.containment.ceiling import Admitted, Denied, declare, evaluate
from ced.domain.containment.predicates import (
    HostEq,
    HostInDomain,
    PathWithin,
    SchemeIn,
    Within,
    admits,
    contains,
)
from tests.containment.fixture import GOOD_PATH, GOOD_URL, path_call, sec_ceiling, url_call

#: Values whose only difference from an admitted one is the boundary
#: character: a host that ends with the domain without a label break, and a
#: path that starts with the prefix without a segment break.
_SIBLING_URLS: tuple[str, ...] = (
    "https://attackersec.gov/evidence/x",
    "https://www.sec.govmore/evidence/x",
    "https://www.sec.gov/evidence-secret/x",
    "https://www.sec.gov/evidencex",
)

_SIBLING_PATHS: tuple[str, ...] = (
    "/evidence-secret/passwd",
    "/evidencex",
    "/evidence.bak/passwd",
)


@pytest.mark.parametrize("value", _SIBLING_URLS)
def test_a_sibling_host_or_path_is_denied(value: str) -> None:
    assert isinstance(evaluate(sec_ceiling(), url_call(value)), Denied)


@pytest.mark.parametrize("value", _SIBLING_PATHS)
def test_a_sibling_fs_path_is_denied(value: str) -> None:
    assert isinstance(evaluate(sec_ceiling(), path_call(value)), Denied)


def test_the_admitted_side_of_each_boundary_still_is() -> None:
    """The other half. A relation that refuses everything passes the above."""
    assert isinstance(evaluate(sec_ceiling(), url_call(GOOD_URL)), Admitted)
    assert isinstance(evaluate(sec_ceiling(), path_call(GOOD_PATH)), Admitted)
    assert isinstance(
        evaluate(sec_ceiling(), url_call("https://sec.gov/evidence/x")), Admitted
    ), "the apex of the domain is inside it, not merely its subdomains"
    assert isinstance(evaluate(sec_ceiling(), path_call("/evidence")), Admitted), (
        "the root itself is within itself"
    )


def test_host_eq_does_not_match_a_sibling() -> None:
    entry = declare(
        "fetch",
        {"url": ("url", (SchemeIn(frozenset({"https"})), HostEq("www.sec.gov")))},
    )
    assert isinstance(evaluate(entry, {"url": "https://www.sec.gov/x"}), Admitted)
    assert isinstance(evaluate(entry, {"url": "https://attackerwww.sec.gov/x"}), Denied)
    assert isinstance(
        evaluate(entry, {"url": "https://www.sec.gov.attacker.example/x"}), Denied
    )


def test_the_containment_relation_respects_the_same_boundaries() -> None:
    """`contains` decides `ceiling ⊆ ceiling`, and needs the boundary too.

    The property test's oracle and `contains` share `_in_domain` and
    `_within_path`, so a boundary deleted from either helper moves both
    sides together and the property stays green. These are the direct
    fixtures that do not.
    """
    assert contains(HostInDomain("sec.gov"), HostInDomain("www.sec.gov"))
    assert not contains(HostInDomain("sec.gov"), HostInDomain("attackersec.gov"))
    assert contains(PathWithin("/evidence/"), PathWithin("/evidence/2024/"))
    assert not contains(PathWithin("/evidence/"), PathWithin("/evidence-secret/"))
    assert contains(Within("/evidence"), Within("/evidence/filings"))
    assert not contains(Within("/evidence"), Within("/evidence-secret"))


def test_admits_respects_the_same_boundaries_directly() -> None:
    """The helper under `admits`, exercised without going through a ceiling."""
    assert not admits(Within("/evidence"), "/evidence-secret/passwd")
    assert admits(Within("/evidence"), "/evidence/passwd")
    assert admits(Within("/evidence"), "/evidence")
