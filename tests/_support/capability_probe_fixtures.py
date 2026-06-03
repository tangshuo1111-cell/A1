"""Shared CapabilityFact probe fixtures for fast-lane migration/integration tests."""

from __future__ import annotations

from typing import Any

from rag.schema import RetrievedChunk
from services.capabilities.contracts import CapabilityAdvice, CapabilityFact


def kb_probe_sync_ok(
    *,
    url: str = "",
) -> tuple[CapabilityFact, CapabilityAdvice, list[RetrievedChunk], dict[str, Any]]:
    del url
    chunks = [
        RetrievedChunk(
            source_id="sample",
            chunk_id="sample::0",
            text="系统默认数据库要求 PostgreSQL。",
            metadata={"source_type": "document"},
            score=0.9,
            retrieval_strategy="keyword",
        ),
    ]
    trace = {"strategy_used": "keyword", "hits": 1}
    fact = CapabilityFact(
        lane="kb",
        probe_elapsed_ms=1,
        quality_level="good",
        metadata={"hits": 1, "top_score": 0.9, "evidence_tier": "strong", "retrieval_trace": trace},
    )
    advice = CapabilityAdvice(
        suggested_mode="sync_ok",
        reason="kb_hits_ok",
        next_action_hint="可继续 fast KB 摘要。",
    )
    return fact, advice, chunks, trace


def web_probe_sync_ok(
    url: str,
) -> tuple[CapabilityFact, CapabilityAdvice]:
    fact = CapabilityFact(
        lane="web",
        probe_elapsed_ms=1,
        dynamic_required=False,
        cookie_required=False,
        quality_level="good",
        metadata={"url": url, "text_length": 400, "static_fetch_ok": True},
    )
    advice = CapabilityAdvice(
        suggested_mode="sync_ok",
        reason="static_fetch_ok",
        next_action_hint="可继续 fast 静态摘要。",
    )
    return fact, advice
