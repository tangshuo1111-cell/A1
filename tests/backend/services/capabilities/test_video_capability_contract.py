"""S4a — video processing service returns native capability contract pairs."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from services.capabilities.contracts import CapabilityAdvice, CapabilityFact
from services.capabilities.video.processing_service import (
    VideoCapabilityOutcome,
    VideoProcessingRequest,
    VideoProcessingResult,
    result_to_capability_pair,
    run_video_capability,
)
from tools.asr import errors as asr_errors


def _result(**kwargs) -> VideoProcessingResult:
    defaults = {
        "status": "success",
        "source_type": "web_video",
        "source_ref": "https://example.com/v",
        "title": "demo",
        "text": "subtitle text long enough for quality",
        "transcript_source": "subtitles",
        "metadata": {"video_probe_elapsed_ms": 120, "duration_sec": 30.0, "quality_level": "good"},
    }
    defaults.update(kwargs)
    return VideoProcessingResult(**defaults)


class TestResultToCapabilityPair:
    def test_success_maps_to_sync_ok(self):
        fact, advice = result_to_capability_pair(_result())
        assert isinstance(fact, CapabilityFact)
        assert isinstance(advice, CapabilityAdvice)
        assert advice.suggested_mode == "sync_ok"
        assert fact.lane == "video"
        assert fact.subtitle_available is True
        assert fact.metadata["source_type"] == "web_video"

    def test_deferred_maps_to_demote_to_async_advice(self):
        fact, advice = result_to_capability_pair(
            _result(
                status="deferred",
                text="",
                transcript_source="",
                metadata={
                    "duration_sec": 600.0,
                    "queue_reason": "duration_over_short_threshold",
                    "background_task_id": "task-1",
                    "video_probe_elapsed_ms": 800,
                },
            )
        )
        assert advice.suggested_mode == "demote_to_async"
        assert advice.reason == "duration_over_short_threshold"
        assert fact.metadata["background_task_id"] == "task-1"

    def test_confirm_required_maps_to_needs_user_confirm(self):
        _, advice = result_to_capability_pair(
            _result(
                status="failed",
                text="",
                error_code=asr_errors.ASR_REQUIRES_USER_CONFIRMATION,
                failure_reason="need confirm",
            )
        )
        assert advice.suggested_mode == "needs_user_confirm"


class TestRunVideoCapability:
    def test_run_video_capability_returns_dual_outcome_and_preserves_result(self, monkeypatch: pytest.MonkeyPatch):
        result = _result(status="deferred", text="", metadata={"queue_reason": "remaining_budget_low"})
        monkeypatch.setattr(
            "services.capabilities.video.processing_service.run_video_processing",
            lambda request: result,
        )
        request = VideoProcessingRequest(
            source_type="web_video",
            source_ref="https://example.com/v",
            title="demo",
            task_id="task-1",
            session_id="s1",
            confirmed=False,
            probe=Mock(),
            duration_probe=lambda: 0.0,
            queue_background=lambda: None,
            run_sync_asr=lambda _ms: Mock(ok=False),
        )
        outcome = run_video_capability(request)
        assert isinstance(outcome, VideoCapabilityOutcome)
        assert outcome.result is result
        assert outcome.advice.suggested_mode == "demote_to_async"
        assert outcome.fact.probe_elapsed_ms >= 0
