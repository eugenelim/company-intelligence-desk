"""The pool's boot-time configuration check: AC-0265, AC-0270 and the variables.

**Every refusal here is driven through `verify_boot`**, which is the callable
both criteria name. That is possible offline only because the validation runs
before either `psycopg` connection is opened, and this module proves that
rather than assuming it: `no_database` replaces `psycopg.connect` with a
function that fails the test if it is called. Without that fixture these checks
would pass against a running substrate for the wrong reason and red on a
machine with none.

The admitted cases go through `validate_pool_config` instead, and they have to:
`verify_boot` has no return before its two connections, so a configuration it
*accepts* is not observable through it at all.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping

import pytest

from ced.worker import pool

#: An admitted configuration, in `role-configuration-seams` § 5's `limits`
#: shape. Cases below start from this and break exactly one thing.
VALID_LIMITS: dict[str, object] = {
    "per_request_input_tokens_limit": 20_000,
    "input_tokens_limit": 200_000,
    "request_limit": 20,
    "tool_calls_limit": 40,
    "count_tokens_before_request": False,
}
VALID_MODEL_IDS = ["stub:counting"]


def env_with(**overrides: str | None) -> dict[str, str]:
    """The valid environment, with named variables replaced or removed."""
    env = {
        pool.DEFAULT_LIMITS_VAR: json.dumps(VALID_LIMITS),
        pool.ALLOWED_MODEL_IDS_VAR: json.dumps(VALID_MODEL_IDS),
    }
    for name, value in overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return env


def limits_env(limits: Mapping[str, object]) -> dict[str, str]:
    """An environment whose limits object is exactly `limits`."""
    return env_with(**{pool.DEFAULT_LIMITS_VAR: json.dumps(limits)})


@pytest.fixture(autouse=True)
def no_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make reaching for a database a test failure, not a hang or a pass.

    The substrate is often up on a developer machine, so a `verify_boot` that
    validated *after* connecting would still raise and still look green. This
    is what makes "the refusal precedes the connection" the thing asserted.
    """

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("verify_boot opened a connection before validating")

    monkeypatch.setattr(pool.psycopg, "connect", refuse)
    yield


# ── the two variables, named on refusal ─────────────────────────────────────


@pytest.mark.parametrize("name", [pool.DEFAULT_LIMITS_VAR, pool.ALLOWED_MODEL_IDS_VAR])
@pytest.mark.parametrize(
    ("case", "value"),
    [
        ("missing", None),
        ("empty", ""),
        ("unparseable", "{not json"),
        ("wrong JSON type", "7"),
    ],
)
def test_a_missing_or_malformed_variable_fails_boot_naming_it(
    name: str, case: str, value: str | None
) -> None:
    """Required with no in-code default, on a `restart: "no"` fleet.

    A worker that cannot state its spend bound must fail at startup, where the
    operator is looking, rather than at its first claim. `7` is well-formed
    JSON of the wrong type for both variables — an object is wanted for one and
    an array for the other — which is the case a bare `json.loads` admits.
    """
    with pytest.raises(ValueError, match=name):
        pool.verify_boot(env_with(**{name: value}))


@pytest.mark.parametrize(
    ("case", "value"),
    [
        ("empty", ""),
        ("unparseable", "{not json"),
        ("unquoted array", "[stub:counting]"),
        ("wrong JSON type", "7"),
        ("non-string member", '["stub:counting", 7]'),
    ],
)
def test_a_malformed_non_provider_declaration_fails_boot_naming_it(
    case: str, value: str
) -> None:
    """AC-0275's declaration is refused on the same terms as the other two.

    Optional is not lenient: only an **unset** variable declares no id, so a
    present value that cannot be read is a refusal. The unquoted array is the
    hand edit that motivates it — a parser answering `()` on a decode error
    would boot every worker green and surface only as an unexplained compile
    refusal in production, long after the operator stopped looking here.
    """
    env = env_with(**{pool.NON_PROVIDER_MODEL_IDS_VAR: value})
    with pytest.raises(ValueError, match=pool.NON_PROVIDER_MODEL_IDS_VAR):
        pool.verify_boot(env)


def test_an_empty_non_provider_declaration_says_to_unset_it() -> None:
    """The empty case's advice, which is the only thing its branch changes.

    Naming the variable is not enough to pin this: the shared JSON decoder
    already refuses an empty value and already names it, so a check matching
    on the variable alone stays green with the bespoke branch deleted — and
    the operator is then told the variable "is required and is unset", which
    is the opposite instruction for the one pool value that is optional.
    What the branch exists to say is that unsetting it is the fix.
    """
    env = env_with(**{pool.NON_PROVIDER_MODEL_IDS_VAR: ""})

    with pytest.raises(ValueError, match="unset it") as refusal:
        pool.verify_boot(env)

    assert pool.NON_PROVIDER_MODEL_IDS_VAR in str(refusal.value)
    assert "is required" not in str(refusal.value), (
        "the optional variable must not be reported as a missing required one"
    )


def test_an_unset_non_provider_declaration_declares_no_id() -> None:
    """The one way this variable differs from the pool's other two.

    Decided through `validate_pool_config`, because `verify_boot` reaches its
    two connections on a configuration it admits and the `no_database` fixture
    would fire there.
    """
    config = pool.validate_pool_config(env_with())

    assert config.non_provider_model_ids == ()


def test_a_non_string_model_id_fails_boot_naming_the_variable() -> None:
    """An array of the right JSON type can still not be a list of model ids."""
    env = env_with(**{pool.ALLOWED_MODEL_IDS_VAR: json.dumps(["stub:counting", 7])})
    with pytest.raises(ValueError, match=pool.ALLOWED_MODEL_IDS_VAR):
        pool.verify_boot(env)


# ── AC-0265: an object that is neither missing nor malformed ────────────────


@pytest.mark.parametrize("key", pool.DEFAULT_LIMIT_KEYS)
@pytest.mark.parametrize("how", ["omitted", "nulled"])
def test_a_limit_key_omitted_or_nulled_fails_boot_naming_the_key(key: str, how: str) -> None:
    """AC-0265, once per key and both ways of leaving it unset.

    This is a distinct case from the variable-level check above: the object is
    present, parses, and is an object, so that check passes it. On the pinned
    2.45.0 three of these four `UsageLimits` fields default to `None`, which is
    no bound at all, and `request_limit` defaults to 50 — so a pool shipping
    one of them unset is either unlimited on that axis or silently bounded at a
    number nobody deployed. AC-0206 cannot catch it: it only ever compares a
    role against the pool, never the pool against itself.
    `tests/contract/test_usage_limits.py` pins those defaults.
    """
    limits = dict(VALID_LIMITS)
    if how == "omitted":
        del limits[key]
    else:
        limits[key] = None

    with pytest.raises(ValueError, match=key):
        pool.verify_boot(limits_env(limits))


@pytest.mark.parametrize("key", pool.DEFAULT_LIMIT_KEYS)
def test_a_non_integer_limit_fails_boot_naming_the_key(key: str) -> None:
    """All four keys are integers per § 5, and `true` is not one of them.

    `bool` subclasses `int`, so a JSON `true` reaches a naive `isinstance`
    check as the integer 1 — a request limit of one, deployed by nobody.
    """
    with pytest.raises(ValueError, match=key):
        pool.verify_boot(limits_env({**VALID_LIMITS, key: True}))


# ── AC-0270: the pool-owned flag ────────────────────────────────────────────


@pytest.mark.parametrize("value", [True, "false", 0, 1, None])
def test_count_tokens_before_request_other_than_false_fails_boot(value: object) -> None:
    """AC-0270. ADR-0006 § Confirmation assigns this predicate to this spec.

    Only a JSON `false` is admitted. The string `"false"` and the number `0`
    are the near-misses a truthiness test would let through, and letting one
    through breaks every invocation on an IAM shape ADR-0006 records as not
    re-derived.
    """
    limits = {**VALID_LIMITS, pool.COUNT_TOKENS_KEY: value}
    with pytest.raises(ValueError, match=pool.COUNT_TOKENS_KEY):
        pool.verify_boot(limits_env(limits))


def test_an_unrecognised_limits_key_fails_boot_naming_it() -> None:
    """The guard above reads one exact name, so the shape is a closed set.

    A misspelled `count_tokens_before_request` is not the flag, so AC-0270's
    check would never see it and the deployment half of ADR-0006 D1 would go
    unchecked while the object looked deliberate. Refusing the unknown key is
    what makes that guard fail closed.
    """
    limits = {**VALID_LIMITS, "count_tokens_before_requests": True}
    with pytest.raises(ValueError, match="count_tokens_before_requests"):
        pool.verify_boot(limits_env(limits))


# ── the admitted cases, decided against `validate_pool_config` ──────────────


def test_an_admitted_configuration_parses_with_no_connection_attempted() -> None:
    """The returned `PoolConfig` carries the parsed values.

    Decided here rather than through `verify_boot`, which has no return before
    its two connections: the `no_database` fixture would fire on a valid
    configuration, because reaching the database is exactly what `verify_boot`
    then does. That makes this case observable nowhere else.
    """
    config = pool.validate_pool_config(
        {**env_with(), "CED_WORKER_ID": "worker-a", "CED_POOL_CLASS": "fault-injection"}
    )

    assert config.worker_id == "worker-a"
    assert config.pool_class == "fault-injection"
    assert config.allowed_model_ids == ("stub:counting",)
    assert config.default_limits == VALID_LIMITS


def test_an_omitted_count_tokens_key_is_admitted_and_lands_false() -> None:
    """AC-0270's third case: omission is already the state ADR-0006 D1 wants.

    2.45.0 defaults `UsageLimits.count_tokens_before_request` to `False`, so an
    absent key needs no refusal. It is normalized to present-and-false rather
    than dropped, so the compiler reads one shape whether or not the operator
    wrote the key out.
    """
    limits = {k: v for k, v in VALID_LIMITS.items() if k != pool.COUNT_TOKENS_KEY}

    config = pool.validate_pool_config(limits_env(limits))

    assert config.default_limits[pool.COUNT_TOKENS_KEY] is False


def test_an_empty_allowed_model_set_is_admitted() -> None:
    """A well-formed array with nothing in it is a deployment, not a defect.

    It compiles no role at all — AC-0251 refuses every model id against it —
    and that refusal is the compiler's to make with the role in hand, which is
    a better error than one naming no role at boot. Recorded as a decision
    because refusing here was the alternative and neither criterion states it.
    """
    config = pool.validate_pool_config(env_with(**{pool.ALLOWED_MODEL_IDS_VAR: "[]"}))

    assert config.allowed_model_ids == ()
