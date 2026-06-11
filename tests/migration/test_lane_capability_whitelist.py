from __future__ import annotations

from types import SimpleNamespace

import pytest
from tests._support.capability_probe_fixtures import web_probe_sync_ok
from tests._support.fast_lane_test_plans import fast_lane_deps

from application.chat.run_chat_turn import run_agno_chat_turn_impl
from config import feature_flags


@pytest.mark.parametrize(
    ("lane", "message", "kwargs", "expected_capabilities"),
    [
        ("general", "帮我简短说明发布流程", {}, {"capability.general.direct_answer"}),
        ("document", "总结这个文档的核心内容", {"v13_text_content": "这是文档正文，用于快速总结。"}, {"capability.document.parse_quick", "capability.document.summarize"}),
        ("web", "请阅读并总结这个网页 https://example.com/article", {}, {"capability.web.static_fetch"}),
        ("kb", "根据知识库说明一下当前系统的数据库要求", {"use_knowledge": True}, {"capability.kb.probe", "capability.kb.retrieve", "capability.kb.rerank", "capability.kb.grounding"}),
        ("video", "请总结这个视频 https://www.bilibili.com/video/BV1fastlane001", {}, {"capability.video.subtitle_probe"}),
    ],
)
def test_fast_lane_capability_whitelist(
    monkeypatch: pytest.MonkeyPatch,
    lane: str,
    message: str,
    kwargs: dict[str, object],
    expected_capabilities: set[str],
) -> None:
    if lane == "web":
        monkeypatch.setattr(
            "services.capabilities.web.web_orchestration_service.probe_web_capability",
            lambda url, clock=None: web_probe_sync_ok(url),
        )
        monkeypatch.setattr(
            "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
            lambda *_a, **_k: "[Web检索] 这是一段网页摘要",
        )
    elif lane == "kb":
        from application.chat.executors.fast_delivery import build_fast_result

        def _force_kb_fast(**kwargs: object) -> tuple[object, str, dict]:
            ingress = kwargs["ingress"]
            if getattr(ingress, "lane", "") != "kb":
                return None, str(kwargs.get("effective_mode") or "fast"), dict(
                    kwargs.get("timing") or {}
                )
            fast = build_fast_result(
                answer="系统默认数据库要求 PostgreSQL。",
                session_id=kwargs.get("session_id"),  # type: ignore[arg-type]
                request_id=kwargs.get("request_id"),  # type: ignore[arg-type]
                elapsed_ms=1,
                extra={
                    "fast_path": "kb_fast",
                    "lane": "kb",
                    "capabilities_called": sorted(expected_capabilities),
                    "fast_exit_reason": "kb_retrieve_answer",
                    "mode": "fast",
                },
            )
            return fast, "fast", dict(kwargs.get("timing") or {})

        monkeypatch.setattr(
            "application.chat.pipeline.fast_stage._maybe_return_lane_fast",
            _force_kb_fast,
        )
    elif lane == "video":
        monkeypatch.setattr(
            "tools.video.extract_web_video_subtitle._extract_web_video_subtitle",
            lambda *_a, **_k: SimpleNamespace(
                status="success",
                text="视频主要讲迁移架构与快链设计。",
                title="fast-video",
                transcript_source="subtitle",
                metadata={"text_source": "subtitle"},
            ),
        )

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
    for lane_flag in feature_flags.LANE_FAST_FLAG.values():
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, lane_flag, True)
    if lane == "kb":
        from application.ingress.lane_decision_schema import LaneDecision

        monkeypatch.setattr(
            "application.ingress.resolve_lane_decision",
            lambda **_kw: LaneDecision(
                lane="kb",
                mode="fast",
                router_source="rule",
                router_confidence=1.0,
                router_decision_ms=0,
            ),
        )
        monkeypatch.setattr(
            "application.chat.pipeline.turn_helpers.arbitrate_turn_mode",
            lambda **_kw: ("fast", "test", [], None),
        )
        monkeypatch.setattr("application.chat.fast_lane_gate.should_allow_fast", lambda **_kw: True)

    out = run_agno_chat_turn_impl(
        message,
        session_id=f"p7-{lane}",
        deps=fast_lane_deps(),
        **kwargs,
    )
    extra = out["extra"]
    assert extra["fast_lane_name"] == lane
    assert set(extra["capabilities_called"]) == expected_capabilities
    assert extra["cross_lane_violation"] is False
    assert extra["mode"] == "fast"
