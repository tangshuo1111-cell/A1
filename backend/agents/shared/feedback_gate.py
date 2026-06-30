"""Controlled feedback gate for default chain."""

from __future__ import annotations

import uuid
from typing import Any


def evaluate_feedback_request(
    *,
    feedback_request: dict[str, Any] | None,
    fallback_steps: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    tools_allowed: list[str] | tuple[str, ...] | None,
    privacy_scope: str,
    budget_policy: dict[str, Any] | None,
    max_rounds: int,
    current_round: int,
) -> dict[str, Any]:
    feedback_request = dict(feedback_request or {})
    fallback_steps = list(fallback_steps or [])
    tools_allowed = list(tools_allowed or [])
    budget_policy = dict(budget_policy or {})
    gate_result: dict[str, Any] = {
        "feedback_gate_result": f"fbgate_{uuid.uuid4().hex[:10]}",
        "allowed": False,
        "reason": "",
        "allowed_fallback_steps": [],
        "blocked_steps": [],
        "policy_violations": [],
    }

    if not feedback_request:
        gate_result["reason"] = "no_feedback_request"
        return gate_result
    if current_round >= max_rounds:
        gate_result["reason"] = "max_rounds_exceeded"
        gate_result["policy_violations"].append("超过 Main 允许的最大反馈轮次。")
        return gate_result

    original_intent = str(feedback_request.get("original_user_intent", "") or "")
    query_hint = str(feedback_request.get("query_hint", "") or "")
    if query_hint and original_intent and query_hint not in original_intent and original_intent not in query_hint:
        gate_result["reason"] = "intent_changed"
        gate_result["policy_violations"].append("feedback_request 改变了用户原始意图。")
        return gate_result

    step_map = {str(step.get("step_id", "")): dict(step) for step in fallback_steps}
    requested_ids = [str(x) for x in feedback_request.get("requested_fallback_step_ids", []) or []]
    requested_steps = []
    for step_id in requested_ids:
        step = step_map.get(step_id)
        if step is None:
            gate_result["blocked_steps"].append(step_id)
            gate_result["policy_violations"].append("请求的 fallback_step 不在 Main 允许范围内。")
            continue
        requested_steps.append(step)

    if not requested_steps:
        gate_result["reason"] = gate_result["reason"] or "fallback_not_allowed_by_main"
        return gate_result

    allowed_steps = []
    for step in requested_steps:
        step_id = str(step.get("step_id", ""))
        tool_name = str(step.get("tool_name", ""))
        if tools_allowed and tool_name not in tools_allowed:
            gate_result["blocked_steps"].append(step_id)
            gate_result["policy_violations"].append(f"{tool_name} 不在 Main tools_allowed 中。")
            continue
        if privacy_scope and privacy_scope != "public_web":
            gate_result["blocked_steps"].append(step_id)
            gate_result["policy_violations"].append("privacy_scope 不允许外部处理。")
            continue
        if tool_name == "web_search" and "web_search" not in tools_allowed:
            gate_result["blocked_steps"].append(step_id)
            gate_result["policy_violations"].append("外部搜索未被 Main 允许。")
            continue
        if tool_name == "ocr_document" and not budget_policy.get("paid_ocr_authorized", False):
            gate_result["blocked_steps"].append(step_id)
            gate_result["policy_violations"].append("付费 OCR 未授权或预算不允许。")
            continue
        if tool_name == "asr_transcribe" and not budget_policy.get("paid_asr_authorized", False):
            gate_result["blocked_steps"].append(step_id)
            gate_result["policy_violations"].append("付费 ASR 未授权或预算不允许。")
            continue
        allowed_steps.append(step)

    gate_result["allowed_fallback_steps"] = allowed_steps
    if allowed_steps:
        gate_result["allowed"] = True
        gate_result["reason"] = "allowed"
    else:
        gate_result["reason"] = gate_result["reason"] or "all_requested_steps_blocked"
    return gate_result
