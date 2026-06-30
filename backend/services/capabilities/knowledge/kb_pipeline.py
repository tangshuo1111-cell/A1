"""KB unified pipeline — retrieve → rerank → grounding for fast/complex lanes."""

from __future__ import annotations

import time
from typing import Any, cast

from rag.schema import RetrievedChunk
from services.capabilities.contracts import CapabilityAdvice, CapabilityFact, QualityLevel

from . import grounding_service, rerank_service, retrieve_service

KB_FAST_CAPABILITIES = (
    "capability.kb.retrieve",
    "capability.kb.rerank",
    "capability.kb.grounding",
)

_KB_LOW_SCORE_THRESHOLD = 0.25


def _retrieve_knowledge_cached(
    query: str,
    *,
    top_k: int,
    strategy: str,
    filters: dict[str, str] | None,
    turn_cache: Any | None = None,
) -> tuple[list[RetrievedChunk], dict[str, Any]]:
    if turn_cache is None:
        return retrieve_service.retrieve_knowledge(
            query,
            top_k=top_k,
            strategy=strategy,
            filters=filters,
        )
    cache_key = f"kb_retrieve:{query}:{top_k}:{strategy}:{filters or {}}"
    return turn_cache.get_or_compute(
        cache_key,
        lambda: retrieve_service.retrieve_knowledge(
            query,
            top_k=top_k,
            strategy=strategy,
            filters=filters,
        ),
        lane="kb",
    )


def _chunk_top_score(chunks: list[RetrievedChunk]) -> float:
    if not chunks:
        return 0.0
    return max(
        float(getattr(chunk, "combined_score", 0.0) or getattr(chunk, "score_normalized", 0.0) or chunk.score)
        for chunk in chunks
    )


def _evidence_tier(*, hits: int, top_score: float) -> str:
    if hits <= 0:
        return "none"
    if top_score >= 0.6:
        return "strong"
    if top_score >= _KB_LOW_SCORE_THRESHOLD:
        return "usable"
    return "weak"


def _quality_from_hits(*, hits: int, top_score: float) -> str:
    if hits <= 0:
        return "empty"
    if top_score >= _KB_LOW_SCORE_THRESHOLD:
        return "good" if top_score >= 0.6 else "usable"
    return "poor"


def probe_kb_capability(
    query: str,
    clock: Any | None = None,
    *,
    top_k: int = 4,
    strategy: str = "auto",
    filters: dict[str, str] | None = None,
    turn_cache: Any | None = None,
) -> tuple[CapabilityFact, CapabilityAdvice, list[RetrievedChunk], dict[str, Any]]:
    """Probe KB retrieve viability; returns facts + advice + raw chunks (§7.4 / K1)."""
    del clock
    started = time.perf_counter()
    chunks, trace_info = _retrieve_knowledge_cached(
        query,
        top_k=top_k,
        strategy=strategy,
        filters=filters,
        turn_cache=turn_cache,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    hits = len(chunks)
    top_score = _chunk_top_score(chunks)
    evidence_tier = _evidence_tier(hits=hits, top_score=top_score)
    quality_level = _quality_from_hits(hits=hits, top_score=top_score)

    if hits <= 0:
        advice = CapabilityAdvice(
            suggested_mode="needs_user_confirm",
            reason="kb_no_hits",
            next_action_hint="知识库无命中，建议走 complex 补检索或换策略。",
        )
    elif quality_level == "poor":
        advice = CapabilityAdvice(
            suggested_mode="needs_user_confirm",
            reason="kb_low_score",
            next_action_hint="知识库命中分数偏低，建议 complex 路径复核。",
        )
    else:
        advice = CapabilityAdvice(
            suggested_mode="sync_ok",
            reason="kb_hits_ok",
            next_action_hint="可继续 fast KB 摘要。",
        )

    fact = CapabilityFact(
        lane="kb",
        probe_elapsed_ms=elapsed_ms,
        quality_level=cast(QualityLevel, quality_level),
        metadata={
            "hits": hits,
            "top_score": top_score,
            "evidence_tier": evidence_tier,
            "retrieve_strategy": strategy,
            "retrieval_trace": trace_info,
        },
    )
    return fact, advice, chunks, trace_info


def fetch_kb_answer_material(
    query: str,
    *,
    top_k: int = 4,
    strategy: str = "auto",
    filters: dict[str, str] | None = None,
    turn_cache: Any | None = None,
) -> tuple[str, list[RetrievedChunk], list[str], dict[str, Any]]:
    chunks, trace_info = _retrieve_knowledge_cached(
        query,
        top_k=top_k,
        strategy=strategy,
        filters=filters,
        turn_cache=turn_cache,
    )
    ranked = rerank_service.rerank_chunks(chunks, top_k=top_k)
    material = grounding_service.chunks_to_context_block(ranked)
    return material, ranked, list(KB_FAST_CAPABILITIES), trace_info


def fetch_kb_answer_material_from_probe(
    chunks: list[RetrievedChunk],
    trace_info: dict[str, Any],
    *,
    top_k: int = 4,
) -> tuple[str, list[RetrievedChunk], list[str], dict[str, Any]]:
    ranked = rerank_service.rerank_chunks(chunks, top_k=top_k)
    material = grounding_service.chunks_to_context_block(ranked)
    capabilities = list(KB_FAST_CAPABILITIES)
    if "capability.kb.probe" not in capabilities:
        capabilities.insert(0, "capability.kb.probe")
    return material, ranked, capabilities, trace_info
