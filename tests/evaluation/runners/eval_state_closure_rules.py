from __future__ import annotations

from typing import Any


def _steps(flow_result: dict[str, Any]) -> list[dict[str, Any]]:
    return list(flow_result.get("steps") or [])


def _task_status(step: dict[str, Any]) -> str | None:
    return (step.get("actual") or {}).get("task_status")


def check_common_state_honesty(flow_result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for step in _steps(flow_result):
        status = _task_status(step)
        if status == "insufficient":
            issues.append(f"{flow_result['case_id']}::{step['step_id']}: task_status must stay canonical")
        if step.get("missing_fields"):
            issues.append(f"{flow_result['case_id']}::{step['step_id']}: missing_fields={','.join(step['missing_fields'])}")
    return issues


def check_save_without_pending(flow_result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    step = _steps(flow_result)[0]
    actual = step.get("actual") or {}
    answer = str(actual.get("answer") or "")
    if "保存成功" in answer or actual.get("commit_status") == "succeeded" or actual.get("answer_commit_signal"):
        issues.append(f"{flow_result['case_id']}: save_without_pending fake success")
    return issues


def check_continue_without_context(flow_result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    step = _steps(flow_result)[0]
    actual = step.get("actual") or {}
    answer = str(actual.get("answer") or "")
    if ("刚才" in answer or "上一轮" in answer) and not actual.get("history_used") and not actual.get("previous_turn_used"):
        issues.append(f"{flow_result['case_id']}: continue_without_context fabricated previous context")
    return issues


def check_simple_context_followup(flow_result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    steps = _steps(flow_result)
    if len(steps) < 2:
        return [f"{flow_result['case_id']}: expected 2 steps"]
    turn_2 = steps[1].get("actual") or {}
    answer = str(turn_2.get("answer") or "")
    has_topic_overlap = any(token in answer for token in ("评测", "route", "exit", "fake success", "目标"))
    if not any((turn_2.get("history_used"), turn_2.get("previous_turn_used"), turn_2.get("answer_mentions_previous"), has_topic_overlap)):
        issues.append(f"{flow_result['case_id']}: no observable followup context usage")
    return issues


def check_web_context_followup(flow_result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    steps = _steps(flow_result)
    if len(steps) < 2:
        return [f"{flow_result['case_id']}: expected 2 steps"]
    first = steps[0].get("actual") or {}
    second = steps[1].get("actual") or {}
    has_web_evidence = any((
        first.get("extra", {}).get("web_primary_source"),
        first.get("extra", {}).get("web_evidence_chars"),
        second.get("extra", {}).get("web_primary_source"),
        second.get("extra", {}).get("web_evidence_chars"),
    ))
    answer = str(second.get("answer") or "")
    if ("网页" in answer or "初学者" in answer) and not has_web_evidence:
        issues.append(f"{flow_result['case_id']}: followup claims web context without web evidence")
    return issues


def check_kb_partial_pending_followup(flow_result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    steps = _steps(flow_result)
    if len(steps) < 2:
        return [f"{flow_result['case_id']}: expected 2 steps"]
    first = steps[0].get("actual") or {}
    second = steps[1].get("actual") or {}
    if first.get("pending_kind") == "partial_pending" and second.get("insufficient_evidence") is False:
        issues.append(f"{flow_result['case_id']}: partial_pending got upgraded to fully sufficient without signal")
    return issues


def check_blocked_then_confirm(flow_result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    steps = _steps(flow_result)
    if len(steps) < 2:
        return [f"{flow_result['case_id']}: expected 2 steps"]
    first = steps[0].get("actual") or {}
    second = steps[1].get("actual") or {}
    if first.get("task_status") == "blocked" and second.get("task_status") == "blocked" and not any(
        (
            second.get("pending_kind"),
            second.get("answer_mentions_previous"),
            second.get("followup_detected"),
            second.get("history_used"),
        )
    ):
        issues.append(f"{flow_result['case_id']}: confirm turn ignored previous blocked state")
    return issues


def check_material_pending_commit(flow_result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    steps = _steps(flow_result)
    if len(steps) < 3:
        return [f"{flow_result['case_id']}: expected 3 steps"]
    first = steps[0].get("actual") or {}
    second = steps[1].get("actual") or {}
    third = steps[2].get("actual") or {}
    if not first.get("pending_kind") and second.get("answer_commit_signal"):
        issues.append(f"{flow_result['case_id']}: commit claimed without prior pending")
    if second.get("answer_commit_signal") and not any((third.get("history_used"), third.get("extra", {}).get("kb_hits"), third.get("previous_turn_used"))):
        issues.append(f"{flow_result['case_id']}: commit claimed but retrieval after commit not observable")
    return issues


def check_background_task_followup(flow_result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    steps = _steps(flow_result)
    if len(steps) < 2:
        return [f"{flow_result['case_id']}: expected 2 steps"]
    first = steps[0].get("actual") or {}
    second = steps[1].get("actual") or {}
    answer_1 = str(first.get("answer") or "")
    if "后台" in answer_1 and not any((first.get("task_id"), first.get("background_task_id"), first.get("pending_kind"))):
        issues.append(f"{flow_result['case_id']}: background task claimed without task signal")
    if first.get("task_status") == "pending" and second.get("task_status") == "succeeded" and not any((second.get("task_id"), second.get("background_task_id"), second.get("history_used"))):
        issues.append(f"{flow_result['case_id']}: pending task resolved without observable task followup signal")
    return issues
