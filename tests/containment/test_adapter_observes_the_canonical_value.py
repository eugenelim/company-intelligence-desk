"""AC-0214 — the adapter sees the canonical value, not the original string.

The assertion is at the **adapter**, deliberately. A validator that
canonicalises and an adapter that re-parses the original both pass a
validator-side assertion while the callee fetches the attacker's string, and
that differential is the whole reason r5's third rule exists.

**This does not close the differential, and the plan says so.** No production
adapter consumes the canonical value in this spec's scope — the tool-call path
that will is `walking-skeleton-policy-decision-point`'s — so the consumer here
is a test double. What that establishes is that the fragment *emits* the
canonical value. What it does not establish is that the real consumer declines
to re-parse the original; that half is asserted one spec over.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ced.domain.containment.canonicaliser import CanonicalUrl
from ced.domain.containment.ceiling import Admitted, CeilingEntry, declare, evaluate
from ced.domain.containment.predicates import HostInDomain, PathWithin, SchemeIn

#: Non-canonical in three ways at once: userinfo, a default port, and a pair
#: of dot segments. Each is a difference an adapter re-parsing the original
#: would act on.
_ORIGINAL = "https://reader@www.filings.example:443/evidence/./2024/../report.pdf"
_CANONICAL = "https://www.filings.example/evidence/report.pdf"


def _ceiling() -> CeilingEntry:
    """A ceiling of this module's own, over a documentation domain.

    AC-0214 is about where the assertion sits, not about which ceiling
    decides, so this one is local. The host is a reserved documentation name
    because the original carries userinfo, and a userinfo component against a
    real-looking host reads as an email address to the repository's
    identifier lint.
    """
    return declare(
        "fetch_filing",
        {
            "url": (
                "url",
                (
                    SchemeIn(frozenset({"https"})),
                    HostInDomain("filings.example"),
                    PathWithin("/evidence/"),
                ),
            )
        },
    )


@dataclass
class _FetchingAdapter:
    """A stand-in for the consumer that will eventually fetch the URL.

    It takes a `CanonicalUrl` and not a string, which is the shape the
    fragment hands over. An adapter that cannot be given the original cannot
    re-parse it, so the type is part of the control rather than a convenience.
    """

    fetched: list[str] = field(default_factory=list)

    def fetch(self, url: CanonicalUrl) -> None:
        self.fetched.append(str(url))


def test_the_adapter_receives_the_canonical_value() -> None:
    decision = evaluate(_ceiling(), {"url": _ORIGINAL})
    assert isinstance(decision, Admitted)

    adapter = _FetchingAdapter()
    url = decision.canonical["url"]
    assert isinstance(url, CanonicalUrl)
    adapter.fetch(url)

    assert adapter.fetched == [_CANONICAL]


def test_the_original_string_never_reaches_the_adapter() -> None:
    decision = evaluate(_ceiling(), {"url": _ORIGINAL})
    assert isinstance(decision, Admitted)

    adapter = _FetchingAdapter()
    url = decision.canonical["url"]
    assert isinstance(url, CanonicalUrl)
    adapter.fetch(url)

    assert _ORIGINAL not in adapter.fetched
    assert "reader@" not in adapter.fetched[0]
    assert ":443" not in adapter.fetched[0]


def test_the_admitting_result_carries_no_route_back_to_the_original() -> None:
    """Setup check: the result has no field holding the string it was given."""
    decision = evaluate(_ceiling(), {"url": _ORIGINAL})
    assert isinstance(decision, Admitted)
    assert _ORIGINAL not in repr(decision)
