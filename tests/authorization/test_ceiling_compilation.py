"""The stored ceiling's decode: routed through `declare`, exact, and refusing.

Beyond every criterion, and the reason is the one the plan states: `CeilingEntry`
is a directly constructible frozen dataclass and both ceiling columns are bare
`jsonb` with no CHECK, populated by operator insert. A decoder that built the
dataclass itself, or that dropped an element it did not recognise, would widen
the ceiling with every authorization criterion green.

**Each check asserts the refusal it names, not merely that compilation
refused.** That distinction is load-bearing here. Four of the refusals below are
reachable only through a `url`-typed argument, and the ratified dataset refusal
rejects *every* `url` entry while the bundled snapshot is stale — so a check
asserting only "compilation refused" would be green on an implementation that
never routed a `url` entry through `declare` at all. Those four suppress the
dataset refusal in this process to reach the refusal they are about.

**What these checks do not establish.** The drift claim is only as good as
somebody re-reading the fragment: nothing mechanical notices a refusal added to
`ced.domain.containment.ceiling` after this file was written. And the
no-canonical-form refusal is a union over every `ContainmentUndecidable` the
canonicaliser can raise, so the check on one cause discharges the site rather
than the cause set.

No substrate. Nothing here opens a connection; the decode is a pure function
over a stored mapping.
"""

from __future__ import annotations

from typing import Any

import pytest

from ced.agents.ceilings import (
    PREDICATE_PAYLOADS,
    STALE_PUBLIC_SUFFIX_SNAPSHOT,
    compile_ceiling,
)
from ced.agents.compiler import compile_role
from ced.agents.models import RoleCompileError
from ced.domain.containment.ceiling import PUBLIC_SUFFIX_DATASET_AS_OF
from tests.compiler.role_records import a_planning_role, a_pool, an_integration

#: A date after every suffix delegation the bundled snapshot is missing. Used
#: only to lift the ratified dataset refusal *in this process*, which is how the
#: four `url`-family refusals below are reached at all. The shipped module holds
#: no switch; this patches the fragment's own module-level constant, the same
#: idiom the canonicaliser's rule tuple uses.
A_REFRESHED_DATASET = "2099-01-01"


@pytest.fixture
def a_refreshed_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lift the public-suffix refusal so a `url` entry can reach `declare`."""
    monkeypatch.setattr(
        "ced.domain.containment.ceiling.PUBLIC_SUFFIX_DATASET_AS_OF", A_REFRESHED_DATASET
    )


def a_stored_entry(
    argument: str, domain_type: str, *predicates: dict[str, Any], tool: str = "fetch_filing"
) -> list[dict[str, Any]]:
    """One stored ceiling entry, in the shape an operator inserts."""
    return [
        {
            "integration_name": "filing-archive",
            "integration_version": 1,
            "tool_name": tool,
            "predicates": {
                argument: {"domain_type": domain_type, "predicates": list(predicates)}
            },
        }
    ]


def refusal_for(ceiling: list[dict[str, Any]]) -> str:
    """Compile and return the refusal text, failing if it compiled."""
    with pytest.raises(RoleCompileError) as raised:
        compile_ceiling("role 'analysis' version 1", ceiling)
    return str(raised.value)


# ── The dataset snapshot, and the ratified refusal over it ───────────────────


def test_the_bundled_dataset_is_still_the_stale_snapshot() -> None:
    """Setup check: the refusal below is live, not already lifted.

    If `publicsuffix2` ever ships a newer dataset and the fragment's constant
    moves with it, this reds — and the refusal it guards stops firing, which is
    a change somebody must notice rather than discover.
    """
    assert PUBLIC_SUFFIX_DATASET_AS_OF == STALE_PUBLIC_SUFFIX_SNAPSHOT


def test_a_url_argument_is_refused_while_the_dataset_is_stale() -> None:
    """The ratified refusal, on an otherwise perfectly authorable entry.

    Every other guard this entry could trip is satisfied: it constrains its
    host, names a resolvable scheme, and the domain is not a public suffix. The
    only thing wrong with it is the dataset it would be judged against.
    """
    message = refusal_for(
        a_stored_entry(
            "target",
            "url",
            {"kind": "host_in_domain", "domain": "sec.gov"},
            {"kind": "scheme_in", "schemes": ["https"]},
        )
    )
    assert "public-suffix dataset" in message
    assert STALE_PUBLIC_SUFFIX_SNAPSHOT in message


def test_the_dataset_refusal_does_not_reach_a_non_url_argument() -> None:
    """What the ratified refusal deliberately does not do.

    It is scoped to `url` because no other domain type resolves a host. Stating
    that as a check keeps a later widening from being mistaken for a fix.
    """
    resolver = compile_ceiling(
        "role 'analysis' version 1",
        a_stored_entry("cik", "opaque-string", {"kind": "prefix", "value": "0003"}),
    )
    assert "fetch_filing" in resolver.entries


# ── The refusals `declare` holds and `evaluate` does not repeat ──────────────


def test_a_prefix_on_an_interpreted_type_is_refused() -> None:
    """`declare`'s prefix rule. A prefix corresponds to no containment relation
    in a parsed domain, and `evaluate` does not re-check it."""
    message = refusal_for(
        a_stored_entry("path", "fs-path", {"kind": "prefix", "value": "/srv"})
    )
    assert "string prefix is not expressible" in message


def test_a_predicate_outside_its_types_row_is_refused() -> None:
    """`declare`'s expressibility table. `one_of` ranges over no filesystem
    path, and nothing at evaluation time would notice."""
    message = refusal_for(
        a_stored_entry("path", "fs-path", {"kind": "one_of", "members": ["/srv"]})
    )
    assert "is not expressible on" in message


def test_a_root_with_no_canonical_form_is_refused() -> None:
    """`within("")` — the case a bypassing decoder admits the filesystem with.

    Left un-canonicalised, `admits` compares with `startswith("/")` and every
    absolute path falls inside. `declare` refuses it on the absolute-root check
    *before* canonicalising, which is why the entry never reaches `evaluate` to
    be re-checked.
    """
    message = refusal_for(a_stored_entry("path", "fs-path", {"kind": "within", "root": ""}))
    assert "no canonical form" in message


def test_a_root_that_bounds_nothing_is_refused() -> None:
    """`within(/)` is the whole filesystem: a predicate present and bounding
    nothing. `evaluate` has no counterpart for it."""
    message = refusal_for(a_stored_entry("path", "fs-path", {"kind": "within", "root": "/"}))
    assert "bounds nothing" in message


def test_a_host_in_domain_over_a_public_suffix_is_refused(a_refreshed_dataset: None) -> None:
    """`host_in_domain` over a public suffix silently admits the internet.

    Reachable only through a `url` argument, so the dataset refusal is lifted in
    this process to get here — otherwise this check would be green on an
    implementation that never called `declare` for a `url` entry at all.
    """
    message = refusal_for(
        a_stored_entry(
            "target",
            "url",
            {"kind": "host_in_domain", "domain": "com"},
            {"kind": "scheme_in", "schemes": ["https"]},
        )
    )
    assert "is a public suffix" in message


def test_a_url_with_no_host_predicate_is_refused(a_refreshed_dataset: None) -> None:
    """Every host admitted, including the link-local metadata address."""
    message = refusal_for(
        a_stored_entry(
            "target",
            "url",
            {"kind": "scheme_in", "schemes": ["https"]},
            {"kind": "path_within", "prefix": "/cgi-bin"},
        )
    )
    assert "no host-constraining predicate" in message


def test_a_url_with_no_scheme_predicate_is_refused(a_refreshed_dataset: None) -> None:
    """A scheme that ignores the authority turns the host predicate into a
    constraint on nothing."""
    message = refusal_for(
        a_stored_entry("target", "url", {"kind": "host_eq", "host": "www.sec.gov"})
    )
    assert "no scheme-constraining predicate" in message


def test_a_scheme_outside_the_resolvable_set_is_refused(a_refreshed_dataset: None) -> None:
    """`scheme_in{file}` beside a host predicate: present, and deciding nothing.

    Presence is not enough, which is the difference from the host rule above,
    and this is the case the scheme refusal is recorded as closing.
    """
    message = refusal_for(
        a_stored_entry(
            "target",
            "url",
            {"kind": "host_eq", "host": "sec.gov"},
            {"kind": "scheme_in", "schemes": ["file"]},
        )
    )
    assert "outside" in message and "file" in message


def test_an_argument_carrying_no_predicate_is_refused() -> None:
    """An empty predicate tuple reaches `declare`, which refuses it.

    Recorded as a check because an earlier reading had this contributing
    nothing and denying by lookup miss. It does not: it is a compile-time
    refusal, and the entry never installs.
    """
    message = refusal_for(a_stored_entry("cik", "opaque-string"))
    assert "no predicate is attached" in message


# ── The decode itself: total, exact, and refusing ────────────────────────────


def test_an_unrecognised_predicate_kind_refuses_the_whole_entry() -> None:
    """Beside a perfectly valid conjunct, which is the point.

    `declare` takes already-constructed predicates, so it cannot refuse a
    conjunct it never received: a decoder that dropped the unrecognised element
    would hand it a strictly weaker conjunction, `declare` would accept it
    because every surviving predicate is well-formed, and the ceiling would
    silently widen.
    """
    message = refusal_for(
        a_stored_entry(
            "cik",
            "opaque-string",
            {"kind": "prefix", "value": "0003"},
            {"kind": "regex_match", "pattern": ".*"},
        )
    )
    assert "regex_match" in message
    assert "recognises" in message


def test_a_recognised_kind_omitting_a_required_key_refuses_the_entry() -> None:
    """Absent is as dangerous as unrecognised, and quieter.

    `declare` accepts `Prefix(value="")` and `evaluate` then admits every
    string, so a decoder supplying the constructor's default for the missing
    payload would turn this into an unconditional admit on an argument that
    reads as constrained. Measured against the installed fragment; the
    companion check below holds that measurement.
    """
    message = refusal_for(a_stored_entry("cik", "opaque-string", {"kind": "prefix"}))
    assert "value" in message
    assert "nothing may be supplied that the row does not" in message


def test_an_empty_prefix_would_have_admitted_every_string() -> None:
    """The grounds for the check above, asserted rather than asserted about.

    If the fragment ever stopped admitting on `Prefix(value="")`, the omitted-key
    refusal would still be right but its stated reason would be stale — and a
    reason nobody can check is how the last four review rounds went.
    """
    from ced.domain.containment.ceiling import Admitted, declare, evaluate
    from ced.domain.containment.predicates import Prefix

    entry = declare("t", {"q": ("opaque-string", (Prefix(value=""),))})
    assert isinstance(evaluate(entry, {"q": "anything at all"}), Admitted)


def test_an_unrecognised_payload_key_refuses_the_entry() -> None:
    """A key the row carries that the kind does not name.

    Refused rather than ignored: a row saying something this compiler cannot
    carry is a row whose meaning is not the one that would be enforced.
    """
    message = refusal_for(
        a_stored_entry(
            "cik", "opaque-string", {"kind": "prefix", "value": "0003", "case": "any"}
        )
    )
    assert "case" in message
    assert "does not recognise" in message


def test_an_argument_object_of_the_wrong_shape_refuses_the_entry() -> None:
    """The argument declaration is exact too, not only its elements."""
    ceiling = a_stored_entry("cik", "opaque-string", {"kind": "prefix", "value": "0003"})
    ceiling[0]["predicates"]["cik"].pop("domain_type")
    message = refusal_for(ceiling)
    assert "domain_type" in message


def test_a_float_bound_is_refused_rather_than_converted() -> None:
    """A numeric bound written as a float has no exact decimal value.

    `Decimal(0.1)` is not one tenth, so the ceiling's edge would sit somewhere
    other than where the operator wrote it — a silent difference between the row
    and the constraint, which is the class of defect this module refuses.
    """
    message = refusal_for(
        a_stored_entry("amount", "number", {"kind": "number_range", "low": 0.1, "high": 1})
    )
    assert "no" in message and "exact decimal value" in message


def test_every_recognised_kind_names_a_fragment_constructor() -> None:
    """The decode table's own setup check.

    A row whose constructor no longer exists, or whose payload keys no longer
    match the dataclass, would fail at compile time on a real ceiling and
    nowhere else. This reads the table against the dataclasses themselves.
    """
    for kind, (constructor, payload) in PREDICATE_PAYLOADS.items():
        fields = set(constructor.__dataclass_fields__)
        assert set(payload) == fields, (
            f"{kind} decodes {sorted(payload)} but "
            f"{constructor.__name__} takes {sorted(fields)}"
        )


# ── What an empty encoding does, and what the compiler installs ──────────────


@pytest.mark.parametrize("encoding", [[], {}, None])
def test_a_ceiling_row_with_no_predicate_encoding_installs_no_entry(
    encoding: object,
) -> None:
    """AC-0235's lookup miss, and where it comes from.

    The miss is produced **here**, by installing nothing — not by the fragment.
    An entry naming no arguments is accepted by `declare` and `evaluate` returns
    `Admitted` for a call supplying none, so handing the fragment an empty entry
    would admit rather than contribute nothing.
    """
    ceiling = a_stored_entry("cik", "opaque-string", {"kind": "prefix", "value": "0003"})
    ceiling[0]["predicates"] = encoding

    resolver = compile_ceiling("role 'analysis' version 1", ceiling)

    assert resolver.entries == {}
    assert resolver.entries_admitting("fetch_filing", {"cik": "0003"}) == ()


def test_the_compiler_installs_the_decoded_ceiling() -> None:
    """The wiring: a predicate nothing wires in is a predicate no stack holds.

    Without this, `compile_ceiling` could be correct and unreachable — every
    check in this file green, and the compiled agent still refusing everything
    through the fail-closed default.
    """
    ceiling = a_stored_entry("cik", "opaque-string", {"kind": "prefix", "value": "0003"})
    role = a_planning_role()
    role["ceiling"] = ceiling

    compiled = compile_role(role, [an_integration()], a_pool())

    resolver = compiled.stack.resolver
    assert resolver.entries_admitting("fetch_filing", {"cik": "000320193"}), (
        "the compiled stack does not hold the ceiling the record declared"
    )
    assert resolver.entries_admitting("fetch_filing", {"cik": "999"}) == ()


#: One stored ceiling per refusal this module can produce, so the check below
#: quantifies over the refusals rather than sampling one. Each is a shape an
#: operator could insert today, because both ceiling columns are bare `jsonb`.
MALFORMED_CEILINGS: list[tuple[str, list[dict[str, Any]]]] = [
    ("unrecognised kind", a_stored_entry("cik", "opaque-string", {"kind": "regex_match"})),
    ("absent payload key", a_stored_entry("cik", "opaque-string", {"kind": "prefix"})),
    (
        "unrecognised payload key",
        a_stored_entry("cik", "opaque-string", {"kind": "prefix", "value": "a", "case": "any"}),
    ),
    ("element is not an object", a_stored_entry("cik", "opaque-string", "prefix")),  # type: ignore[arg-type]
    (
        "unknown domain type",
        a_stored_entry("cik", "postcode", {"kind": "prefix", "value": "a"}),
    ),
    ("no predicate at all", a_stored_entry("cik", "opaque-string")),
    (
        "prefix on an interpreted type",
        a_stored_entry("p", "fs-path", {"kind": "prefix", "value": "/"}),
    ),
    ("root bounding nothing", a_stored_entry("p", "fs-path", {"kind": "within", "root": "/"})),
    (
        "root with no canonical form",
        a_stored_entry("p", "fs-path", {"kind": "within", "root": ""}),
    ),
    (
        "url while the dataset is stale",
        a_stored_entry("u", "url", {"kind": "host_eq", "host": "sec.gov"}),
    ),
    (
        "float bound",
        a_stored_entry("n", "number", {"kind": "number_range", "low": 0.5, "high": 1}),
    ),
]


@pytest.mark.parametrize(
    "ceiling", [c for _, c in MALFORMED_CEILINGS], ids=[n for n, _ in MALFORMED_CEILINGS]
)
def test_every_ceiling_refusal_is_one_the_event_log_can_record(
    ceiling: list[dict[str, Any]],
) -> None:
    """The refusal reaches the compiler, and with a type it can file.

    `RoleCompileError` and not the fragment's own refusal type, because
    `append_role_refusal` maps this one to `role.compile.refused` and raises
    `TypeError` on anything it cannot classify — so an unmapped refusal is a
    role that never becomes an agent with the event log silent about why. That
    is `unmapped-refusal-appends-no-event` in `workspace.toml` `[backlog].open`,
    and this check is the evidence that **this task adds no new instance of
    it**: every refusal this module can raise is one the seam maps.

    Quantified over the refusals rather than sampling one, because a single
    case would leave the claim resting on which one somebody picked.
    """
    from ced.agents.compiler import ROLE_REFUSAL_EVENT_TYPES

    role = a_planning_role()
    role["ceiling"] = ceiling

    with pytest.raises(RoleCompileError) as raised:
        compile_role(role, [an_integration()], a_pool())

    assert any(
        isinstance(raised.value, refusal_type) for refusal_type, _ in ROLE_REFUSAL_EVENT_TYPES
    ), "the refusal is of a type `append_role_refusal` cannot file"
