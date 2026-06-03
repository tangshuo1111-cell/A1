"""§7.5 — async_entry unified field contract for video/web/document lanes."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from application.chat.async_entry import (
    ASYNC_PENDING_EXTRA_FIELDS,
    ASYNC_PENDING_TOP_LEVEL_FIELDS,
    build_async_pending_result,
)
from application.chat.pending_kind import PendingKind
from services.capabilities.contracts import CapabilityFact
from tasks.orchestration import task_query_service


def _router_kwargs() -> dict:
    return {
        "router_source": "rule",
        "router_confidence": 0.95,
        "router_fallback": False,
        "router_decision_ms": 4,
        "session_id": "s7b-async",
        "request_id": "req-s7b",
        "elapsed_ms": 90,
    }


def _assert_async_contract(result: dict, *, lane: str, task_id: str) -> None:
    for field in ASYNC_PENDING_TOP_LEVEL_FIELDS:
        assert field in result, f"missing top-level field {field}"
    extra = result["extra"]
    for field in ASYNC_PENDING_EXTRA_FIELDS:
        assert field in extra, f"missing extra field {field} for lane={lane}"

    assert result["task_id"] == task_id
    assert result["task_status"] == "pending"
    assert result["answer_type"] == "async_pending"
    assert result["primary_path"] == f"{lane}_async"
    assert extra["lane"] == lane
    assert extra["mode"] == "async"
    assert extra["pending_kind"] == PendingKind.PROCESSING_PENDING.value
    assert extra["partial_answer_text"] == result["answer"]
    assert "video_task_id" not in extra


@pytest.mark.parametrize(
    ("lane", "message", "enqueue_path", "task_id"),
    [
        (
            "video",
            "https://www.bilibili.com/video/BVtest001",
            "application.chat.async_entry.task_plane_service.enqueue_video_background_task",
            "task-video-s7b",
        ),
        (
            "web",
            "请抓取 https://example.com/article",
            "application.chat.async_entry.task_plane_service.enqueue_web_heavy_fetch_task",
            "task-web-s7b",
        ),
        (
            "document",
            "请 OCR D:\\docs\\report.pdf",
            "application.chat.async_entry.task_plane_service.enqueue_document_ocr_task",
            "task-doc-s7b",
        ),
    ],
)
def test_async_entry_three_lanes_share_field_contract(
    lane: str,
    message: str,
    enqueue_path: str,
    task_id: str,
) -> None:
    with patch(enqueue_path, return_value=(task_id, "memory")) as enqueue_mock:
        result = build_async_pending_result(message=message, lane=lane, **_router_kwargs())
    enqueue_mock.assert_called_once()
    _assert_async_contract(result, lane=lane, task_id=task_id)


def test_async_entry_reuses_existing_task_without_reenqueue() -> None:
    with patch(
        "application.chat.async_entry.task_plane_service.enqueue_video_background_task",
    ) as enqueue_mock:
        result = build_async_pending_result(
            message="https://example.com/v",
            lane="video",
            existing_task_id="task-existing-s7b",
            queue_backend="memory",
            **_router_kwargs(),
        )
    enqueue_mock.assert_not_called()
    _assert_async_contract(result, lane="video", task_id="task-existing-s7b")
    assert result["extra"]["queue_backend"] == "memory"


def test_async_entry_passes_prefilled_fact_to_video_enqueue() -> None:
    fact = CapabilityFact(lane="video", probe_elapsed_ms=120, duration_sec=600.0)
    with patch(
        "application.chat.async_entry.task_plane_service.enqueue_video_background_task",
        return_value=("task-fact-s7b", "memory"),
    ) as enqueue_mock:
        build_async_pending_result(
            message="https://example.com/long",
            lane="video",
            prefilled_fact=fact,
            **_router_kwargs(),
        )
    enqueue_mock.assert_called_once()
    assert enqueue_mock.call_args.kwargs["prefilled_fact"] is fact


def test_task_query_pending_kind_matches_chat_contract() -> None:
    assert (
        task_query_service.pending_kind_for_public_status(task_query_service.PUBLIC_STATUS_QUEUED)
        == PendingKind.PROCESSING_PENDING.value
    )
    assert (
        task_query_service.pending_kind_for_public_status(task_query_service.PUBLIC_STATUS_RUNNING)
        == PendingKind.PROCESSING_PENDING.value
    )
    assert (
        task_query_service.pending_kind_for_public_status(task_query_service.PUBLIC_STATUS_PARTIAL)
        == PendingKind.PARTIAL_PENDING.value
    )


def test_normalize_task_row_includes_pending_kind() -> None:
    row = task_query_service._normalize_task_row(
        {
            "task_id": "task-norm-s7b",
            "status": "queued",
            "metadata": {"payload_version": 1},
        }
    )
    assert row["pending_kind"] == PendingKind.PROCESSING_PENDING.value
