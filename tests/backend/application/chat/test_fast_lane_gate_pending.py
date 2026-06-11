"""§6.3 — fast_lane_gate rejects fast when session carries pending context."""
from __future__ import annotations

from threading import Lock
from types import SimpleNamespace

import pytest

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
from application.chat.fast_lane_gate import should_allow_fast
from application.chat.history_buffer import ChatTurnDeps
from application.chat.pending_kind import PendingKind
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from application.ingress.lane_decision_schema import LaneDecision
from domain.session_types import PendingVideoText, PrevVideoRef
from schemas import MainDecision


def test_fast_lane_gate_rejects_session_pending() -> None:
    ingress = LaneDecision(
        lane="video",
        mode="fast",
        router_source="rule",
        router_confidence=0.9,
        router_decision_ms=1,
    )
    assert should_allow_fast(
        session_pending=PendingKind.PROCESSING_PENDING,
        ingress=ingress,
        message="总结一下",
    ) is False
    assert should_allow_fast(
        session_pending=PendingKind.NONE,
        ingress=ingress,
        message="https://example.com/v",
    ) is True


def test_run_chat_turn_skips_fast_when_session_pending_video(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import feature_flags

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_FAST_LANE_GATE", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_FAST_LANE_VIDEO", True)

    fast_called = {"count": 0}

    def _video_fast(*_a, **_k):
        fast_called["count"] += 1
        return "fast answer", {"lane": "video", "fast_path": "video_fast"}

    monkeypatch.setattr(
        "application.ingress.resolve_lane_decision",
        lambda **_kwargs: LaneDecision(
            lane="video",
            mode="fast",
            router_source="rule",
            router_confidence=0.95,
            router_decision_ms=2,
        ),
    )
    monkeypatch.setattr("application.chat.executors.fast_lanes.video.run", _video_fast)
    monkeypatch.setattr(
        "application.chat.response_assembly.build_extra",
        lambda *_a, **_k: {"lane": "video", "primary_path": "complex"},
    )

    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="s5-gate", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="waibu",
            zhengju_need=True,
            allow_kb=False,
            allow_web=True,
            fengxian_yinzi=0.5,
            celue_tag="complex",
        ),
    )
    bundle = AgnoMaterialBundle(
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
            laiyuan_zhu="video",
            use_kb=False,
            use_web=False,
            que_shenme="none",
            xia_yi_bu="zhi_da",
        ),
    )

    deps = ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={
            "sess-pending": PendingVideoText(
                text="pending transcript",
                title="old video",
                source_url="https://example.com/old",
                source_basename="old",
                duration_sec=120.0,
                text_source="asr",
            )
        },
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: bundle),
        answer_agent=SimpleNamespace(),
        run_basic_qa=lambda *a, **k: "complex path answer",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )

    out = run_agno_chat_turn_impl("总结一下", session_id="sess-pending", deps=deps)
    assert fast_called["count"] == 0
    assert out["answer"] == "complex path answer"
    assert out["answer_type"] == "basic_agno"


def test_run_chat_turn_skips_fast_when_prev_video_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config import feature_flags

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_FAST_LANE_GATE", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_FAST_LANE_VIDEO", True)
    monkeypatch.setattr(
        "application.ingress.resolve_lane_decision",
        lambda **_kwargs: LaneDecision(
            lane="video",
            mode="fast",
            router_source="rule",
            router_confidence=0.95,
            router_decision_ms=2,
        ),
    )
    monkeypatch.setattr(
        "application.chat.executors.fast_lanes.video.run",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("fast must not run")),
    )
    monkeypatch.setattr(
        "application.chat.response_assembly.build_extra",
        lambda *_a, **_k: {"lane": "video", "primary_path": "complex"},
    )

    deps = ChatTurnDeps(
        histories={},
        session_prev_video={
            "sess-prev": PrevVideoRef(source_id="video:foo.mp4", basename="foo.mp4", path=None)
        },
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(
            pan=lambda *a, **k: AgnoCollaborationPlan(
                decision=MainDecision(task_id="s5-prev", task_status="routed"),
                force_skip_evidence=False,
                web_supplement_mode="explicit_only",
                answer_composition="default",
                xiezuo_pan=MainXiezuoPan(
                    renwu_lei="waibu",
                    zhengju_need=True,
                    allow_kb=False,
                    allow_web=False,
                    fengxian_yinzi=0.5,
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
                    laiyuan_zhu="video",
                    use_kb=False,
                    use_web=False,
                    que_shenme="none",
                    xia_yi_bu="zhi_da",
                ),
            )
        ),
        answer_agent=SimpleNamespace(),
        run_basic_qa=lambda *a, **k: "prev video complex answer",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )

    out = run_agno_chat_turn_impl("总结一下", session_id="sess-prev", deps=deps)
    assert out["answer"] == "prev video complex answer"
