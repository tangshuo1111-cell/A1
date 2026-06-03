"""台账 G-005「invoke_tail_flow」：gather 完成之后 → trace / V13 / V15 finalize → Bundle。

承接 `MiddleGatherPhaseOutcome`，避免 `invoke_executor` 再手工 unpack 数十个局部变量。
"""

from __future__ import annotations

from typing import Any

from agents._runtime import AgentRunFrame
from agents.main_agent import AgnoCollaborationPlan
from debug_trace import trace
from schemas import MainDecision

from . import bundle_finalize_flow, pending_flow
from .evidence_checker import build_default_chain_critic_check
from .gather_phase import MiddleGatherPhaseOutcome
from .schema import AgnoMaterialBundle, EvidenceEnvelope


def build_material_bundle_after_gather(
    *,
    frame: AgentRunFrame,
    message: str,
    inputs: dict[str, Any],
    msg: str,
    session_id: str,
    plan: AgnoCollaborationPlan,
    decision: MainDecision,
    http_use_knowledge: bool,
    blocked_failures: list[dict[str, Any]],
    g: MiddleGatherPhaseOutcome,
) -> AgnoMaterialBundle:
    envelopes: list[EvidenceEnvelope] = []
    if g.try_rag:
        envelopes.append(
            EvidenceEnvelope(
                source_type="kb",
                status="success" if g.knowledge_block else "failed",
                text=g.knowledge_block or "",
                summary=(g.knowledge_block or "")[:200],
                confidence=1.0 if g.knowledge_adequate else 0.35,
                error_code="" if g.knowledge_block else "kb_no_match",
                next_action="" if g.knowledge_block else "fallback_or_conservative_answer",
            ),
        )
    if g.want_web:
        envelopes.append(
            EvidenceEnvelope(
                source_type="web",
                status="success" if g.web_block else "failed",
                text=g.web_block or "",
                summary=(g.web_block or "")[:200],
                confidence=0.75 if g.web_block else 0.2,
                error_code="" if g.web_block else "web_fetch_failed",
                next_action="" if g.web_block else "fallback_or_conservative_answer",
            ),
        )
    if g.video_url_yitu.get("has_video_url") or g.mcp_video_decision != "skip_no_video_yitu":
        video_status = "success"
        video_error = ""
        video_text = g.mcp_video_text or ""
        video_task_id = g.mcp_video_pending_id or ""
        if not video_task_id and getattr(g.video_url_result, "extra", None):
            _video_extra = getattr(g.video_url_result, "extra", {}) or {}
            video_task_id = str(
                _video_extra.get("background_task_id")
                or _video_extra.get("task_id")
                or ""
            )
        if video_task_id:
            video_status = "pending"
        elif not g.mcp_video_ok and not getattr(g.video_url_result, "success", False):
            video_status = "failed"
            video_error = (
                g.mcp_video_error
                or g.video_url_ingest_error
                or "video_unreachable"
            )
        elif getattr(g.video_url_result, "success", False):
            video_text = getattr(g.video_url_result, "text", "") or video_text
        envelopes.append(
            EvidenceEnvelope(
                source_type="video",
                status=video_status,
                text=video_text,
                summary=video_text[:200],
                confidence=0.8 if video_text else 0.3,
                error_code=video_error,
                next_action="poll_task_result" if video_task_id else "",
                task_id=video_task_id,
            ),
        )

    _early_norm = str(g.early_web_video_url_normalized or "")
    knowledge_block = g.knowledge_block

    lines = bundle_finalize_flow.build_trace_lines_pre_v13(
        message=message,
        http_use_knowledge=http_use_knowledge,
        plan=plan,
        decision=decision,
        intent=g.intent,
        try_rag=g.try_rag,
        knowledge_block=knowledge_block,
        v14_trace_info=g.v14_trace_info,
        web_reason=g.web_reason,
        want_web=g.want_web,
        web_block=g.web_block,
        cailiao_pan=g.cailiao_pan,
        knowledge_adequate=g.knowledge_adequate,
        kb_tier=g.kb_tier,
        material_insufficient=g.material_insufficient,
        signal=g.signal,
        video_yitu=g.video_yitu,
        mcp_video_decision=g.mcp_video_decision,
        mcp_video_ok=g.mcp_video_ok,
        mcp_video_source=g.mcp_video_source,
        mcp_video_text=g.mcp_video_text,
        mcp_video_error=g.mcp_video_error or "",
        mcp_video_pending_id=g.mcp_video_pending_id,
        mcp_video_ingest_error=g.mcp_video_ingest_error or "",
        video_url_yitu=g.video_url_yitu,
        video_url_from=g.video_url_from,
        video_url_decision=g.video_url_decision,
        video_url_result=g.video_url_result,
        video_url_ingest_source_id=g.video_url_ingest_source_id,
        video_url_ingest_chunks=g.video_url_ingest_chunks,
        video_url_ingest_error=g.video_url_ingest_error,
        video_url_kb_block=g.video_url_kb_block,
        video_url_tidy_status=g.video_url_tidy_status,
        video_url_tidy_model=g.video_url_tidy_model,
        v8_history_used=g.v8_history_used,
        v8_anchor=g.v8_anchor,
        v8_history_anchor_status=g.v8_history_anchor_status,
        retrieved_chunks=g.retrieved_chunks,
    )

    _v13o = pending_flow.run_v13_prepare_commit_phase(
        plan=plan,
        inputs=inputs,
        msg=msg,
        session_id=session_id,
        knowledge_block=knowledge_block,
        lines=lines,
        blocked_failures=blocked_failures,
        save_requested=g.save_requested,
        web_video_pending_early=g.web_video_pending_early,
        document_pending_early=g.document_pending_early,
        early_web_video_url_normalized=_early_norm,
    )
    knowledge_block = _v13o.knowledge_block
    pending_item_obj = _v13o.pending_item_obj
    v13_commit_result_obj = _v13o.v13_commit_result_obj
    v13_material_status = _v13o.v13_material_status
    v13_source_type = _v13o.v13_source_type
    v13_used_pending_text = _v13o.v13_used_pending_text

    _facet = bundle_finalize_flow.finalize_bundle_after_v13(
        lines=lines,
        plan=plan,
        blocked_failures=blocked_failures,
        needs_retrieval_plan=g.needs_retrieval_plan,
        try_rag=g.try_rag,
        knowledge_block=knowledge_block,
        retrieved_chunks=g.retrieved_chunks,
        want_web=g.want_web,
        web_block=g.web_block,
        mcp_video_ok=g.mcp_video_ok,
        mcp_video_source=g.mcp_video_source,
        mcp_video_error=g.mcp_video_error or "",
        web_video_pending_early=g.web_video_pending_early,
        early_web_video_url_normalized=_early_norm,
        pending_item_obj=pending_item_obj,
        mcp_video_pending_item=g.mcp_video_pending_item,
        mcp_video_pending_id=g.mcp_video_pending_id,
        v13_commit_result_obj=v13_commit_result_obj,
        v13_material_status=v13_material_status,
        material_insufficient=g.material_insufficient,
        kb_sufficiency=g.kb_sufficiency,
        v14_trace_info=g.v14_trace_info,
    )

    trace(
        f"MiddleAgentRuntime exec frame={frame.frame_id} intent={g.intent} "
        f"try_rag={g.try_rag} want_web={g.want_web} signal={g.signal} "
        f"video_decision={g.mcp_video_decision} video_ok={g.mcp_video_ok} "
        f"video_pending_id={g.mcp_video_pending_id} "
        f"v11_video_url_decision={g.video_url_decision} "
        f"v11_video_url_ok={bool(g.video_url_result and g.video_url_result.success)} "
        f"v11_video_url_chunks={g.video_url_ingest_chunks} "
        f"v11_video_url_kb_block={'fresh' if g.video_url_kb_block else 'none'} "
        f"v8_history_used={g.v8_history_used} "
        f"v8_followup_anchor={g.v8_anchor.source_id if g.v8_anchor else None} "
        f"v8_history_anchor_status={g.v8_history_anchor_status} "
        f"role_sig={frame.role_signature}"
    )

    critic_check = build_default_chain_critic_check(
        material_sufficiency=_facet.material_sufficiency,
        evidence_envelopes=envelopes,
        failures=_facet.failures,
        force_skip_evidence=bool(getattr(plan, "force_skip_evidence", False)),
    )
    limitations = list(dict.fromkeys(list(critic_check.get("limitations") or [])))

    return AgnoMaterialBundle(
        knowledge_block=knowledge_block,
        web_block=g.web_block,
        trace=lines,
        knowledge_adequate=g.knowledge_adequate,
        material_still_insufficient=g.material_insufficient,
        web_judgment_reason=g.web_reason,
        kb_evidence_tier=g.kb_tier,
        insufficiency_signal=g.signal,
        cailiao_pan=g.cailiao_pan,
        kb_sufficiency_level=(g.kb_sufficiency.level if g.kb_sufficiency is not None else "none"),
        kb_sufficiency_reasons=tuple(g.kb_sufficiency.reason_codes or ()) if g.kb_sufficiency is not None else (),
        retrieved_chunks=g.retrieved_chunks,
        plan_id=_facet.plan_id,
        execution_status=_facet.execution_status,
        tool_calls=_facet.tool_calls,
        temporary_materials=_facet.temporary_materials,
        commit_results=_facet.commit_results,
        failures=_facet.failures,
        material_sufficiency=_facet.material_sufficiency,
        evidence_envelopes=envelopes,
        critic_check=critic_check,
        mcp_video_text=g.mcp_video_text,
        mcp_video_source=g.mcp_video_source,
        mcp_video_path=g.mcp_video_path,
        mcp_video_ok=g.mcp_video_ok,
        mcp_video_error=g.mcp_video_error,
        mcp_video_decision=g.mcp_video_decision,
        mcp_video_ingested=False,
        mcp_video_ingest_source_id=None,
        mcp_video_ingest_chunks=0,
        mcp_video_ingest_error=g.mcp_video_ingest_error,
        mcp_video_pending_id=g.mcp_video_pending_id,
        v8_history_used=g.v8_history_used,
        v8_history_anchor_source_id=(
            g.v8_anchor.source_id if g.v8_anchor is not None else None
        ),
        v8_history_followup_query=g.v8_followup_query,
        v8_history_anchor_status=g.v8_history_anchor_status,
        v8_history_anchor_stale=g.v8_history_anchor_stale,
        v11_pending_video_text=g.pending_video,
        v11_saved_to_kb=_facet.v11_saved_to_kb,
        v11_saved_source_id=_facet.v11_saved_source_id,
        v11_saved_title=_facet.v11_saved_title,
        pending_item=pending_item_obj,
        v13_commit_result=v13_commit_result_obj,
        v13_material_status=v13_material_status,
        v13_source_type=v13_source_type,
        v13_used_pending_text=v13_used_pending_text,
        answer_limitations=limitations,
    )
