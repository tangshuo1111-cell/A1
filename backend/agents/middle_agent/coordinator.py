"""Middle coordinator：前置上下文阶段之后的并发取材编排。

职责边界：
- 不产出最终 `CailiaoPan` / `AgnoMaterialBundle`
- 只负责编排可独立取材的 worker，并把结果交回 gather/judgment 阶段
- `Memory`/history 不在这里并发，仍属于前置上下文阶段
"""

from __future__ import annotations

import contextvars
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from agents.main_agent import AgnoCollaborationPlan
from agents.shared.history_context import PrevVideoRef
from application.chat.budget_allocator import WorkerSpec, allocate_parallel_budgets
from application.chat.budget_clock import BudgetClock, SkippedForBudget
from config.feature_flags import is_enabled
from config.settings import settings
from services.capabilities.knowledge.middle_retrieval_gather import (
    KbRetrievalGatherOutcome,
    run_kb_retrieval_gather,
)

from . import video_flow
from .material_policy import _is_tool_allowed


@dataclass(frozen=True)
class ParallelGatherResult:
    kb: KbRetrievalGatherOutcome
    web_video: video_flow.EarlyWebVideoOutcome
    mcp_video: video_flow.McpVideoPendingOutcome
    document: video_flow.EarlyDocumentOutcome
    failures: list[dict[str, Any]] = field(default_factory=list)
    budget_allocations: dict[str, int] = field(default_factory=dict)


def _default_worker_specs(*, try_rag: bool) -> list[WorkerSpec]:
    probe_ms = int(getattr(settings, "v16_video_probe_budget_ms", 6000) or 6000)
    workers = [
        WorkerSpec(name="web_video", priority=3, default_cap_ms=probe_ms),
        WorkerSpec(name="mcp_video", priority=3, default_cap_ms=probe_ms),
        WorkerSpec(name="document", priority=2, default_cap_ms=probe_ms),
    ]
    if try_rag:
        workers.append(WorkerSpec(name="kb", priority=2, default_cap_ms=8000))
    return workers


def _skipped_outcome(worker: str) -> dict[str, Any]:
    return {
        "worker": worker,
        "outcome": "skipped_budget",
        "reason": "parallel_budget_zero",
    }


def run_parallel_gather_workers(
    *,
    try_rag: bool,
    msg: str,
    plan: AgnoCollaborationPlan,
    shared_prep: Any | None,
    v8_history_used: bool,
    v8_anchor: PrevVideoRef | None,
    v8_followup_query: str,
    video_url_decision: str,
    video_url_yitu: dict[str, Any],
    mcp_video_decision: str,
    video_yitu: dict[str, Any],
    session_id: str,
    fetch_video_text_fn: Any,
    file_content: str | bytes | None,
    clock: BudgetClock,
) -> ParallelGatherResult:
    """并发运行最独立的取材块。

    当前并发范围：
    - KB retrieval
    - web video subtitle / pending early fetch
    - local video mcp pending

    注意：普通 Web fetch 仍不在这里并发，它依赖 KB 结果后的条件判断。
    """
    budgets: dict[str, int] = {}
    use_budget = is_enabled("ENABLE_BUDGET_CLOCK_V2")
    kb_required = bool(
        try_rag
        and str(getattr(plan, "answer_mode", "") or "") == "knowledge_grounded"
        and bool(_is_tool_allowed(plan, "retrieve_knowledge"))
    )
    if use_budget:
        budgets = allocate_parallel_budgets(clock, _default_worker_specs(try_rag=try_rag))

    failures: list[dict[str, Any]] = []
    kb_snapshot_ready = bool(
        shared_prep is not None
        and not getattr(shared_prep, "supplementary_retrieve", False)
        and getattr(getattr(shared_prep, "snapshot", None), "chunks", ())
        and not v8_history_used
    )

    def _run_web_video() -> tuple[video_flow.EarlyWebVideoOutcome, list[dict[str, Any]]]:
        if use_budget and budgets.get("web_video", 1) <= 0:
            raise SkippedForBudget(worker="web_video")
        local_failures: list[dict[str, Any]] = []
        out = video_flow.run_video_probe_stage(
            video_url_decision=video_url_decision,
            video_url_yitu=video_url_yitu,
            plan=plan,
            session_id=session_id,
            blocked_failures=local_failures,
            fetch_video_text_fn=fetch_video_text_fn,
        )
        return out, local_failures

    def _run_kb() -> tuple[KbRetrievalGatherOutcome, list[dict[str, Any]]]:
        if not try_rag:
            return KbRetrievalGatherOutcome(
                knowledge_block=None,
                retrieved_chunks=[],
                v8_history_anchor_status="none",
                v14_trace_info=None,
                kb_sufficiency=None,
            ), []
        # Shared snapshot has already paid the retrieval cost on the main thread;
        # consuming it inside the worker should not be blocked by a zero worker budget.
        if use_budget and budgets.get("kb", 1) <= 0 and not kb_snapshot_ready and not kb_required:
            raise SkippedForBudget(worker="kb")
        local_failures: list[dict[str, Any]] = []
        out = run_kb_retrieval_gather(
            try_rag=try_rag,
            msg=msg,
            plan=plan,
            shared_prep=shared_prep,
            v8_history_used=v8_history_used,
            v8_anchor=v8_anchor,
            v8_followup_query=v8_followup_query,
            blocked_failures=local_failures,
            is_tool_allowed=_is_tool_allowed,
        )
        return out, local_failures

    def _run_mcp_video() -> tuple[video_flow.McpVideoPendingOutcome, list[dict[str, Any]]]:
        if use_budget and budgets.get("mcp_video", 1) <= 0:
            raise SkippedForBudget(worker="mcp_video")
        local_failures: list[dict[str, Any]] = []
        out = video_flow.run_mcp_video_tool_and_pending(
            mcp_video_decision=mcp_video_decision,
            video_yitu=video_yitu,
            plan=plan,
            session_id=session_id,
            blocked_failures=local_failures,
        )
        return out, local_failures

    def _run_document() -> tuple[video_flow.EarlyDocumentOutcome, list[dict[str, Any]]]:
        if use_budget and budgets.get("document", 1) <= 0:
            raise SkippedForBudget(worker="document")
        local_failures: list[dict[str, Any]] = []
        out = video_flow.run_early_document_prepare_flow(
            plan=plan,
            session_id=session_id,
            file_content=file_content,
            blocked_failures=local_failures,
        )
        return out, local_failures

    def _safe_result(name: str, fn: Any, default: Any) -> tuple[Any, list[dict[str, Any]]]:
        try:
            return fn()
        except SkippedForBudget as exc:
            failures.append(_skipped_outcome(exc.worker or name))
            return default, []

    kb_default = KbRetrievalGatherOutcome(
        knowledge_block=None,
        retrieved_chunks=[],
        v8_history_anchor_status="none",
        v14_trace_info=None,
        kb_sufficiency=None,
    )
    web_default = video_flow.EarlyWebVideoOutcome()
    mcp_default = video_flow.McpVideoPendingOutcome()
    doc_default = video_flow.EarlyDocumentOutcome()

    def _submit_with_context(fn: Any) -> Any:
        ctx = contextvars.copy_context()
        return pool.submit(lambda: ctx.run(fn))

    with ThreadPoolExecutor(max_workers=4) as pool:
        web_video_future = _submit_with_context(lambda: _safe_result("web_video", _run_web_video, web_default))
        kb_future = _submit_with_context(lambda: _safe_result("kb", _run_kb, kb_default))
        mcp_video_future = _submit_with_context(lambda: _safe_result("mcp_video", _run_mcp_video, mcp_default))
        document_future = _submit_with_context(lambda: _safe_result("document", _run_document, doc_default))

        web_video, web_video_failures = web_video_future.result()
        kb, kb_failures = kb_future.result()
        mcp_video, mcp_video_failures = mcp_video_future.result()
        document, document_failures = document_future.result()

    failures.extend([*web_video_failures, *kb_failures, *mcp_video_failures, *document_failures])
    return ParallelGatherResult(
        kb=kb,
        web_video=web_video,
        mcp_video=mcp_video,
        document=document,
        failures=failures,
        budget_allocations=budgets,
    )


def should_fetch_web_after_kb(
    *,
    want_web: bool,
    knowledge_block: str | None,
    http_use_knowledge: bool,
) -> bool:
    """普通 Web fetch 的条件触发边界。

    KB 未命中且用户显式要 web / 外部意图时才继续 web fetch。
    """
    if not want_web:
        return False
    return not (http_use_knowledge and (knowledge_block or "").strip())
