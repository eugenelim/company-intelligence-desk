"""AC-0302, AC-0330, and the prerelease check.

Mutation-proof discipline applied here:
- test_the_gated_tool_is_offered_only_when_a_check_failed covers the offered-list
  pure function. Mutating offered_approval_gated_tools to always return [] fails
  the non-empty assertion; mutating it to always return [...] fails the empty one.
- test_check_prerelease_returns_false_for_unflagged_role pins check_prerelease_failed
  at the function boundary the executor calls. A mutant that returns True for every
  role fails this case, catching the scenario where the gate becomes unconditional.
- test_check_prerelease_raises_on_malformed_model_settings pins the fail-closed
  direction for Entry 18 (adjudication): a non-mapping model_settings must raise,
  not silently disable the gate.
"""

import pytest


# AC-0302 — pure offered-list function
def test_the_gated_tool_is_offered_only_when_a_check_failed() -> None:
    """Exclusion paired with its positive case, so returning [] cannot pass."""
    from ced.worker.executor import offered_approval_gated_tools

    assert offered_approval_gated_tools(prerelease_failed=False) == []
    assert offered_approval_gated_tools(prerelease_failed=True) != []


# AC-0302 — executor-level gate (mutation-proof for check_prerelease_failed)
def test_check_prerelease_returns_false_for_unflagged_role() -> None:
    """A role without needs_approval does not trigger the gate.

    This pins check_prerelease_failed — the function the executor calls before
    offered_approval_gated_tools. A mutant that returns True for every role
    fails here, closing the gap where the gate becomes unconditional.
    """
    from ced.worker.prerelease import check_prerelease_failed

    assert check_prerelease_failed({}) is False
    assert check_prerelease_failed({"model_settings": None}) is False
    assert check_prerelease_failed({"model_settings": {"needs_approval": False}}) is False


def test_check_prerelease_returns_true_for_flagged_role() -> None:
    """A role with needs_approval=True triggers the gate."""
    from ced.worker.prerelease import check_prerelease_failed

    assert check_prerelease_failed({"model_settings": {"needs_approval": True}}) is True


def test_check_prerelease_raises_on_malformed_model_settings() -> None:
    """A non-mapping model_settings is refused, not silently treated as absent (Entry 18)."""
    from ced.worker.prerelease import check_prerelease_failed

    with pytest.raises(ValueError, match="not a mapping"):
        check_prerelease_failed({"model_settings": "string-not-a-mapping"})


def test_check_prerelease_raises_on_non_bool_needs_approval() -> None:
    """A non-boolean needs_approval is refused (Entry 18 fail-closed)."""
    from ced.worker.prerelease import check_prerelease_failed

    with pytest.raises(ValueError, match="must be a boolean"):
        check_prerelease_failed({"model_settings": {"needs_approval": "yes"}})


@pytest.mark.substrate
# AC-0330
def test_a_resume_with_no_committed_decision_refuses_to_run(require_substrate: None) -> None:
    """Absent decision for this cycle is a refusal, not an approval."""
    from ced.worker.persistence import approval_results_for_cycle

    with pytest.raises(LookupError):
        approval_results_for_cycle(
            step_id="11111111-2222-3333-4444-5555aaaabbbb", cycle=1, pending_call_ids=["c1"]
        )


def test_cycle_zero_is_refused_without_database() -> None:
    """cycle < 1 raises LookupError before any database call (AC-0330 guard).

    Differing outcome from the substrate case: cycle=0 is refused immediately
    with a message naming the cycle, not as 'no committed decision'.
    """
    from ced.worker.persistence import approval_results_for_cycle

    with pytest.raises(LookupError, match="below 1"):
        approval_results_for_cycle(
            step_id="11111111-2222-3333-4444-5555aaaabbbb", cycle=0, pending_call_ids=["c1"]
        )
