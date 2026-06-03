"""Shared KB retrieval before executor profiles — single snapshot per turn."""

from __future__ import annotations

import time
from typing import Any

from application.chat.chat_contracts import (
    RetrievalSnapshot,
    SharedMaterialPrepResult,
)
from application.chat.turn_cache import current_turn_cache
from config.feature_flags import shared_retrieval_active
from services.capabilities.knowledge import kb_sufficiency as kb_suff_svc
from services.capabilities.knowledge.kb_pipeline import (
    fetch_kb_answer_material_from_probe,
    probe_kb_capability,
)

_SHARED_CACHE_KEY = "shared_material_prep"


def _kb_in_scope(*, lane: str, use_knowledge: bool, message: str) -> bool:
    if use_knowledge or lane == "kb":
        return True
    lower = (message or "").lower()
    return any(token in lower for token in ("知识库", "样例", "rag", "资料库"))


def load_shared_prep_from_cache() -> SharedMaterialPrepResult | None:
    cache = current_turn_cache()
    if cache is None:
        return None
    item = cache.get(_SHARED_CACHE_KEY, lane="kb")
    return item if isinstance(item, SharedMaterialPrepResult) else None


def _store_shared_prep(result: SharedMaterialPrepResult) -> None:
    cache = current_turn_cache()
    if cache is not None:
        cache.set(_SHARED_CACHE_KEY, result, lane="kb")


def run_shared_material_prep(
    *,
    message: str,
    lane: str,
    use_knowledge: bool,
    complex_candidate: bool,
    clock: Any | None = None,
    supplementary_retrieve: bool = False,
) -> SharedMaterialPrepResult | None:
    if not shared_retrieval_active():
        return None
    if not _kb_in_scope(lane=lane, use_knowledge=use_knowledge, message=message):
        return None

    if not supplementary_retrieve:
        existing = load_shared_prep_from_cache()
        if existing is not None and not existing.supplementary_retrieve:
            return existing

    started = time.perf_counter()
    turn_cache = current_turn_cache()
    retrieve_cache = None if supplementary_retrieve else turn_cache
    top_k = 8 if supplementary_retrieve else 4
    fact, advice, chunks, trace_info = probe_kb_capability(
        message,
        clock=clock,
        top_k=top_k,
        turn_cache=retrieve_cache,
    )
    material, ranked, capabilities, trace_info = fetch_kb_answer_material_from_probe(
        chunks,
        trace_info,
    )
    hits = len(ranked)
    top_score = float(fact.metadata.get("top_score") or 0.0)
    tier = kb_suff_svc.tier_from_score(hits=hits, top_score=top_score)
    strategy_used = str(trace_info.get("strategy_used") or trace_info.get("strategy_requested") or "auto")
    snapshot = RetrievalSnapshot(
        chunks=tuple(ranked),
        hits=hits,
        top_score=top_score,
        evidence_tier=tier,
        strategy_requested=str(trace_info.get("strategy_requested") or "auto"),
        strategy_used=strategy_used,
        rag_miss=hits <= 0,
        trace_info=dict(trace_info),
    )
    kb_result = kb_suff_svc.evaluate_kb_sufficiency(snapshot, complex_candidate=complex_candidate)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    result = SharedMaterialPrepResult(
        snapshot=snapshot,
        kb_sufficiency=kb_result,
        knowledge_block=material if material else None,
        material_text=material if material else None,
        capabilities_called=tuple(capabilities),
        trace_extra={
            "shared_retrieval_ms": elapsed_ms,
            "shared_retrieval_supplementary": supplementary_retrieve,
            "strategy_requested": snapshot.strategy_requested,
            "strategy_used": snapshot.strategy_used,
            "kb_sufficiency_level": kb_result.level,
            "kb_hits": hits,
            "kb_top_score": top_score,
            "kb_evidence_tier": tier,
            "capability_fact": fact,
            "capability_advice": advice,
            "v14_retrieval_trace": trace_info,
        },
        supplementary_retrieve=supplementary_retrieve,
    )
    _store_shared_prep(result)
    return result


def shared_prep_trace_extra(prep: SharedMaterialPrepResult | None) -> dict[str, Any]:
    if prep is None:
        return {}
    extra = dict(prep.trace_extra)
    if prep.kb_sufficiency is not None:
        extra["kb_sufficiency_level"] = prep.kb_sufficiency.level
    return extra
