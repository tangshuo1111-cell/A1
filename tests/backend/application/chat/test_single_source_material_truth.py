from __future__ import annotations

from types import SimpleNamespace

from agents.middle_agent.material_sufficiency import evaluate_material_sufficiency
from application.chat.chat_contracts import KbSufficiencyResult
from services.capabilities.knowledge.middle_retrieval_gather import run_kb_retrieval_gather


def _plan() -> SimpleNamespace:
    return SimpleNamespace(
        retrieval_strategy="auto",
        retrieval_filters={},
        tools_allowed=("retrieve_knowledge",),
    )


def test_kb_gather_derives_kb_sufficiency_without_shared_cache(monkeypatch):
    class Chunk:
        source_id = "src"
        chunk_id = "c1"
        score = 0.82

        def to_context_line(self) -> str:
            return "chunk body"

    def fake_retrieve(*_args, **_kwargs):
        return [Chunk()], {
            "strategy_requested": "auto",
            "strategy_used": "auto:hybrid",
            "hits": 1,
            "no_match": False,
        }

    monkeypatch.setattr(
        "services.capabilities.knowledge.middle_retrieval_gather._retrieve_svc.retrieve_knowledge",
        fake_retrieve,
    )

    out = run_kb_retrieval_gather(
        try_rag=True,
        msg="test message",
        plan=_plan(),
        shared_prep=None,
        v8_history_used=False,
        v8_anchor=None,
        v8_followup_query="",
        blocked_failures=[],
        is_tool_allowed=lambda *_a, **_k: True,
    )

    assert out.kb_sufficiency is not None
    assert out.kb_sufficiency.hits == 1
    assert out.kb_sufficiency.level in {"insufficient", "adequate_complex"}


def test_material_sufficiency_uses_kb_result_as_single_source():
    result = evaluate_material_sufficiency(
        try_rag=True,
        knowledge_block="kb",
        web_block=None,
        retrieved_chunks_count=1,
        temporary_materials_count=0,
        commit_results_count=0,
        kb_sufficiency=KbSufficiencyResult(
            level="insufficient",
            adequate=False,
            reason_codes=("kb_hits_below_complex",),
            hits=1,
            top_score=0.82,
            evidence_tier="strong",
        ),
        material_insufficient=False,
        retrieval_trace_info={"no_match": False, "low_confidence": False},
    )

    assert result.level == "insufficient"
    assert result.adequate is False
    assert "kb_hits_below_complex" in result.reason_codes


def test_material_sufficiency_allows_non_kb_material_to_satisfy_bundle():
    result = evaluate_material_sufficiency(
        try_rag=True,
        knowledge_block=None,
        web_block="web evidence",
        retrieved_chunks_count=0,
        temporary_materials_count=0,
        commit_results_count=0,
        kb_sufficiency=KbSufficiencyResult(
            level="insufficient",
            adequate=False,
            reason_codes=("kb_miss",),
            hits=0,
            top_score=0.0,
            evidence_tier="none",
        ),
        material_insufficient=False,
        retrieval_trace_info={"no_match": True},
    )

    assert result.level == "sufficient"
    assert result.adequate is True
