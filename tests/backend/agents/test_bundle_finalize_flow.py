from __future__ import annotations

from agents.middle_agent.bundle_finalize_flow import _is_blocking_failure


def test_parallel_budget_zero_is_soft_failure_for_execution_status() -> None:
    assert _is_blocking_failure({"tool": "document", "reason": "parallel_budget_zero"}) is False


def test_web_fetch_empty_is_soft_failure_for_execution_status() -> None:
    assert _is_blocking_failure({"tool": "fetch_web", "reason": "web_fetch_empty"}) is False


def test_not_allowed_by_plan_still_blocks_execution_status() -> None:
    assert _is_blocking_failure({"tool": "fetch_web", "reason": "not_allowed_by_plan"}) is True


def test_prepare_commit_failed_still_blocks_execution_status() -> None:
    assert _is_blocking_failure({"tool": "v13_prepare_commit", "reason": "prepare/commit failed"}) is True
