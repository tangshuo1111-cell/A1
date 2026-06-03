"""S4b — artifact_ref reuse hint in background executor."""
from __future__ import annotations

from pathlib import Path

import pytest

from services.capabilities.video import background_executor
from services.capabilities.video.parallel_asr_service import ParallelAsrResult
from services.execution import artifact_store


def _asr_ok() -> ParallelAsrResult:
    return ParallelAsrResult(
        ok=True,
        text="transcript",
        provider="test",
        model="test",
        segments=[],
        error_code="",
        failure_reason="",
        provider_failures=[],
        provider_attempts=[],
        audio_segment_count=1,
        audio_segmentation_mode="single",
        audio_segmentation_fallback_reason="",
        silence_point_count=0,
        cut_point_count=0,
    )


def _patch_asr_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        background_executor,
        "_download_web_video_audio",
        lambda url: (Path("fake.wav"), Path("/tmp/work"), None),
    )
    monkeypatch.setattr(background_executor, "run_parallel_segment_asr", lambda *a, **k: _asr_ok())
    monkeypatch.setattr("video.url_fetch_ytdlp._safe_cleanup", lambda *_a, **_k: None)


def test_background_executor_marks_artifact_reused(monkeypatch: pytest.MonkeyPatch, tmp_path):
    ref = artifact_store.put(b"cached-audio", kind="audio", ttl_sec=1800, root=tmp_path)
    monkeypatch.setattr(
        "services.execution.artifact_store.get",
        lambda artifact_ref, root=None: b"cached-audio" if artifact_ref == ref else None,
    )
    monkeypatch.setattr(
        background_executor.task_job_store,
        "get_job",
        lambda task_id: {
            "task_id": task_id,
            "metadata": {"artifact_ref": ref},
        },
    )
    monkeypatch.setattr(background_executor.task_job_store, "mark_task_running", lambda *a, **k: None)
    succeeded: list[dict] = []
    monkeypatch.setattr(
        background_executor.task_job_store,
        "mark_task_succeeded",
        lambda task_id, result_summary=None, **kwargs: succeeded.append(result_summary or {}),
    )
    _patch_asr_chain(monkeypatch)
    monkeypatch.setattr(
        "services.capabilities.answer_draft.final_answer_fields_for_task",
        lambda **k: {
            "final_answer": str(k.get("material") or ""),
            "draft": True,
            "draft_limitations": [],
            "draft_critic_check": {},
        },
    )
    from video.web_video_chat_context import web_video_long_asr_confirmed

    token = web_video_long_asr_confirmed.set(True)
    try:
        background_executor.run_web_video_asr_task(
            "task-artifact",
            "https://example.com/v",
            "sess",
            artifact_ref=ref,
        )
    finally:
        web_video_long_asr_confirmed.reset(token)
    assert succeeded
    assert succeeded[0].get("artifact.reused") is True
    assert succeeded[0].get("artifact.miss_reason") is None
    assert succeeded[0].get("final_answer") == "transcript"


def test_background_executor_records_artifact_miss_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        background_executor.task_job_store,
        "mark_task_running",
        lambda *a, **k: None,
    )
    succeeded: list[dict] = []
    monkeypatch.setattr(
        background_executor.task_job_store,
        "mark_task_succeeded",
        lambda task_id, result_summary=None, **kwargs: succeeded.append(result_summary or {}),
    )
    _patch_asr_chain(monkeypatch)
    monkeypatch.setattr(
        "services.capabilities.answer_draft.final_answer_fields_for_task",
        lambda **k: {"final_answer": str(k.get("material") or ""), "draft": True, "draft_limitations": [], "draft_critic_check": {}},
    )
    from video.web_video_chat_context import web_video_long_asr_confirmed

    token = web_video_long_asr_confirmed.set(True)
    try:
        background_executor.run_web_video_asr_task(
            "task-artifact-miss",
            "https://example.com/v",
            "sess",
            artifact_ref="local://sha256/" + ("0" * 64) + "?kind=audio&ttl=1800",
        )
    finally:
        web_video_long_asr_confirmed.reset(token)
    assert succeeded
    assert succeeded[0].get("artifact.reused") is False
    assert succeeded[0].get("artifact.miss_reason") == "not_found"


def test_resolve_artifact_reuse_expired(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.execution import artifact_store

    ref = artifact_store.put(b"cached-audio", kind="audio", ttl_sec=1800, root=tmp_path)
    monkeypatch.setattr("services.execution.artifact_store.time.time", lambda: 9999999999)
    fields = artifact_store.resolve_artifact_reuse(ref, root=tmp_path)
    assert fields["artifact.reused"] is False
    assert fields["artifact.miss_reason"] == "expired"
