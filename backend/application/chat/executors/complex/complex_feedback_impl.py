"""Complex feedback round execution after quality_gate (Round 18 thin coordinator)."""

from __future__ import annotations

from typing import Any

from application.chat import autonomy_loop
from application.chat.complex_pending_mapping import attach_complex_pending_context, complex_pending_kind_active
from application.chat.executors.complex.complex_deadline import FeedbackGatherContext
from application.chat.executors.complex import complex_feedback_gate as feedback_gate_mod
from application.chat.executors.complex import complex_feedback_refresh as feedback_refresh_mod
from application.chat.executors.complex.complex_feedback_paths import (
    complete_feedback_round,
    maybe_stop_for_budget,
    reject_feedback_gate,
    reject_missing_feedback_request,
    reject_tool_failure,
)
from application.chat.executors.complex.complex_feedback_trace import trace_feedback_round
from application.chat.executors.complex.complex_feedback_synthesize import (
    synthesize_multisource_feedback_request,
    synthesize_web_feedback_request,
)
from application.chat.executors.complex import complex_feedback_web_fetch as feedback_web_fetch_mod
from application.chat.pending_kind import PendingKind
from config.feature_flags import three_agent_autonomy_active
from services.capabilities.web import web_orchestration_service as agno_web_service


def run_feedback_round_execution(
    message: str,
    plan: Any,
    bundle: Any,
    deps: Any,
    *,
    quality_gate: Any,
    current_round: int = 0,
    session_pending_kind: PendingKind = PendingKind.NONE,
    budget_clock: Any | None = None,
    gather_context: FeedbackGatherContext | None = None,
) -> Any:
    """Execute round-1 material actions after quality_gate requested refine."""
    if not quality_gate.need_second_round:
        return bundle
    bundle = attach_complex_pending_context(bundle, session_pending=session_pending_kind)
    if not three_agent_autonomy_active():
        return bundle

    stop_reason = autonomy_loop.autonomy_stop_reason_with_clock(
        plan,
        current_round=current_round,
        clock=budget_clock if complex_pending_kind_active() else None,
    )
    budget_result = maybe_stop_for_budget(
        bundle,
        plan=plan,
        current_round=current_round,
        stop_reason=stop_reason,
    )
    if budget_result is not None:
        return budget_result

    feedback_request = feedback_gate_mod.build_feedback_request(
        plan=plan,
        bundle=bundle,
        deps=deps,
        quality_gate=quality_gate,
        current_round=current_round,
        synthesize_multisource_feedback_request=synthesize_multisource_feedback_request,
        synthesize_web_feedback_request=synthesize_web_feedback_request,
    )
    if feedback_request is None:
        return reject_missing_feedback_request(
            bundle,
            plan=plan,
            current_round=current_round,
            quality_gate=quality_gate,
        )

    feedback_gate_result = feedback_gate_mod.evaluate_feedback_gate(
        feedback_request=feedback_request,
        plan=plan,
        current_round=current_round,
    )
    bundle = feedback_gate_mod.attach_feedback_gate_result(
        bundle,
        feedback_request=feedback_request,
        feedback_gate_result=feedback_gate_result,
    )
    bundle = trace_feedback_round(
        bundle,
        plan=plan,
        round_index=current_round,
        trigger="quality_gate_refine",
        requested_action="more_material",
        requested_by="quality_gate",
        answer_check="more_evidence",
        more_evidence_requested=True,
        payload={"refine_reason_codes": list(quality_gate.reason_codes)},
    )
    if not feedback_gate_result.get("allowed"):
        return reject_feedback_gate(bundle, plan=plan, current_round=current_round)

    if str(getattr(plan, "job_type", "") or "") == "multi_source_compare" and gather_context is not None:
        bundle = feedback_refresh_mod.run_multisource_refresh(
            message=message,
            plan=plan,
            bundle=bundle,
            deps=deps,
            feedback_gate_result=feedback_gate_result,
            gather_context=gather_context,
            current_round=current_round,
            budget_clock=budget_clock,
        )
        return complete_feedback_round(
            bundle,
            plan=plan,
            stop_reason="round_1_completed",
        )

    refreshed_bundle = feedback_refresh_mod.maybe_refresh_from_shared_prep(
        message=message,
        plan=plan,
        bundle=bundle,
        deps=deps,
        feedback_gate_result=feedback_gate_result,
        gather_context=gather_context if quality_gate.need_more_material else None,
        budget_clock=budget_clock,
    )
    if refreshed_bundle is not None:
        bundle = complete_feedback_round(
            refreshed_bundle,
            plan=plan,
            stop_reason="round_1_kb_refresh_completed",
        )
        if list(getattr(bundle, "retrieved_chunks", []) or []):
            return bundle

    budget_policy = dict(getattr(plan, "budget_policy", None) or {})
    if int(budget_policy.get("tool_calls_remaining", 1)) <= 0:
        return reject_tool_failure(
            bundle,
            plan=plan,
            current_round=current_round,
            stop_reason="tool_calls_exhausted",
        )
    allowed_steps = list(feedback_gate_result.get("allowed_fallback_steps") or [])
    if not any(str(step.get("tool_name", "")) == "fetch_web" for step in allowed_steps):
        return bundle

    bundle, fetch_ok = feedback_web_fetch_mod.run_web_feedback_fetch(
        message=message,
        plan=plan,
        bundle=bundle,
        feedback_gate_result=feedback_gate_result,
        fetch_web_evidence_block=agno_web_service.fetch_web_evidence_block,
    )
    if not fetch_ok:
        return reject_tool_failure(
            bundle,
            plan=plan,
            stop_reason="web_fetch_empty",
            retry_requested=True,
        )
    return complete_feedback_round(
        bundle,
        plan=plan,
        stop_reason="round_1_completed",
        retry_requested=True,
    )


run_default_feedback_round = run_feedback_round_execution
