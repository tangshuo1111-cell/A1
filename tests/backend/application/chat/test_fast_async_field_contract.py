"""§6.4 — fast/async field contract: top-level task_id + pending_kind."""
from __future__ import annotations

from unittest.mock import patch

from application.chat.async_entry import build_async_pending_result
from application.chat.fast_path_entry import build_fast_result, should_demote_fast_to_async
from application.chat.pending_kind import PendingKind
from services.capabilities.contracts import CapabilityAdvice


def test_build_fast_result_sets_top_level_task_id_for_video_background() -> None:
    result = build_fast_result(
        answer="这个视频已进入后台处理队列。",
        session_id="s5-fields",
        request_id="req-1",
        elapsed_ms=120,
        extra={
            "lane": "video",
            "fast_path": "video_fast_background_hint",
            "task_id": "task-bg-001",
            "pending_kind": PendingKind.FAST_PENDING.value,
            "capabilities_called": ["capability.video.duration_probe"],
        },
    )
    assert result["task_id"] == "task-bg-001"
    assert result["task_status"] == "pending"
    assert result["answer_type"] == "fast_pending"
    assert result["extra"]["pending_kind"] == PendingKind.FAST_PENDING.value
    assert "video_task_id" not in result["extra"]
    assert result["extra"]["partial_answer_text"] == "这个视频已进入后台处理队列。"


def test_build_fast_result_plain_fast_has_no_task_id() -> None:
    result = build_fast_result(
        answer="quick answer",
        session_id="s5-plain",
        request_id=None,
        elapsed_ms=50,
        extra={
            "lane": "general",
            "fast_path": "direct_llm",
            "capabilities_called": ["capability.general.direct_answer"],
        },
    )
    assert result["task_id"] is None
    assert result["task_status"] == "succeeded"


def test_async_entry_sets_processing_pending_kind() -> None:
    with patch(
        "application.chat.async_entry.task_plane_service.enqueue_video_background_task",
        return_value=("task-async-001", "pg"),
    ):
        result = build_async_pending_result(
            message="https://www.bilibili.com/video/BVtest",
            lane="video",
            router_source="rule",
            router_confidence=0.98,
            router_fallback=False,
            router_decision_ms=3,
            session_id="s5-async",
            request_id="req-async",
            elapsed_ms=80,
        )
    assert result["task_id"] == "task-async-001"
    assert result["task_status"] == "pending"
    assert result["extra"]["pending_kind"] == PendingKind.PROCESSING_PENDING.value


def test_should_demote_fast_to_async_from_capability_advice() -> None:
    advice = CapabilityAdvice(suggested_mode="demote_to_async", reason="duration_probe")
    assert should_demote_fast_to_async({"capability_advice": advice}) is True
    assert should_demote_fast_to_async({"capability_suggested_mode": "demote_to_async"}) is True
    assert should_demote_fast_to_async({"arbitrator.decided_mode": "async"}) is True
    assert should_demote_fast_to_async({"lane": "video"}) is False
