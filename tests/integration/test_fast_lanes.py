from __future__ import annotations

from threading import Lock
from types import SimpleNamespace

import pytest

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
from application.chat.history_buffer import ChatTurnDeps
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from schemas import MainDecision


def _deps() -> ChatTurnDeps:
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: None),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: None),
        answer_agent=SimpleNamespace(),
        run_basic_qa=lambda *a, **k: "unused",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )


def _complex_deps() -> ChatTurnDeps:
    plan = AgnoCollaborationPlan(
        decision=MainDecision(task_id="p7-complex", task_status="routed"),
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
        web_block="[Web检索] 长视频需要后续重处理",
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
            laiyuan_zhu="web",
            use_kb=False,
            use_web=True,
            que_shenme="none",
            xia_yi_bu="zhi_da",
        ),
    )
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *a, **k: plan),
        middle_agent=SimpleNamespace(caipan=lambda *a, **k: bundle),
        answer_agent=SimpleNamespace(),
        run_basic_qa=lambda *a, **k: "这是复杂链返回，不是 fast lane。",
        path_fingerprint=lambda *a, **k: "fp",
        nodes_contract=lambda trace: {},
    )


def test_web_fast_lane_emits_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.capabilities.contracts import CapabilityAdvice, CapabilityFact

    fact = CapabilityFact(
        lane="web",
        probe_elapsed_ms=12,
        metadata={"url": "https://example.com/fast"},
    )
    advice = CapabilityAdvice(suggested_mode="fast", reason="static_fetch")
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.probe_web_capability",
        lambda url, clock=None: (fact, advice),
    )
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
        lambda *_a, **_k: "[Web检索] Fast lane 网页材料",
    )
    out = run_agno_chat_turn_impl(
        "请阅读并总结这个网页 https://example.com/fast",
        session_id="p7-web",
        deps=_deps(),
    )
    extra = out["extra"]
    assert extra["fast_lane_name"] == "web"
    assert extra["fast_exit_reason"] == "web_static_fetch_answer"
    assert extra["capabilities_called"] == ["capability.web.static_fetch"]


def test_video_fast_lane_emits_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.video.extract_web_video_subtitle._extract_web_video_subtitle",
        lambda *_a, **_k: SimpleNamespace(
            status="success",
            text="视频讲了字幕探测和快链。",
            title="p7-video",
            transcript_source="subtitle",
            metadata={"text_source": "subtitle"},
        ),
    )
    out = run_agno_chat_turn_impl(
        "请总结这个视频 https://www.bilibili.com/video/BV1phase7001",
        session_id="p7-video",
        deps=_deps(),
    )
    extra = out["extra"]
    assert extra["fast_lane_name"] == "video"
    assert "capability.video.subtitle_probe" in extra["capabilities_called"]
    assert extra["fast_exit_reason"] == "video_probe_answer"


def test_long_video_escalates_out_of_fast_lane(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import feature_flags

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_APPROVAL_GATE_V1", False)
    monkeypatch.setattr(
        "application.chat.async_entry.task_plane_service.enqueue_video_background_task",
        lambda **_kw: ("task-p7-long", "memory"),
    )
    out = run_agno_chat_turn_impl(
        "帮我总结这个长视频的重点 https://www.youtube.com/watch?v=phase7long001",
        session_id="p7-video-long",
        deps=_complex_deps(),
    )
    extra = out["extra"]
    assert extra["mode"] == "async"
    assert out["task_status"] == "pending"
    assert out.get("task_id") == "task-p7-long"
    assert extra.get("pending_kind") == "processing_pending"
    assert "video_task_id" not in extra
    assert extra.get("fast_lane_name") != "video"
