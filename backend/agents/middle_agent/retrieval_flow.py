"""台账 G-005「retrieval_flow」：Middle gather 内 KB 检索聚块。

承接 V8 前文锚点 `source_all` 与 V14/V15 普通 `retrieve_knowledge` 路径，
产出 `knowledge_block` / `retrieved_chunks` / 锚点状态 / trace 信息。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.shared.history_context import PrevVideoRef
from agents.main_agent import AgnoCollaborationPlan
from application.chat.chat_contracts import KbSufficiencyResult
from services.capabilities.knowledge import retrieve_service as _retrieve_svc

from .material_policy import _is_tool_allowed


@dataclass(frozen=True)
class KbRetrievalGatherOutcome:
    knowledge_block: str | None
    retrieved_chunks: list[Any]
    v8_history_anchor_status: str
    v14_trace_info: dict[str, Any] | None
    kb_sufficiency: KbSufficiencyResult | None


def run_kb_retrieval_gather(
    *,
    try_rag: bool,
    msg: str,
    plan: AgnoCollaborationPlan,
    v8_history_used: bool,
    v8_anchor: PrevVideoRef | None,
    v8_followup_query: str,
    blocked_failures: list[dict[str, Any]],
) -> KbRetrievalGatherOutcome:
    knowledge_block: str | None = None
    v8_history_anchor_status = "none"
    retrieved_chunks: list[Any] = []
    v14_trace_info: dict[str, Any] | None = None

    if not try_rag:
        return KbRetrievalGatherOutcome(
            knowledge_block=None,
            retrieved_chunks=[],
            v8_history_anchor_status="none",
            v14_trace_info=None,
            kb_sufficiency=None,
        )

    kb = ""
    if v8_history_used and v8_anchor is not None:
        _sid_anchor = str(getattr(v8_anchor, "source_id", "") or "").strip()
        if not _sid_anchor:
            blocked_failures.append({
                "tool": "retrieve_knowledge",
                "reason": "source_all_missing_anchor_source_id",
                "recoverable": False,
            })
            chunks_by_sid_result = []
            v8_source_all_trace = {
                "strategy_requested": "source_all",
                "strategy_used": "source_all",
                "hits": 0,
                "no_match": True,
                "failure_reason": "source_all_missing_anchor_source_id",
                "filters_applied": {},
            }
        else:
            _v8_filters = {"source_id": _sid_anchor}
            chunks_by_sid_result, v8_source_all_trace = _retrieve_svc.retrieve_knowledge(
                v8_followup_query or msg,
                top_k=5,
                strategy="source_all",
                filters=_v8_filters,
            )
        if chunks_by_sid_result:
            retrieved_chunks = list(chunks_by_sid_result)
            kb = "\n\n---\n\n".join(c.to_context_line() for c in chunks_by_sid_result)
            v8_history_anchor_status = "fresh"
        else:
            v8_history_anchor_status = "stale"
            kb = ""
        v14_trace_info = v8_source_all_trace
    else:
        if not _is_tool_allowed(plan, "retrieve_knowledge"):
            kb = ""
            blocked_failures.append({
                "tool": "retrieve_knowledge",
                "reason": "not_allowed_by_plan",
                "recoverable": False,
            })
        else:
            _retrieval_strategy = getattr(plan, "retrieval_strategy", "auto") or "auto"
            _retrieval_filters = getattr(plan, "retrieval_filters", None) or {}
            chunks_by_query_result, v14_trace_info = _retrieve_svc.retrieve_knowledge(
                msg, top_k=5, strategy=_retrieval_strategy, filters=_retrieval_filters
            )
            chunks_by_query = chunks_by_query_result
            if chunks_by_query:
                retrieved_chunks = list(chunks_by_query)
                kb = "\n\n---\n\n".join(c.to_context_line() for c in chunks_by_query)
            else:
                kb = ""

    knowledge_block = kb if kb else None
    return KbRetrievalGatherOutcome(
        knowledge_block=knowledge_block,
        retrieved_chunks=retrieved_chunks,
        v8_history_anchor_status=v8_history_anchor_status,
        v14_trace_info=v14_trace_info,
        kb_sufficiency=None,
    )
