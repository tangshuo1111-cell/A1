"""S8 — within-turn KB retrieve dedup via TurnCache (§6.5)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from application.chat.turn_cache import TurnCache
from config import feature_flags
from rag.schema import RetrievedChunk
from services.capabilities.knowledge import kb_pipeline


def _sample_chunks() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id="c1",
            source_id="doc:1",
            text="命中段落",
            score=0.82,
            combined_score=0.82,
            score_normalized=0.82,
        )
    ]


def test_kb_probe_and_fetch_share_turn_cache() -> None:
    retrieve_calls = {"n": 0}

    def _retrieve(*_args, **_kwargs):
        retrieve_calls["n"] += 1
        return (_sample_chunks(), {"strategy": "auto", "hits": 1})

    cache = TurnCache(request_id="req-cache-1")
    cache.set_lane("kb")
    with patch.object(kb_pipeline.retrieve_service, "retrieve_knowledge", side_effect=_retrieve):
        kb_pipeline.probe_kb_capability("知识库条款是什么", turn_cache=cache)
        kb_pipeline.fetch_kb_answer_material("知识库条款是什么", turn_cache=cache)

    assert retrieve_calls["n"] == 1
    assert cache.hits()["hits"] == 1
    assert cache.hits()["misses"] == 1


def test_run_kb_fast_path_exposes_turn_cache_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from threading import Lock
    from types import SimpleNamespace

    from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
    from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
    from application.chat.history_buffer import ChatTurnDeps
    from application.chat.run_chat_turn import run_agno_chat_turn_impl
    from application.ingress.lane_decision_schema import LaneDecision
    from schemas import MainDecision

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_TURN_CACHE", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_FAST_LANE_KB", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_CAPABILITY_FACT_KB", True)

    retrieve_calls = {"n": 0}

    def _retrieve(*_args, **_kwargs):
        retrieve_calls["n"] += 1
        return (_sample_chunks(), {"strategy": "auto", "hits": 1})

    monkeypatch.setattr(
        "application.ingress.resolve_lane_decision",
        lambda **_kwargs: LaneDecision(
            lane="kb",
            mode="fast",
            router_source="rule",
            router_confidence=0.95,
            router_decision_ms=2,
        ),
    )
    monkeypatch.setattr(
        "application.chat.executors.fast_lanes.fast_llm.summarize_fast_material",
        lambda **_kwargs: "KB 快答",
    )

    deps = ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(
            pan=lambda *a, **k: AgnoCollaborationPlan(
                decision=MainDecision(task_id="s8-kb", task_status="routed"),
                force_skip_evidence=False,
                web_supplement_mode="explicit_only",
                answer_composition="default",
                xiezuo_pan=MainXiezuoPan(
                    renwu_lei="zhijie",
                    zhengju_need=False,
                    allow_kb=True,
                    allow_web=False,
                    fengxian_yinzi=0.2,
                    celue_tag="complex",
                ),
            )
        ),
        middle_agent=SimpleNamespace(
            caipan=lambda *a, **k: AgnoMaterialBundle(
                knowledge_block=None,
                web_block=None,
                trace=[],
                knowledge_adequate=False,
                material_still_insufficient=False,
                web_judgment_reason="explicit_only",
                kb_evidence_tier="none",
                insufficiency_signal="none",
                cailiao_pan=CailiaoPan(
                    gou=True,
                    kb_qiangdu=0.0,
                    bukong_xinhao="ok",
                    laiyuan_zhu="kb",
                    use_kb=True,
                    use_web=False,
                    que_shenma="none",
                    xia_yi_bu="zhi_da",
                ),
            )
        ),
        answer_agent=SimpleNamespace(),
        run_basic_qa=lambda *a, **k: "不应走到 complex",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )

    with patch.object(kb_pipeline.retrieve_service, "retrieve_knowledge", side_effect=_retrieve):
        out = run_agno_chat_turn_impl(
            "知识库条款是什么",
            session_id="sess-kb-cache",
            request_id="req-kb-cache",
            use_knowledge=True,
            deps=deps,
        )

    assert out["answer"] == "KB 快答"
    assert retrieve_calls["n"] == 1
    assert out["extra"].get("turn_cache.misses") == 1
    assert out["extra"].get("turn_cache.hits") == 0
