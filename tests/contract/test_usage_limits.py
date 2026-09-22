"""§ Grounding probe rows 2 and 13 — the spend and token ceilings DR6 reads.

`UsageLimits` is a dataclass, so field presence is read off its fields rather
than off `hasattr`, which a property or a `__getattr__` would also satisfy.
The per-request bound is additionally asserted by behaviour, because its whole
value is being *not* the cumulative one.
"""

from __future__ import annotations

import dataclasses

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import RunUsage, UsageLimits

#: The declared fields, by name, of the pinned release.
FIELDS = {field.name: field for field in dataclasses.fields(UsageLimits)}


def test_usage_limits_declares_the_four_ceilings_dr6_reads() -> None:
    """Row 2, plus the defaults each ships with — an unset ceiling is not a ceiling.

    Three of the four default to no bound at all, which is why AC-0265 makes a
    pool that omits a key a boot failure. `request_limit` is the exception: it
    ships at 50, so a role that omits it is bounded, not unlimited.
    """
    required = {
        "cost_limit",
        "count_tokens_before_request",
        "request_limit",
        "tool_calls_limit",
    }
    assert required <= set(FIELDS)
    assert FIELDS["count_tokens_before_request"].default is False
    assert FIELDS["request_limit"].default == 50
    assert FIELDS["cost_limit"].default is None
    assert FIELDS["tool_calls_limit"].default is None


def test_the_request_limit_is_enforced_before_a_request() -> None:
    """Row 2, by behaviour: a declared field the framework never reads is not a ceiling."""
    limits = UsageLimits(request_limit=1)
    limits.check_before_request(RunUsage(requests=0))
    with pytest.raises(UsageLimitExceeded):
        limits.check_before_request(RunUsage(requests=1))


def test_the_tool_call_limit_is_enforced_before_a_tool_call() -> None:
    """Row 2, by behaviour, on the other ceiling this spec's successor narrows."""
    limits = UsageLimits(tool_calls_limit=2)
    limits.check_before_tool_call(RunUsage(tool_calls=2))
    with pytest.raises(UsageLimitExceeded):
        limits.check_before_tool_call(RunUsage(tool_calls=3))


def test_the_per_request_input_bound_is_declared_and_distinct_from_the_cumulative_one() -> None:
    """Row 13. AC-0246 reads the per-request bound; the two names differ by one word.

    The distinction is asserted both ways round. A per-request limit must not
    fire on cumulative usage, and a cumulative limit must not be satisfied by a
    single request that fits under it.
    """
    assert "per_request_input_tokens_limit" in FIELDS
    assert "input_tokens_limit" in FIELDS
    assert FIELDS["per_request_input_tokens_limit"].default is None

    per_request = UsageLimits(per_request_input_tokens_limit=10)
    per_request.check_per_request_input_tokens(10)
    with pytest.raises(UsageLimitExceeded, match="per_request_input_tokens_limit"):
        per_request.check_per_request_input_tokens(11)

    # Cumulative usage well past the per-request bound does not trip it: the
    # per-request field bounds one request, so it is not checked against the run.
    per_request.check_tokens(RunUsage(input_tokens=1_000))

    cumulative = UsageLimits(input_tokens_limit=10)
    cumulative.check_per_request_input_tokens(1_000)
    with pytest.raises(UsageLimitExceeded, match="input_tokens_limit"):
        cumulative.check_tokens(RunUsage(input_tokens=11))
