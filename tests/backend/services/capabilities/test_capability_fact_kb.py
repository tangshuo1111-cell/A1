"""S6b — KB capability contract when ENABLE_CAPABILITY_FACT_KB is on."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from application.chat.budget_clock import BudgetClock
from config import feature_flags
from rag.schema import RetrievedChunk
from services.capabilities.contracts import CapabilityAdvice, CapabilityFact
from services.capabilities.knowledge import kb_pipeline


@pytest.fixture
def enable_capability_fact_kb(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_CAPABILITY_FACT_KB", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_DECISION_ARBITRATOR", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_BUDGET_CLOCK_V2", True)


def test_probe_kb_capability_empty_hits_not_sync_ok() -> None:
    with patch.object(
        kb_pipeline.retrieve_service,
        "retrieve_knowledge",
        return_value=([], {"strategy": "auto", "hits": 0}),
    ):
        fact, advice, chunks, _trace = kb_pipeline.probe_kb_capability("知识库里有什么")
    assert chunks == []
    assert fact.quality_level == "empty"
    assert fact.metadata["hits"] == 0
    assert fact.metadata["evidence_tier"] == "none"
    assert advice.suggested_mode != "sync_ok"
    assert advice.reason == "kb_no_hits"


def test_probe_kb_capability_with_hits_sync_ok() -> None:
    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            source_id="doc:1",
            text="命中段落",
            score=0.82,
            combined_score=0.82,
            score_normalized=0.82,
        )
    ]
    with patch.object(
        kb_pipeline.retrieve_service,
        "retrieve_knowledge",
        return_value=(chunks, {"strategy": "auto", "hits": 1}),
    ):
        fact, advice, out_chunks, _trace = kb_pipeline.probe_kb_capability("查询条款")
    assert len(out_chunks) == 1
    assert fact.metadata["hits"] == 1
    assert fact.metadata["top_score"] == pytest.approx(0.82)
    assert fact.metadata["evidence_tier"] == "strong"
    assert advice.suggested_mode == "sync_ok"


def test_probe_kb_capability_low_score_not_sync_ok() -> None:
    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            source_id="doc:1",
            text="弱命中",
            score=0.05,
            combined_score=0.05,
            score_normalized=0.05,
        )
    ]
    with patch.object(
        kb_pipeline.retrieve_service,
        "retrieve_knowledge",
        return_value=(chunks, {"strategy": "auto", "hits": 1}),
    ):
        _fact, advice, _chunks, _trace = kb_pipeline.probe_kb_capability("模糊问题")
    assert advice.suggested_mode != "sync_ok"
    assert advice.reason == "kb_low_score"


def test_run_kb_fast_path_returns_none_when_no_hits(
    enable_capability_fact_kb,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from application.chat.executors.fast_lanes import kb_fast_impl

    with patch.object(
        kb_pipeline,
        "probe_kb_capability",
        return_value=(
            CapabilityFact(
                lane="kb",
                probe_elapsed_ms=10,
                quality_level="empty",
                metadata={"hits": 0, "top_score": 0.0, "evidence_tier": "none"},
            ),
            CapabilityAdvice(
                suggested_mode="needs_user_confirm",
                reason="kb_no_hits",
            ),
            [],
            {},
        ),
    ):
        monkeypatch.setattr(
            kb_fast_impl,
            "summarize_fast_material",
            lambda **_k: (_ for _ in ()).throw(AssertionError("summarize must not run")),
        )
        assert kb_fast_impl.run_kb_fast_path(
            message="查知识库",
            context_block=None,
            clock=BudgetClock.start(),
        ) is None
