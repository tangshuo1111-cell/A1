"""台账 G-005「gather_phase」：Middle gather 阶段（由 `invoke_executor` 经 mixin 调用）。

意图识别 → try_rag / needs_retrieval 收紧 → 网页视频 URL early fetch →
V8 前文锚点 → KB 检索聚块 → Web 取证 → `pan_zhuyao_panjue` / `pan_shibai_bianjie` /
`qingxi_yueshu_doudi`（方法与实现在 `judgment_phase`）→ MCP 本地视频 pending。

以 `MiddleGatherPhaseMixin._middle_invoke_gather_phase` 挂到 `MiddleAgentRuntime`，
保留原有实例方法委托语义。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.main_agent import AgnoCollaborationPlan
from agents.shared.history_context import PendingVideoText, PrevVideoRef, SessionHistorySnapshot
from application.chat.budget_clock import BudgetClock
from application.chat.chat_contracts import KbSufficiencyResult
from schemas import MainDecision
from services.capabilities.web import web_orchestration_service as agno_web_service

from . import coordinator, video_flow
from .material_policy import _extract_mp4_path_from_message, _is_tool_allowed
from .schema import CailiaoPan


@dataclass(frozen=True)
class MiddleGatherPhaseOutcome:
    intent: str
    try_rag: bool
    needs_retrieval_plan: Any
    video_url_yitu: dict[str, Any]
    video_url_from: str
    video_url_decision: str
    video_url_result: Any | None
    video_url_ingest_source_id: str | None
    video_url_ingest_chunks: int
    video_url_ingest_error: str
    video_url_kb_block: str | None
    video_url_tidy_status: str
    video_url_tidy_model: str
    pending_video: PendingVideoText | None
    save_requested: bool
    early_web_video_url_normalized: str
    web_video_pending_early: Any | None
    document_pending_early: Any | None
    document_prepare_error: str
    v8_anchor: PrevVideoRef | None
    v8_followup_query: str
    v8_history_used: bool
    knowledge_block: str | None
    retrieved_chunks: list[Any]
    v8_history_anchor_status: str
    v14_trace_info: dict[str, Any] | None
    v8_history_anchor_stale: bool
    want_web: bool
    web_reason: str
    web_block: str | None
    cailiao_pan: CailiaoPan
    material_insufficient: bool
    signal: str
    knowledge_adequate: bool
    kb_tier: str
    kb_sufficiency: KbSufficiencyResult | None
    video_yitu: dict[str, Any]
    mcp_video_decision: str
    mcp_video_text: str | None
    mcp_video_source: str | None
    mcp_video_path: str | None
    mcp_video_ok: bool
    mcp_video_error: str
    mcp_video_pending_id: str | None
    mcp_video_ingest_error: str
    mcp_video_pending_item: Any | None


class MiddleGatherPhaseMixin:
    """供 `MiddleAgentRuntime` 多重继承；仅实现 gather 阶段。"""

    def _middle_invoke_gather_phase(
        self,
        *,
        message: str,
        msg: str,
        plan: AgnoCollaborationPlan,
        shared_prep: Any | None,
        http_use_knowledge: bool,
        history: SessionHistorySnapshot | None,
        decision: MainDecision,
        session_id: str,
        blocked_failures: list[dict[str, Any]],
        fetch_video_text_fn: Any,
        v13_file_content: str | bytes | None = None,
        budget_clock: BudgetClock,
    ) -> MiddleGatherPhaseOutcome:
        intent = self.shibie_yitu(
            message=message,
            http_use_knowledge=http_use_knowledge,
            plan=plan,
        )
        try_rag = self.pan_jubu_celue_kb(intent=intent, plan=plan, decision=decision)

        _needs_retrieval_plan = getattr(plan, "needs_retrieval", None)
        if _needs_retrieval_plan is False:
            try_rag = False

        video_url_yitu, video_url_from = self.video_url_yitu_from_plan_or_message(
            plan=plan, message=message
        )
        video_url_decision = self.pan_jubu_celue_video_url(video_url_yitu=video_url_yitu)
        video_url_result = None
        video_url_ingest_source_id: str | None = None
        video_url_ingest_chunks = 0
        video_url_ingest_error = ""
        video_url_kb_block: str | None = None
        video_url_tidy_status: str = "skip"
        video_url_tidy_model: str = ""
        pending_video: PendingVideoText | None = None
        save_requested = self.shibie_save_to_kb_yitu(message=message)

        own_mp4_in_message = _extract_mp4_path_from_message(message) is not None
        own_video_url_in_message = bool(video_url_yitu.get("has_video_url"))
        v8_anchor, v8_followup_query = self.pan_history_followup(
            message=message,
            history=history,
            own_mp4_in_message=own_mp4_in_message or own_video_url_in_message,
        )
        v8_history_used = v8_anchor is not None

        video_yitu, mcp_video_decision = video_flow.resolve_mcp_video_decision(
            message=message,
            plan=plan,
        )

        parallel = coordinator.run_parallel_gather_workers(
            try_rag=try_rag,
            msg=msg,
            plan=plan,
            shared_prep=shared_prep,
            v8_history_used=v8_history_used,
            v8_anchor=v8_anchor,
            v8_followup_query=v8_followup_query,
            video_url_decision=video_url_decision,
            video_url_yitu=video_url_yitu,
            mcp_video_decision=mcp_video_decision,
            video_yitu=video_yitu,
            session_id=session_id,
            fetch_video_text_fn=fetch_video_text_fn,
            file_content=v13_file_content,
            clock=budget_clock,
        )
        blocked_failures.extend(parallel.failures)

        early_web_video_url_normalized = parallel.web_video.early_web_video_url_normalized
        web_video_pending_early = parallel.web_video.web_video_pending_early
        document_pending_early = parallel.document.pending_item_early
        document_prepare_error = parallel.document.error_code
        video_url_result = parallel.web_video.video_url_result
        video_url_kb_block = parallel.web_video.video_url_kb_block
        video_url_ingest_error = parallel.web_video.video_url_ingest_error

        knowledge_block = parallel.kb.knowledge_block
        retrieved_chunks = parallel.kb.retrieved_chunks
        v8_history_anchor_status = parallel.kb.v8_history_anchor_status
        v14_trace_info = parallel.kb.v14_trace_info
        kb_sufficiency = parallel.kb.kb_sufficiency
        v8_history_anchor_stale = v8_history_anchor_status == "stale"

        want_web, web_reason = self.pan_jubu_celue_web(
            intent=intent,
            plan=plan,
            message=message,
            http_use_knowledge=http_use_knowledge,
            knowledge_block=knowledge_block,
        )

        web_block: str | None = None
        if coordinator.should_fetch_web_after_kb(
            want_web=want_web,
            knowledge_block=knowledge_block,
            http_use_knowledge=http_use_knowledge,
        ):
            if not _is_tool_allowed(plan, "fetch_web"):
                blocked_failures.append({
                    "tool": "fetch_web",
                    "reason": "not_allowed_by_plan",
                    "recoverable": False,
                })
            else:
                wb = agno_web_service.fetch_web_evidence_block(msg)
                web_block = wb if wb else None

        cailiao_pan = self.pan_zhuyao_panjue(
            intent=intent,
            message=message,
            try_rag=try_rag,
            knowledge_block=knowledge_block,
            web_block=web_block,
        )
        material_insufficient, signal, knowledge_adequate, kb_tier = self.pan_shibai_bianjie(
            intent=intent,
            cailiao_pan=cailiao_pan,
            try_rag=try_rag,
            knowledge_block=knowledge_block,
            web_block=web_block,
            http_use_knowledge=http_use_knowledge,
            kb_sufficiency=kb_sufficiency,
        )
        cailiao_pan = self.qingxi_yueshu_doudi(
            cailiao_pan=cailiao_pan,
            plan=plan,
            http_use_knowledge=http_use_knowledge,
        )

        return MiddleGatherPhaseOutcome(
            intent=intent,
            try_rag=try_rag,
            needs_retrieval_plan=_needs_retrieval_plan,
            video_url_yitu=video_url_yitu,
            video_url_from=video_url_from,
            video_url_decision=video_url_decision,
            video_url_result=video_url_result,
            video_url_ingest_source_id=video_url_ingest_source_id,
            video_url_ingest_chunks=video_url_ingest_chunks,
            video_url_ingest_error=video_url_ingest_error,
            video_url_kb_block=video_url_kb_block,
            video_url_tidy_status=video_url_tidy_status,
            video_url_tidy_model=video_url_tidy_model,
            pending_video=pending_video,
            save_requested=save_requested,
            early_web_video_url_normalized=early_web_video_url_normalized,
            web_video_pending_early=web_video_pending_early,
            document_pending_early=document_pending_early,
            document_prepare_error=document_prepare_error,
            v8_anchor=v8_anchor,
            v8_followup_query=v8_followup_query,
            v8_history_used=v8_history_used,
            knowledge_block=knowledge_block,
            retrieved_chunks=retrieved_chunks,
            v8_history_anchor_status=v8_history_anchor_status,
            v14_trace_info=v14_trace_info,
            v8_history_anchor_stale=v8_history_anchor_stale,
            want_web=want_web,
            web_reason=web_reason,
            web_block=web_block,
            cailiao_pan=cailiao_pan,
            material_insufficient=material_insufficient,
            signal=signal,
            knowledge_adequate=knowledge_adequate,
            kb_tier=kb_tier,
            kb_sufficiency=kb_sufficiency,
            video_yitu=video_yitu,
            mcp_video_decision=mcp_video_decision,
            mcp_video_text=parallel.mcp_video.mcp_video_text,
            mcp_video_source=parallel.mcp_video.mcp_video_source,
            mcp_video_path=parallel.mcp_video.mcp_video_path,
            mcp_video_ok=parallel.mcp_video.mcp_video_ok,
            mcp_video_error=parallel.mcp_video.mcp_video_error or "",
            mcp_video_pending_id=parallel.mcp_video.mcp_video_pending_id,
            mcp_video_ingest_error=parallel.mcp_video.mcp_video_ingest_error or "",
            mcp_video_pending_item=parallel.mcp_video.mcp_video_pending_item,
        )
