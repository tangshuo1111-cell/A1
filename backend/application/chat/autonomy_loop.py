from __future__ import annotations

from dataclasses import replace
from typing import Any

from config.budget_policy import BUDGET_POLICY_DEFAULTS, MAX_AUTONOMY_ROUNDS


def build_budget_snapshot(plan: Any) -> dict[str, int]:
    budget_policy = dict(getattr(plan, "budget_policy", None) or {})
    return {
        "budget_remaining_ms": int(
            getattr(plan, "remaining_ms_hint", 0)
            or budget_policy.get("budget_remaining_ms", 0)
            or 0
        ),
        "llm_calls_remaining": int(
            budget_policy.get("llm_calls_remaining", BUDGET_POLICY_DEFAULTS.default_llm_calls_remaining)
        ),
        "tool_calls_remaining": int(
            budget_policy.get("tool_calls_remaining", BUDGET_POLICY_DEFAULTS.default_tool_calls_remaining)
        ),
    }


def build_loop_id(bundle: Any) -> str:
    seed = str(getattr(bundle, "bundle_id", "") or "default")
    return f"loop_{seed}"


def build_autonomy_event(
    *,
    bundle: Any,
    plan: Any,
    round_index: int,
    trigger: str,
    requested_action: str,
    requested_by: str,
    stop_reason: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "loop_id": build_loop_id(bundle),
        "round_index": round_index,
        "trigger": trigger,
        "requested_action": requested_action,
        "requested_by": requested_by,
        "budget_snapshot": build_budget_snapshot(plan),
        "stop_reason": stop_reason,
        "payload": dict(payload or {}),
    }


def classify_answer_check(*, feedback_request: dict[str, Any] | None, critic_check: dict[str, Any] | None) -> str:
    critic = dict(critic_check or {})
    if feedback_request:
        return "more_evidence"
    if critic.get("revision_required", False):
        return "revise"
    return "pass"


def append_autonomy_trace(
    bundle: Any,
    *,
    plan: Any,
    round_index: int,
    trigger: str,
    requested_action: str,
    requested_by: str,
    stop_reason: str = "",
    answer_check: str | None = None,
    revise_requested: bool = False,
    retry_requested: bool = False,
    more_evidence_requested: bool = False,
    payload: dict[str, Any] | None = None,
) -> Any:
    events = list(getattr(bundle, "autonomy_events", []) or [])
    event = build_autonomy_event(
        bundle=bundle,
        plan=plan,
        round_index=round_index,
        trigger=trigger,
        requested_action=requested_action,
        requested_by=requested_by,
        stop_reason=stop_reason,
        payload=payload,
    )
    events.append(event)
    if answer_check is None:
        answer_check = classify_answer_check(
            feedback_request=getattr(bundle, "feedback_request", None),
            critic_check=getattr(bundle, "critic_check", None),
        )
    return replace(
        bundle,
        autonomy_loop_id=build_loop_id(bundle),
        autonomy_events=events,
        stop_reason=stop_reason or str(getattr(bundle, "stop_reason", "") or ""),
        answer_check=answer_check,
        revise_requested=revise_requested,
        retry_requested=retry_requested,
        more_evidence_requested=more_evidence_requested,
        retry_count=max(int(getattr(bundle, "retry_count", 0) or 0), 0),
    )


def autonomy_stop_reason(plan: Any, *, current_round: int) -> str:
    budget = build_budget_snapshot(plan)
    max_rounds = max(
        int(getattr(plan, "max_rounds", 0) or 0),
        1,
    )
    if current_round >= min(MAX_AUTONOMY_ROUNDS, max_rounds):
        return "max_round_reached"
    if budget["budget_remaining_ms"] <= BUDGET_POLICY_DEFAULTS.min_remaining_ms_to_continue:
        return "budget_exhausted"
    if budget["llm_calls_remaining"] <= 0:
        return "llm_calls_exhausted"
    return ""


def autonomy_stop_reason_with_clock(
    plan: Any,
    *,
    current_round: int,
    clock: Any | None = None,
    reserve_ms: int = 500,
) -> str:
    """Plan budget guard plus optional SLA clock for complex first-response (§6.2.1 / S7c)."""
    reason = autonomy_stop_reason(plan, current_round=current_round)
    if reason:
        return reason
    if clock is not None and int(clock.remaining_ms(reserve_ms=reserve_ms)) <= 0:
        return "budget_exhausted"
    return ""
