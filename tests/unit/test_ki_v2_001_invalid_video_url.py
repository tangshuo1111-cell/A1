"""KI-V2-001 — unsupported video URL must stay in video failure path."""

from __future__ import annotations

from threading import Lock
from unittest.mock import patch

import pytest

from application.chat.executors.fast_lanes.video_fast_impl import (
    VIDEO_URL_UNSUPPORTED_ANSWER,
    run_video_fast_path,
)
from application.chat.history_buffer import ChatTurnDeps
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from application.ingress.lane_selector import select_lane
from application.ingress.request_classifier import classify_request
from config import feature_flags
from tools.video.errors import VIDEO_URL_UNSUPPORTED


@pytest.fixture(autouse=True)
def _enable_router(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_DECISION_ARBITRATOR", True)


def test_unsupported_video_intent_routes_to_video_lane() -> None:
    message = "请总结这个视频：https://example.com/not-a-real-video"
    signals = classify_request(
        message=message,
        use_knowledge=False,
        v13_file_content=None,
        v13_text_content=None,
    )
    assert signals.has_unsupported_video_url is True
    assert signals.has_video_url is False
    assert signals.has_web_url is False
    assert select_lane(signals)[0] == "video"


def test_webpage_intent_stays_on_web_lane() -> None:
    message = "请总结这个网页：https://example.com/article"
    signals = classify_request(
        message=message,
        use_knowledge=False,
        v13_file_content=None,
        v13_text_content=None,
    )
    assert signals.has_unsupported_video_url is False
    assert signals.has_web_url is True
    assert select_lane(signals)[0] == "web"


def test_supported_video_url_stays_video_lane() -> None:
    message = "请总结这个视频：https://www.youtube.com/watch?v=zafiGBrFkRM"
    signals = classify_request(
        message=message,
        use_knowledge=False,
        v13_file_content=None,
        v13_text_content=None,
    )
    assert signals.has_video_url is True
    assert signals.has_unsupported_video_url is False
    assert select_lane(signals)[0] == "video"


def test_video_fast_returns_unsupported_failure_without_probe() -> None:
    with patch(
        "tools.video.extract_web_video_subtitle._extract_web_video_subtitle",
    ) as probe:
        answer, extra = run_video_fast_path(
            message="请总结这个视频：https://example.com/not-a-real-video",
            session_id="s1",
            context_block=None,
            clock=None,
        )
    probe.assert_not_called()
    assert answer == VIDEO_URL_UNSUPPORTED_ANSWER
    assert extra.get("fast_path") == "video"
    assert extra.get("lane") == "video"
    assert extra.get("v16_video_error_code") == VIDEO_URL_UNSUPPORTED
    assert "capability.document" not in str(extra.get("capabilities_called"))


def _deps() -> ChatTurnDeps:
    from agents.answer_agent import AnswerAgent
    from agents.main_agent import MainAgent
    from agents.middle_agent import MiddleAgent

    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=MainAgent(),
        middle_agent=MiddleAgent(),
        answer_agent=AnswerAgent(),
        run_basic_qa=lambda *_a, **_k: "不应走 direct_llm 总结。",
        path_fingerprint=lambda *_a, **_k: "fp",
        nodes_contract=lambda *_a, **_k: {},
    )


def test_invalid_video_url_turn_returns_failed_video_path() -> None:
    with patch(
        "tools.video.extract_web_video_subtitle._extract_web_video_subtitle",
    ) as probe:
        out = run_agno_chat_turn_impl(
            "请总结这个视频：https://example.com/not-a-real-video",
            session_id="eval_video_total_failure",
            deps=_deps(),
        )
    probe.assert_not_called()
    assert out["task_status"] == "failed"
    assert out["task_status"] not in {"succeeded", "pending"}
    assert out.get("primary_path") == "video"
    assert out["extra"].get("lane") == "video"
    assert out["extra"].get("fast_path") == "video"
    assert out["extra"].get("exit", {}).get("winner_rule") == "hard_failure"
    assert out["extra"].get("v16_video_error_code") == VIDEO_URL_UNSUPPORTED
    assert out.get("transcript_source") in (None, "")
    assert "刚才" not in str(out.get("answer") or "")
    assert out.get("answer") == VIDEO_URL_UNSUPPORTED_ANSWER
