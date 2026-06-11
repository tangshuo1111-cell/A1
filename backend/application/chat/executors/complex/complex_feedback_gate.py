"""Feedback request and gate evaluation helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import is_dataclass, replace
from typing import Any

from services.execution.feedback_gate import evaluate_feedback_request


def append_trace(
    bundle: Any,
    *,
    append_autonomy_trace: Callable[..., Any],
    plan: Any,
    round_index: int,
    trigger: str,
    requested_action: str,
    requested_by: str,
    answer_check: str,
    **kwargs: Any,
) -> Any:
    if not is_dataclass(bundle):
        return bundle
    return append_autonomy_trace(
        bundle,
        plan=plan,
        round_index=round_index,
        trigger=trigger,
        requested_action=requested_action,
        requested_by=requested_by,
        answer_check=answer_check,
        **kwargs,
    )


def build_feedback_request(
    *,
    plan: Any,
    bundle: Any,
    deps: Any,
    quality_gate: Any,
    current_round: int,
    synthesize_multisource_feedback_request: Callable[..., dict[str, Any] | None],
    synthesize_web_feedback_request: Callable[..., dict[str, Any] | None],
) -> dict[str, Any] | None:
    runtime = getattr(deps.answer_agent, "runtime", None)
    builder = getattr(runtime, "build_feedback_request", None)
    feedback_request = None
    if callable(builder):
        feedback_request = builder(plan=plan, bundle=bundle, current_round=current_round)
    if feedback_request is None and quality_gate.need_more_material:
        if str(getattr(plan, "job_type", "") or "") == "multi_source_compare":
            feedback_request = synthesize_multisource_feedback_request(
                plan=plan,
                bundle=bundle,
                current_round=current_round,
            )
        else:
            feedback_request = synthesize_web_feedback_request(
                plan=plan,
                bundle=bundle,
                current_round=current_round,
            )
    if feedback_request is None or not isinstance(feedback_request, dict):
        return None
    return feedback_request


def attach_feedback_gate_result(
    bundle: Any,
    *,
    feedback_request: dict[str, Any],
    feedback_gate_result: dict[str, Any],
) -> Any:
    if is_dataclass(bundle):
        return replace(bundle, feedback_request=feedback_request, feedback_gate_result=feedback_gate_result)
    bundle.feedback_request = feedback_request
    bundle.feedback_gate_result = feedback_gate_result
    return bundle


def evaluate_feedback_gate(
    *,
    feedback_request: dict[str, Any],
    plan: Any,
    current_round: int,
) -> dict[str, Any]:
    return evaluate_feedback_request(
        feedback_request=feedback_request,
        fallback_steps=getattr(plan, "fallback_steps", ()),
        tools_allowed=list(getattr(plan, "tools_allowed", ()) or []),
        privacy_scope=str(getattr(plan, "privacy_scope", "") or ""),
        budget_policy=dict(getattr(plan, "budget_policy", None) or {}),
        max_rounds=max(int(getattr(plan, "max_rounds", 0) or 0), 1),
        current_round=current_round,
    )
