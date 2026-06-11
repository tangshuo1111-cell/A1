"""§6.1 — MainAgent.pan single call per turn when ENABLE_MAIN_PLAN_CACHE is on."""
from __future__ import annotations

from threading import Lock
from types import SimpleNamespace

import pytest

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from application.chat.budget_clock import BudgetClock
from application.chat.history_buffer import ChatTurnDeps
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from application.ingress.semantic_router import route_chat_request
from config import feature_flags
from schemas import MainDecision


def _sample_plan() -> AgnoCollaborationPlan:
    return AgnoCollaborationPlan(
        decision=MainDecision(task_id="s1-test", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="zhijie",
            zhengju_need=False,
            allow_kb=False,
            allow_web=False,
            fengxian_yinzi=0.2,
            celue_tag="complex",
        ),
        needs_retrieval=False,
        retrieval_strategy="none",
        answer_mode="direct",
        tools_allowed=(),
        max_rounds=1,
        original_user_intent="你好",
    )


def _deps_with_counting_pan(counter: list[int]) -> ChatTurnDeps:
    plan = _sample_plan()

    def pan(*_args, **_kwargs):
        counter.append(1)
        return plan

    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=pan),
        middle_agent=SimpleNamespace(
            caipan=lambda *a, **k: SimpleNamespace(
                knowledge_block="",
                web_block="",
                trace=[],
                knowledge_adequate=True,
                material_still_insufficient=False,
                web_judgment_reason="skip",
                kb_evidence_tier="none",
                insufficiency_signal="none",
                v11_pending_video_text=None,
                v11_saved_to_kb=False,
                v11_saved_source_id=None,
                pending_item=None,
            )
        ),
        answer_agent=SimpleNamespace(),
        run_basic_qa=lambda *a, **k: (
            "这是一段用于集成测试的足够长的默认回答，确保 complex profile 的质量门控可以通过。"
            "包含结构与足够字符长度。"
        ),
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )


def _disable_fast_lanes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
    for lane_flag in feature_flags.LANE_FAST_FLAG.values():
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, lane_flag, False)


def test_router_defers_pan_when_main_plan_cache_active(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_MAIN_PLAN_CACHE", True)
    pan_calls: list[int] = []

    def pan(*_args, **_kwargs):
        pan_calls.append(1)
        return _sample_plan()

    decision = route_chat_request(
        message="你好",
        session_id="s1-router",
        request_id="s1-router-req",
        use_knowledge=False,
        v13_file_content=None,
        v13_text_content=None,
        main_agent=SimpleNamespace(pan=pan),
        clock=BudgetClock.start(),
    )
    assert pan_calls == []
    assert decision.cached_main_hints is not None
    assert decision.cached_main_hints.router_reason == "low_confidence_deferred_to_main"
    assert not hasattr(decision.cached_main_hints, "tools_allowed")


def test_main_plan_cache_single_pan_call(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_fast_lanes(monkeypatch)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_MAIN_PLAN_CACHE", True)
    pan_calls: list[int] = []
    monkeypatch.setattr(
        "application.chat.response_assembly.build_extra",
        lambda *a, **k: {"lane": "agno_basic", "primary_path": "agno_basic", "mode": "complex"},
    )
    out = run_agno_chat_turn_impl(
        "你好",
        session_id="s1-cache-on",
        deps=_deps_with_counting_pan(pan_calls),
    )
    assert len(pan_calls) == 1
    assert "足够长的默认回答" in out["answer"]


def test_legacy_double_pan_when_main_plan_cache_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_fast_lanes(monkeypatch)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_MAIN_PLAN_CACHE", False)
    pan_calls: list[int] = []
    monkeypatch.setattr(
        "application.chat.response_assembly.build_extra",
        lambda *a, **k: {"lane": "agno_basic", "primary_path": "agno_basic", "mode": "complex"},
    )
    run_agno_chat_turn_impl(
        "你好",
        session_id="s1-cache-off",
        deps=_deps_with_counting_pan(pan_calls),
    )
    assert len(pan_calls) == 2
