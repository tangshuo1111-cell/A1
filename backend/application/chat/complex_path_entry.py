"""Complex path — round0 answer then quality_gate; feedback round is execution-only."""

from __future__ import annotations

from dataclasses import dataclass, is_dataclass, replace
from typing import Any

from application.chat.autonomy_loop import append_autonomy_trace, autonomy_stop_reason_with_clock
from application.chat.chat_contracts import QualityGateResult
from application.chat.complex_pending_mapping import (
    apply_multisource_budget_short_circuit,
    attach_complex_pending_context,
    complex_pending_kind_active,
)
from application.chat.pending_kind import PendingKind
from config.feature_flags import three_agent_autonomy_active
from services.capabilities.web import web_orchestration_service as agno_web_service
from services.execution.feedback_gate import evaluate_feedback_request


@dataclass(frozen=True)
class FeedbackGatherContext:
    use_knowledge: bool
    history_snapshot: Any
    session_id: str | None
    v13_text_content: str | None
    v13_title: str | None
    v13_file_content: str | bytes | None
    shared_prep: Any | None = None


def build_deadline_limited_answer(bundle: Any) -> tuple[str, str]:
    pending_item = getattr(bundle, "pending_item", None)
    source_type = str(getattr(pending_item, "source_type", "") or getattr(bundle, "v13_source_type", "") or "")
    if source_type in {"web_video", "local_video"} or getattr(bundle, "mcp_video_pending_id", None):
        return "视频材料仍在处理中，我先在 20 秒截止前返回主响应。你可以稍后轮询任务结果，或等后台处理完成后继续追问。", "pending"
    return "我先在 20 秒截止前返回当前结果。现有材料不足以继续扩展，建议补充来源或稍后继续。", "partial"


def _synthesize_web_feedback_request(*, plan: Any, bundle: Any, current_round: int) -> dict[str, Any] | None:
    if not getattr(plan.xiezuo_pan, "allow_web", False):
        return None
    if getattr(bundle, "web_block", None):
        return None
    return {
        "feedback_request_id": f"fbreq_{getattr(bundle, 'bundle_id', 'default')}",
        "job_id": str(getattr(plan.decision, "task_id", "") or ""),
        "round_index": current_round,
        "reason": "quality_gate 触发补抓网页证据",
        "evidence_gap": "质量门控判定材料不足，需补抓网页证据。",
        "query_hint": getattr(plan, "original_user_intent", "") or "",
        "requested_source_task_ids": [],
        "requested_fallback_step_ids": ["default_web_round1"],
        "requested_fallback_steps": [
            {
                "step_id": "default_web_round1",
                "tool_name": "fetch_web",
                "source_type": "web",
            }
        ],
        "material_sufficiency_before": getattr(bundle, "material_sufficiency", "insufficient"),
        "original_user_intent": getattr(plan, "original_user_intent", "") or "",
        "status": "requested",
    }


def _synthesize_multisource_feedback_request(*, plan: Any, bundle: Any, current_round: int) -> dict[str, Any]:
    fallback_steps = list(getattr(plan, "fallback_steps", ()) or ())
    requested = [
        {
            "step_id": str(step.get("step_id", f"ms_{idx}")),
            "tool_name": str(step.get("tool_name", "")),
            "source_type": str(step.get("source_type", "")),
        }
        for idx, step in enumerate(fallback_steps)
        if isinstance(step, dict) and step.get("tool_name")
    ]
    if not requested:
        requested = [
            {"step_id": "default_web_round1", "tool_name": "fetch_web", "source_type": "web"},
        ]
        if getattr(plan.xiezuo_pan, "allow_kb", False):
            requested.append({"step_id": "default_kb_round1", "tool_name": "retrieve_kb", "source_type": "kb"})
    return {
        "feedback_request_id": f"fbreq_{getattr(bundle, 'bundle_id', 'default')}",
        "job_id": str(getattr(plan.decision, "task_id", "") or ""),
        "round_index": current_round,
        "reason": "quality_gate 触发多来源补材",
        "evidence_gap": "质量门控判定多来源比较材料不足。",
        "query_hint": getattr(plan, "original_user_intent", "") or "",
        "requested_source_task_ids": [],
        "requested_fallback_step_ids": [step["step_id"] for step in requested],
        "requested_fallback_steps": requested,
        "material_sufficiency_before": getattr(bundle, "material_sufficiency", "insufficient"),
        "original_user_intent": getattr(plan, "original_user_intent", "") or "",
        "status": "requested",
    }


def run_multisource_round0_answer(
    message: str,
    plan: Any,
    bundle: Any,
    deps: Any,
    *,
    use_knowledge: bool,
    history_snapshot: Any,
    session_id: str | None,
    context_block: str | None,
    knowledge_block: str | None,
    web_block: str | None,
    main_dec: Any,
    v13_text_content: str | None,
    v13_title: str | None,
    v13_file_content: str | bytes | None,
    session_pending_kind: PendingKind = PendingKind.NONE,
    budget_clock: Any | None = None,
) -> tuple[Any, str]:
    """Produce round-0 answer only; second round is driven by quality_gate in run_chat_turn."""
    bundle = attach_complex_pending_context(bundle, session_pending=session_pending_kind)
    if not three_agent_autonomy_active():
        answer_text = deps.run_basic_qa(
            message,
            context_block=context_block,
            knowledge_block=knowledge_block,
            web_search_block=web_block,
            main_decision=main_dec,
            collaboration_plan=plan,
            material_bundle=bundle,
            clock=budget_clock,
        )
        return bundle, answer_text
    stop_reason = autonomy_stop_reason_with_clock(
        plan,
        current_round=0,
        clock=budget_clock if complex_pending_kind_active() else None,
    )
    if stop_reason:
        bundle = append_autonomy_trace(
            bundle,
            plan=plan,
            round_index=0,
            trigger="budget_guard",
            requested_action="abort_and_finalize",
            requested_by="MainAgent",
            stop_reason=stop_reason,
            answer_check="pass",
        )
        if complex_pending_kind_active():
            bundle = apply_multisource_budget_short_circuit(bundle, stop_reason=stop_reason)
        answer_text = deps.run_basic_qa(
            message,
            context_block=context_block,
            knowledge_block=knowledge_block,
            web_search_block=web_block,
            main_decision=main_dec,
            collaboration_plan=plan,
            material_bundle=bundle,
            clock=budget_clock,
        )
        return bundle, answer_text

    if is_dataclass(bundle):
        bundle = append_autonomy_trace(
            bundle,
            plan=plan,
            round_index=0,
            trigger="initial_dispatch",
            requested_action="await_quality_gate",
            requested_by="MainAgent",
            answer_check="pending",
            payload={"job_type": "multi_source_compare"},
        )

    answer_text = deps.run_basic_qa(
        message,
        context_block=context_block,
        knowledge_block=knowledge_block,
        web_search_block=web_block,
        main_decision=main_dec,
        collaboration_plan=plan,
        material_bundle=bundle,
        clock=budget_clock,
    )
    return bundle, answer_text


def run_feedback_round_execution(
    message: str,
    plan: Any,
    bundle: Any,
    deps: Any,
    *,
    quality_gate: QualityGateResult,
    current_round: int = 0,
    session_pending_kind: PendingKind = PendingKind.NONE,
    budget_clock: Any | None = None,
    gather_context: FeedbackGatherContext | None = None,
) -> Any:
    """Execute round-1 material actions after quality_gate requested refine.

    Does not decide whether to refine — caller must pass quality_gate.need_second_round=True.
    """
    if not quality_gate.need_second_round:
        return bundle
    bundle = attach_complex_pending_context(bundle, session_pending=session_pending_kind)
    if not three_agent_autonomy_active():
        return bundle

    def _trace(bundle_in: Any, **kwargs: Any) -> Any:
        if not is_dataclass(bundle_in):
            return bundle_in
        return append_autonomy_trace(bundle_in, **kwargs)

    stop_reason = autonomy_stop_reason_with_clock(
        plan,
        current_round=current_round,
        clock=budget_clock if complex_pending_kind_active() else None,
    )
    if stop_reason:
        bundle = _trace(
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
            return apply_multisource_budget_short_circuit(bundle, stop_reason=stop_reason)
        return bundle

    job_type = str(getattr(plan, "job_type", "") or "")
    runtime = getattr(deps.answer_agent, "runtime", None)
    builder = getattr(runtime, "build_feedback_request", None)
    feedback_request = None
    if callable(builder):
        feedback_request = builder(plan=plan, bundle=bundle, current_round=current_round)
    if feedback_request is None and quality_gate.need_more_material:
        if job_type == "multi_source_compare":
            feedback_request = _synthesize_multisource_feedback_request(
                plan=plan,
                bundle=bundle,
                current_round=current_round,
            )
        else:
            feedback_request = _synthesize_web_feedback_request(
                plan=plan,
                bundle=bundle,
                current_round=current_round,
            )
    if feedback_request is None or not isinstance(feedback_request, dict):
        return _trace(
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

    feedback_gate_result = evaluate_feedback_request(
        feedback_request=feedback_request,
        fallback_steps=getattr(plan, "fallback_steps", ()),
        tools_allowed=list(getattr(plan, "tools_allowed", ()) or []),
        privacy_scope=str(getattr(plan, "privacy_scope", "") or ""),
        budget_policy=dict(getattr(plan, "budget_policy", None) or {}),
        max_rounds=max(int(getattr(plan, "max_rounds", 0) or 0), 1),
        current_round=current_round,
    )
    if is_dataclass(bundle):
        bundle = replace(bundle, feedback_request=feedback_request, feedback_gate_result=feedback_gate_result)
    else:
        bundle.feedback_request = feedback_request
        bundle.feedback_gate_result = feedback_gate_result
    bundle = _trace(
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
        if is_dataclass(bundle):
            blocked = replace(bundle, used_rounds=[0], final_answer_based_on_round="round_0", round_delta={"job_id": str(getattr(plan.decision, "task_id", "") or ""), "round_0_bundle_id": getattr(bundle, "bundle_id", ""), "round_1_bundle_id": "", "new_tool_calls": [], "new_source_tasks": [], "new_source_briefs": [], "new_chunks_added": [], "new_failures_added": [], "material_sufficiency_before": getattr(bundle, "material_sufficiency", "insufficient"), "material_sufficiency_after": getattr(bundle, "material_sufficiency", "insufficient"), "feedback_result": feedback_gate_result, "final_answer_based_on_round": "round_0"})
        else:
            blocked = bundle
        return _trace(
            blocked,
            plan=plan,
            round_index=current_round,
            trigger="quality_gate_refine",
            requested_action="abort_and_finalize",
            requested_by="feedback_gate",
            stop_reason="feedback_gate_denied",
            answer_check="more_evidence",
            more_evidence_requested=True,
        )

    if job_type == "multi_source_compare" and gather_context is not None:
        bundle = deps.middle_agent.caipan(
            message,
            plan=plan,
            shared_prep=gather_context.shared_prep,
            http_use_knowledge=gather_context.use_knowledge,
            history=gather_context.history_snapshot,
            session_id=gather_context.session_id or "",
            v13_text_content=gather_context.v13_text_content,
            v13_title=gather_context.v13_title,
            v13_file_content=gather_context.v13_file_content,
            prior_bundle=bundle,
            allowed_fallback_steps=list(feedback_gate_result.get("allowed_fallback_steps") or []),
            current_round=current_round + 1,
            feedback_gate_result=feedback_gate_result,
            clock=budget_clock,
        )
        if is_dataclass(bundle):
            bundle = replace(
                bundle,
                feedback_request=feedback_request,
                feedback_gate_result=feedback_gate_result,
                used_rounds=[0, 1],
                final_answer_based_on_round="round_1",
            )
        return _trace(
            bundle,
            plan=plan,
            round_index=1,
            trigger="quality_gate_refine",
            requested_action="continue_same_plan",
            requested_by="MiddleAgent",
            stop_reason="round_1_completed",
            answer_check="pass",
            more_evidence_requested=True,
        )

    if (
        gather_context is not None
        and quality_gate.need_more_material
        and getattr(getattr(gather_context, "shared_prep", None), "snapshot", None) is not None
        and getattr(gather_context.shared_prep.snapshot, "chunks", ())
        and not list(getattr(bundle, "retrieved_chunks", []) or [])
    ):
        refreshed_bundle = deps.middle_agent.caipan(
            message,
            plan=plan,
            shared_prep=gather_context.shared_prep,
            http_use_knowledge=gather_context.use_knowledge,
            history=gather_context.history_snapshot,
            session_id=gather_context.session_id or "",
            v13_text_content=gather_context.v13_text_content,
            v13_title=gather_context.v13_title,
            v13_file_content=gather_context.v13_file_content,
            clock=budget_clock,
        )
        if is_dataclass(refreshed_bundle):
            refreshed_bundle = replace(
                refreshed_bundle,
                feedback_request=feedback_request,
                feedback_gate_result=feedback_gate_result,
                used_rounds=[0, 1],
                final_answer_based_on_round="round_1",
            )
        bundle = _trace(
            refreshed_bundle,
            plan=plan,
            round_index=1,
            trigger="quality_gate_refine",
            requested_action="continue_same_plan",
            requested_by="MiddleAgent",
            stop_reason="round_1_kb_refresh_completed",
            answer_check="pass",
            more_evidence_requested=True,
        )
        if list(getattr(bundle, "retrieved_chunks", []) or []):
            return bundle

    allowed_steps = list(feedback_gate_result.get("allowed_fallback_steps") or [])
    budget_policy = dict(getattr(plan, "budget_policy", None) or {})
    if int(budget_policy.get("tool_calls_remaining", 1)) <= 0:
        return _trace(
            bundle,
            plan=plan,
            round_index=current_round,
            trigger="tool_failure",
            requested_action="abort_and_finalize",
            requested_by="MiddleAgent",
            stop_reason="tool_calls_exhausted",
            answer_check="more_evidence",
            more_evidence_requested=True,
        )
    if not any(str(step.get("tool_name", "")) == "fetch_web" for step in allowed_steps):
        return bundle
    new_web_block = agno_web_service.fetch_web_evidence_block(message, max_results=3)
    if not (new_web_block or "").strip():
        if is_dataclass(bundle):
            failed = replace(bundle, used_rounds=[0, 1], final_answer_based_on_round="round_0", round_delta={"job_id": str(getattr(plan.decision, "task_id", "") or ""), "round_0_bundle_id": getattr(bundle, "bundle_id", ""), "round_1_bundle_id": "", "new_tool_calls": [{"tool": "fetch_web", "ok": False, "round": "round_1"}], "new_source_tasks": [], "new_source_briefs": [], "new_chunks_added": [], "new_failures_added": [{"tool": "fetch_web", "reason": "web_fetch_empty", "recoverable": True, "round": "round_1"}], "material_sufficiency_before": getattr(bundle, "material_sufficiency", "insufficient"), "material_sufficiency_after": getattr(bundle, "material_sufficiency", "insufficient"), "feedback_result": feedback_gate_result, "final_answer_based_on_round": "round_0"}, answer_limitations=list(dict.fromkeys(list(getattr(bundle, "answer_limitations", []) or []) + ["补网后仍未获得可用网页证据。"])))
        else:
            failed = bundle
        return _trace(
            failed,
            plan=plan,
            round_index=1,
            trigger="tool_failure",
            requested_action="abort_and_finalize",
            requested_by="MiddleAgent",
            stop_reason="web_fetch_empty",
            answer_check="more_evidence",
            more_evidence_requested=True,
            retry_requested=True,
        )
    updated_failures = list(getattr(bundle, "failures", []) or [])
    updated_tool_calls = list(getattr(bundle, "tool_calls", []) or [])
    updated_tool_calls.append({"tool": "fetch_web", "ok": True, "round": "round_1"})
    updated_critic = dict(getattr(bundle, "critic_check", {}) or {})
    updated_critic["revision_required"] = False
    updated_critic["safe_to_answer"] = True
    updated_limitations = list(dict.fromkeys(list(updated_critic.get("limitations") or []) + ["已通过 round_1 补充网页证据。"]))
    updated_critic["limitations"] = updated_limitations
    updated_envs = list(getattr(bundle, "evidence_envelopes", []) or [])
    if not any(getattr(env, "source_type", "") == "web" for env in updated_envs):
        from agents.middle_agent.schema import EvidenceEnvelope
        updated_envs.append(EvidenceEnvelope(source_type="web", status="success", text=new_web_block, summary=new_web_block[:200], confidence=0.72))
    success = replace(bundle, web_block=new_web_block, material_still_insufficient=False, web_judgment_reason="feedback_round_1_fetch_web", execution_status="ok", material_sufficiency="sufficient", critic_check=updated_critic, tool_calls=updated_tool_calls, failures=updated_failures, evidence_envelopes=updated_envs, feedback_request=feedback_request, feedback_gate_result=feedback_gate_result, used_rounds=[0, 1], final_answer_based_on_round="round_1", round_delta={"job_id": str(getattr(plan.decision, "task_id", "") or ""), "round_0_bundle_id": getattr(bundle, "bundle_id", ""), "round_1_bundle_id": getattr(bundle, "bundle_id", ""), "new_tool_calls": [{"tool": "fetch_web", "ok": True, "round": "round_1"}], "new_source_tasks": [], "new_source_briefs": [], "new_chunks_added": [], "new_failures_added": [], "material_sufficiency_before": getattr(bundle, "material_sufficiency", "insufficient"), "material_sufficiency_after": "sufficient", "feedback_result": feedback_gate_result, "final_answer_based_on_round": "round_1"}, answer_limitations=updated_limitations)
    return _trace(
        success,
        plan=plan,
        round_index=1,
        trigger="quality_gate_refine",
        requested_action="continue_same_plan",
        requested_by="MiddleAgent",
        stop_reason="round_1_completed",
        answer_check="pass",
        more_evidence_requested=True,
        retry_requested=True,
    )


run_default_feedback_round = run_feedback_round_execution
