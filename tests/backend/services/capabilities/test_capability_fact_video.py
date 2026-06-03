"""S4b — video capability contract when ENABLE_CAPABILITY_FACT_VIDEO is on."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from config import feature_flags
from services.capabilities.video.processing_service import (
    VideoProcessingRequest,
    VideoProcessingResult,
    result_to_capability_pair,
    run_video_processing,
)


@pytest.fixture
def enable_capability_fact_video(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_CAPABILITY_FACT_VIDEO", True)


def test_run_video_processing_returns_deferred_not_queued(
    enable_capability_fact_video,
    monkeypatch: pytest.MonkeyPatch,
):
    probe = Mock(
        ok=False,
        text="",
        duration_sec=1200.0,
        duration_ms=0.0,
        metadata_extra={},
        error_code="",
        failure_reason="",
    )
    queued_calls: list[str] = []

    request = VideoProcessingRequest(
        source_type="web_video",
        source_ref="https://example.com/v",
        title="demo",
        task_id="task-v4b",
        session_id="s1",
        confirmed=True,
        probe=lambda: probe,
        duration_probe=lambda: 1200.0,
        queue_background=lambda: queued_calls.append("queued"),
        run_sync_asr=lambda _ms: Mock(ok=False),
    )
    monkeypatch.setattr(
        "services.capabilities.video.processing_service.should_queue_video_background",
        lambda **kwargs: (True, "duration_over_short_threshold"),
    )
    monkeypatch.setattr(
        "services.capabilities.video.processing_service.should_force_video_background",
        lambda **kwargs: (False, ""),
    )

    result = run_video_processing(request)
    assert result.status == "deferred"
    assert result.status != "queued"
    assert queued_calls == []


def test_deferred_maps_to_demote_advice_without_queued_status():
    legacy = VideoProcessingResult(
        status="deferred",
        source_type="web_video",
        source_ref="https://example.com/v",
        title="demo",
        metadata={
            "queue_reason": "remaining_budget_low",
            "background_task_id": "task-v4b",
            "video_probe_elapsed_ms": 900,
        },
    )
    fact, advice = result_to_capability_pair(legacy)
    assert advice.suggested_mode == "demote_to_async"
    assert advice.reason == "remaining_budget_low"
    assert fact.metadata["background_task_id"] == "task-v4b"


def test_tool_surface_status_maps_demote_advice_to_queued():
    from services.capabilities.contracts import CapabilityAdvice
    from services.capabilities.video.video_contract_runtime import tool_surface_status

    advice = CapabilityAdvice(
        suggested_mode="demote_to_async",
        reason="remaining_budget_low",
    )
    assert tool_surface_status(legacy_status="deferred", advice=advice) == "queued"
