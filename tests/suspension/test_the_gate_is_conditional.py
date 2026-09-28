import pytest


# STUB: AC-0302
def test_the_gated_tool_is_offered_only_when_a_check_failed() -> None:
    """Exclusion paired with its positive case, so returning [] cannot pass."""
    from ced.worker.executor import offered_approval_gated_tools

    assert offered_approval_gated_tools(prerelease_failed=False) == []
    assert offered_approval_gated_tools(prerelease_failed=True) != []


@pytest.mark.substrate
# STUB: AC-0330
def test_a_resume_with_no_committed_decision_refuses_to_run(require_substrate: None) -> None:
    """Absent decision for this cycle is a refusal, not an approval."""
    from ced.worker.persistence import approval_results_for_cycle

    with pytest.raises(LookupError):
        approval_results_for_cycle(
            step_id="11111111-2222-3333-4444-5555aaaabbbb", cycle=1, pending_call_ids=["c1"]
        )
