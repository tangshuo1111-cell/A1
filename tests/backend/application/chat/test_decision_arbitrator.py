"""§5.6 — decision_arbitrator precedence rules."""
from __future__ import annotations

import time

import pytest

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from application.chat.budget_clock import BudgetClock
from application.chat.decision_arbitrator import arbitrate_mode
from application.chat.pending_kind import PendingKind
from application.ingress.lane_decision_schema import LaneDecision
from schemas import MainDecision
from services.capabilities.contracts import CapabilityAdvice


def _ingress(*, mode: str = "fast") -> LaneDecision:
    return LaneDecision(
        lane="video",
        mode=mode,  # type: ignore[arg-type]
        router_source="rule",
        router_confidence=0.9,
        router_decision_ms=1,
    )


def _clock_with_remaining_ms(remaining_ms: int) -> BudgetClock:
    now = time.perf_counter()
    return BudgetClock(
        started_at=now,
        deadline_at=now + remaining_ms / 1000.0,
        total_budget_ms=remaining_ms,
    )


def _multi_source_plan() -> AgnoCollaborationPlan:
    return AgnoCollaborationPlan(
        decision=MainDecision(task_id="s3-ms", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="hunhe",
            zhengju_need=True,
            allow_kb=True,
            allow_web=True,
            fengxian_yinzi=0.5,
            celue_tag="complex",
        ),
        needs_retrieval=True,
        retrieval_strategy="auto",
        answer_mode="direct",
        tools_allowed=(),
        max_rounds=2,
        original_user_intent="compare",
        job_type="multi_source_compare",
    )


class TestDecisionArbitratorPrecedence:
    def test_rule1_session_pending_forces_complex(self):
        mode, reason = arbitrate_mode(
            session_pending=PendingKind.PROCESSING_PENDING,
            ingress=_ingress(mode="fast"),
            main_plan=None,
            capability_advice=None,
            clock=_clock_with_remaining_ms(15_000),
        )
        assert mode == "complex"
        assert reason == "session_pending_active"

    def test_rule2_capability_demote_to_async(self):
        advice = CapabilityAdvice(
            suggested_mode="demote_to_async",
            reason="duration_over_short_threshold",
        )
        mode, reason = arbitrate_mode(
            session_pending=PendingKind.NONE,
            ingress=_ingress(mode="fast"),
            main_plan=None,
            capability_advice=advice,
            clock=_clock_with_remaining_ms(15_000),
        )
        assert mode == "async"
        assert reason == "duration_over_short_threshold"

    def test_rule3_budget_reserved_exhausted_forces_async(self):
        mode, reason = arbitrate_mode(
            session_pending=PendingKind.NONE,
            ingress=_ingress(mode="fast"),
            main_plan=None,
            capability_advice=None,
            clock=_clock_with_remaining_ms(400),
            reserved_ms=500,
        )
        assert mode == "async"
        assert reason == "budget_reserved_exhausted"

    def test_rule4_multi_source_compare_forces_complex(self):
        mode, reason = arbitrate_mode(
            session_pending=PendingKind.NONE,
            ingress=_ingress(mode="fast"),
            main_plan=_multi_source_plan(),
            capability_advice=None,
            clock=_clock_with_remaining_ms(15_000),
        )
        assert mode == "complex"
        assert reason == "multi_source_compare"

    def test_rule5_fallback_to_ingress_mode(self):
        mode, reason = arbitrate_mode(
            session_pending=PendingKind.NONE,
            ingress=_ingress(mode="complex"),
            main_plan=None,
            capability_advice=None,
            clock=_clock_with_remaining_ms(15_000),
        )
        assert mode == "complex"
        assert reason == "ingress_mode"

    def test_rule_priority_session_pending_beats_capability_demote(self):
        advice = CapabilityAdvice(suggested_mode="demote_to_async", reason="late")
        mode, reason = arbitrate_mode(
            session_pending=PendingKind.MATERIAL_PENDING,
            ingress=_ingress(mode="fast"),
            main_plan=None,
            capability_advice=advice,
            clock=_clock_with_remaining_ms(15_000),
        )
        assert mode == "complex"
        assert reason == "session_pending_active"


def test_run_chat_turn_arbitrator_demotes_async_when_budget_low(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from threading import Lock
    from types import SimpleNamespace

    from application.chat.history_buffer import ChatTurnDeps
    from application.chat.run_chat_turn import run_agno_chat_turn_impl
    from application.ingress.lane_decision_schema import LaneDecision
    from config import feature_flags

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_DECISION_ARBITRATOR", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_BUDGET_CLOCK_V2", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
    monkeypatch.setattr(
        "application.chat.run_chat_turn.resolve_lane_decision",
        lambda **_kwargs: LaneDecision(
            lane="video",
            mode="async",
            router_source="rule",
            router_confidence=0.98,
            router_decision_ms=2,
        ),
    )
    monkeypatch.setattr(
        "application.chat.run_chat_turn._build_async_pending_result",
        lambda **_kwargs: {
            "ok": True,
            "answer": "queued",
            "session_id": "s3-int",
            "request_id": None,
            "task_id": "task-s3",
            "answer_type": "async_pending",
            "task_status": "pending",
            "primary_path": "video_async",
            "pipeline_ok": True,
            "extra": {"mode": "async"},
            "workflow_elapsed_ms": 1,
        },
    )
    monkeypatch.setattr(
        "application.chat.run_chat_turn.BudgetClock.start",
        lambda *_a, **_k: _clock_with_remaining_ms(15_000),
    )

    deps = ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(),
        middle_agent=SimpleNamespace(),
        answer_agent=SimpleNamespace(),
        run_basic_qa=lambda *a, **k: "",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )
    out = run_agno_chat_turn_impl(
        "https://www.bilibili.com/video/BV1test000001",
        session_id="s3-int",
        deps=deps,
    )
    assert out["extra"]["arbitrator.decided_mode"] == "async"
    assert out["extra"]["arbitrator.decided_reason"] == "ingress_mode"
    assert out["extra"]["collaboration_trace"][0]["stage"] == "arbitrator"
