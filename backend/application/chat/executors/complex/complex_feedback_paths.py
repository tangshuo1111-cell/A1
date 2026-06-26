"""Decision branches for complex feedback execution."""

from __future__ import annotations

from typing import Any

from application.chat.complex_pending_mapping import complex_pending_kind_active
from application.chat.executors.complex import complex_feedback_refresh as feedback_refresh_mod
from application.chat.executors.complex.complex_feedback_trace import trace_feedback_round


def maybe_stop_for_budget(
    bundle: Any,
    *,
    plan: Any,
    current_round: int,
    stop_reason: str | None,
) -> Any | None:
    if not stop_reason:
        return None
    bundle = trace_feedback_round(
        bundle,
        plan=plan,
        round_index=current_round,
        trigger="budget_guard",
        requested_action="abort_and_finalize",
        requested_by="MainAgent",
        stop_reason=stop_reason,
        answer_check="pass",
    )
    if complex_pending_kind_active() and current_round == 0:
        return feedback_refresh_mod.apply_multisource_budget_short_circuit(
            bundle,
            stop_reason=stop_reason,
        )
    return bundle


def reject_missing_feedback_request(
    bundle: Any,
    *,
    plan: Any,
    current_round: int,
    quality_gate: Any,
) -> Any:
    return trace_feedback_round(
        bundle,
        plan=plan,
        round_index=current_round,
        trigger="quality_gate_refine",
        requested_action="abort_and_finalize",
        requested_by="quality_gate",
        stop_reason="no_executable_feedback_plan",
        answer_check="pass",
        payload={"refine_reason_codes": list(quality_gate.reason_codes)},
    )


def schedule_answer_only_refine(
    bundle: Any,
    *,
    plan: Any,
    current_round: int,
    quality_gate: Any,
) -> Any:
    from dataclasses import is_dataclass, replace

    bundle = trace_feedback_round(
        bundle,
        plan=plan,
        round_index=current_round,
        trigger="quality_gate_refine",
        requested_action="answer_only_regenerate",
        requested_by="quality_gate",
        stop_reason="answer_only_refine_scheduled",
        answer_check="retry_generate",
        payload={
            "refine_reason_codes": list(quality_gate.reason_codes),
            "refine_kind": "answer_only",
        },
    )
    if is_dataclass(bundle):
        return replace(
            bundle,
            used_rounds=[0, 1],
            final_answer_based_on_round="round_1",
        )
    return bundle


def reject_feedback_gate(
    bundle: Any,
    *,
    plan: Any,
    current_round: int,
) -> Any:
    return trace_feedback_round(
        bundle,
        plan=plan,
        round_index=current_round,
        trigger="quality_gate_refine",
        requested_action="abort_and_finalize",
        requested_by="feedback_gate",
        stop_reason="feedback_gate_denied",
        answer_check="more_evidence",
        more_evidence_requested=True,
    )


def complete_feedback_round(
    bundle: Any,
    *,
    plan: Any,
    stop_reason: str,
    retry_requested: bool = False,
) -> Any:
    return trace_feedback_round(
        bundle,
        plan=plan,
        round_index=1,
        trigger="quality_gate_refine",
        requested_action="continue_same_plan",
        requested_by="MiddleAgent",
        stop_reason=stop_reason,
        answer_check="pass",
        more_evidence_requested=True,
        retry_requested=retry_requested,
    )


def reject_tool_failure(
    bundle: Any,
    *,
    plan: Any,
    current_round: int = 0,
    stop_reason: str,
    retry_requested: bool = False,
) -> Any:
    return trace_feedback_round(
        bundle,
        plan=plan,
        round_index=1 if retry_requested else current_round,
        trigger="tool_failure",
        requested_action="abort_and_finalize",
        requested_by="MiddleAgent",
        stop_reason=stop_reason,
        answer_check="more_evidence",
        more_evidence_requested=True,
        retry_requested=retry_requested,
    )
