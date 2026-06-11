"""Knowledge capability bridge for Middle gather retrieval.

Owns KB retrieval gather so agent-layer code does not import retrieval helpers
that themselves depend on knowledge/retrieval internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.main_agent import AgnoCollaborationPlan
from agents.shared.history_context import PrevVideoRef
from application.chat.chat_contracts import KbSufficiencyResult, RetrievalSnapshot
from config.feature_flags import shared_retrieval_active
from services.capabilities.knowledge import retrieve_service as _retrieve_svc
from services.capabilities.knowledge.kb_sufficiency import evaluate_kb_sufficiency, tier_from_score


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
    shared_prep: Any | None,
    v8_history_used: bool,
    v8_anchor: PrevVideoRef | None,
    v8_followup_query: str,
    blocked_failures: list[dict[str, Any]],
    is_tool_allowed: Any,
) -> KbRetrievalGatherOutcome:
    knowledge_block: str | None = None
    v8_history_anchor_status = "none"
    retrieved_chunks: list[Any] = []
    v14_trace_info: dict[str, Any] | None = None
    kb_sufficiency: KbSufficiencyResult | None = None

    if not try_rag:
        return KbRetrievalGatherOutcome(
            knowledge_block=None,
            retrieved_chunks=[],
            v8_history_anchor_status="none",
            v14_trace_info=None,
            kb_sufficiency=None,
        )

    if shared_retrieval_active() and not v8_history_used:
        from services.capabilities.knowledge.grounding_service import chunks_to_context_block

        prep = shared_prep
        if (
            prep is not None
            and not prep.supplementary_retrieve
            and prep.snapshot is not None
            and prep.snapshot.chunks
        ):
            knowledge_block = prep.knowledge_block or chunks_to_context_block(list(prep.snapshot.chunks))
            return KbRetrievalGatherOutcome(
                knowledge_block=knowledge_block or None,
                retrieved_chunks=list(prep.snapshot.chunks),
                v8_history_anchor_status="shared_snapshot",
                v14_trace_info=dict(prep.snapshot.trace_info),
                kb_sufficiency=prep.kb_sufficiency,
            )

    kb = ""
    if v8_history_used and v8_anchor is not None:
        anchor_source_id = str(getattr(v8_anchor, "source_id", "") or "").strip()
        if not anchor_source_id:
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
            retrieval_filters = {"source_id": anchor_source_id}
            chunks_by_sid_result, v8_source_all_trace = _retrieve_svc.retrieve_knowledge(
                v8_followup_query or msg,
                top_k=5,
                strategy="source_all",
                filters=retrieval_filters,
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
        if not is_tool_allowed(plan, "retrieve_knowledge"):
            kb = ""
            blocked_failures.append({
                "tool": "retrieve_knowledge",
                "reason": "not_allowed_by_plan",
                "recoverable": False,
            })
        else:
            retrieval_strategy = getattr(plan, "retrieval_strategy", "auto") or "auto"
            retrieval_filters = getattr(plan, "retrieval_filters", None) or {}
            chunks_by_query_result, v14_trace_info = _retrieve_svc.retrieve_knowledge(
                msg, top_k=5, strategy=retrieval_strategy, filters=retrieval_filters
            )
            if chunks_by_query_result:
                retrieved_chunks = list(chunks_by_query_result)
                kb = "\n\n---\n\n".join(c.to_context_line() for c in chunks_by_query_result)
            else:
                kb = ""

    knowledge_block = kb if kb else None
    trace_payload = dict(v14_trace_info or {})
    hits = len(retrieved_chunks)
    top_score = max((float(getattr(chunk, "score", 0.0) or 0.0) for chunk in retrieved_chunks), default=0.0)
    snapshot = RetrievalSnapshot(
        chunks=tuple(retrieved_chunks),
        hits=hits,
        top_score=top_score,
        evidence_tier=tier_from_score(hits=hits, top_score=top_score),
        strategy_requested=str(trace_payload.get("strategy_requested") or "auto"),
        strategy_used=str(trace_payload.get("strategy_used") or trace_payload.get("strategy_requested") or "auto"),
        rag_miss=hits <= 0,
        trace_info=trace_payload,
    )
    kb_sufficiency = evaluate_kb_sufficiency(snapshot, complex_candidate=True)
    return KbRetrievalGatherOutcome(
        knowledge_block=knowledge_block,
        retrieved_chunks=retrieved_chunks,
        v8_history_anchor_status=v8_history_anchor_status,
        v14_trace_info=v14_trace_info,
        kb_sufficiency=kb_sufficiency,
    )
