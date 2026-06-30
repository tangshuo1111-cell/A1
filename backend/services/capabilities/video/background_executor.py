from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from config.settings import settings
from services.capabilities.video.audio_service import extract_audio_wav_for_asr
from storage import task_job_store
from tasks.queue.video_task_queue import VideoTaskMessage
from video.web_video_chat_context import web_video_long_asr_confirmed

from .duration_probe import probe_local_video_duration_sec
from .parallel_asr_service import run_parallel_segment_asr
from .provider_chain import resolve_video_asr_provider_chain
from .types import VideoBackgroundTaskPayload
from .web_video_extract_service import _download_web_video_audio

logger = logging.getLogger("light_maqa")


def _artifact_fields(artifact_ref: str | None) -> dict[str, bool | str | None]:
    from services.execution.artifact_store import resolve_artifact_reuse

    return resolve_artifact_reuse(artifact_ref)


def _record_video_failure_diagnostics(
    task_id: str,
    *,
    stage_timings: dict[str, int],
    fetched_extra: dict[str, object] | None = None,
) -> None:
    task_job_store.update_task_async_metadata(
        task_id,
        metadata={
            "video_failure_diagnostics": {
                "stage_timings": stage_timings,
                "asr_provider_chain": list(chain) if isinstance(chain := (fetched_extra or {}).get("asr_provider_chain"), list) else [],
                "asr_provider_failures": list(failures) if isinstance(failures := (fetched_extra or {}).get("asr_provider_failures"), list) else [],
                "asr_provider_attempts": list(attempts) if isinstance(attempts := (fetched_extra or {}).get("asr_provider_attempts"), list) else [],
            }
        },
    )


def _mark_video_stage(task_id: str, *, stage: str, progress: float, metadata: dict[str, object] | None = None) -> None:
    task_job_store.mark_task_running(task_id, stage=stage, progress=progress)
    if metadata:
        task_job_store.update_task_async_metadata(task_id, metadata=metadata)


def run_web_video_asr_task(task_id: str, url: str, session_id: str, *, artifact_ref: str | None = None) -> None:
    _mark_video_stage(task_id, stage="video_asr_background", progress=0.1)
    artifact_fields = _artifact_fields(artifact_ref)
    token = web_video_long_asr_confirmed.set(True)
    try:
        _mark_video_stage(task_id, stage="audio_download", progress=0.15)
        audio_started = time.perf_counter()
        audio_path, workdir, audio_error = _download_web_video_audio(url)
        audio_elapsed_ms = int((time.perf_counter() - audio_started) * 1000)
    finally:
        web_video_long_asr_confirmed.reset(token)
    if audio_error or audio_path is None:
        _record_video_failure_diagnostics(
            task_id,
            stage_timings={
                "metadata_ms": 0,
                "subtitle_ms": 0,
                "audio_ms": audio_elapsed_ms,
                "asr_ms": 0,
                "fetch_total_ms": audio_elapsed_ms,
                "draft_answer_ms": 0,
                "background_total_ms": audio_elapsed_ms,
            },
        )
        task_job_store.mark_task_failed(
            task_id,
            error_code=(audio_error or "web_video_asr_failed")[:200],
            failure_reason=f"网页视频后台音频准备失败: {audio_error or 'unknown'}",
            next_action_hint="检查 cookies、网络、视频可访问性与下载权限后重试。",
        )
        return
    try:
        _mark_video_stage(task_id, stage="segment_asr", progress=0.45)
        asr_started = time.perf_counter()
        asr_result = run_parallel_segment_asr(
            audio_path,
            session_id=session_id,
            provider_chain=resolve_video_asr_provider_chain(source_type="web_video"),
            deadline_ms=int(getattr(settings, "v16_video_sync_deadline_ms", 20000) or 20000),
            max_workers=int(getattr(settings, "v16_video_parallel_asr_workers", 6) or 6),
        )
        asr_elapsed_ms = int((time.perf_counter() - asr_started) * 1000)
    finally:
        if workdir is not None:
            from video.url_fetch_ytdlp import _safe_cleanup

            _safe_cleanup(workdir)
    if not asr_result.ok or not (asr_result.text or "").strip():
        _record_video_failure_diagnostics(
            task_id,
            stage_timings={
                "metadata_ms": 0,
                "subtitle_ms": 0,
                "audio_ms": audio_elapsed_ms,
                "asr_ms": asr_elapsed_ms,
                "fetch_total_ms": audio_elapsed_ms + asr_elapsed_ms,
                "draft_answer_ms": 0,
                "background_total_ms": audio_elapsed_ms + asr_elapsed_ms,
            },
            fetched_extra={
                "asr_provider_chain": list(resolve_video_asr_provider_chain(source_type="web_video")),
                "asr_provider_failures": list(asr_result.provider_failures or []),
                "asr_provider_attempts": list(asr_result.provider_attempts or []),
            },
        )
        task_job_store.mark_task_failed(
            task_id,
            error_code=(asr_result.error_code or "web_video_asr_failed")[:200],
            failure_reason=f"网页视频后台 ASR 失败: {asr_result.failure_reason or asr_result.error_code or 'unknown'}",
            next_action_hint="检查 provider 链、额度、网络或音频质量后重试。",
        )
        return
    text = (asr_result.text or "").strip()
    from services.capabilities.answer_draft import final_answer_fields_for_task

    _mark_video_stage(
        task_id,
        stage="answer_draft",
        progress=0.85,
        metadata={
            "video_runtime_diagnostics": {
                "audio_segment_count": asr_result.audio_segment_count,
                "audio_segmentation_mode": asr_result.audio_segmentation_mode,
                "audio_segmentation_fallback_reason": asr_result.audio_segmentation_fallback_reason,
                "silence_point_count": asr_result.silence_point_count,
                "cut_point_count": asr_result.cut_point_count,
            }
        },
    )
    draft_started = time.perf_counter()
    draft_fields = final_answer_fields_for_task(
        lane="video",
        user_query=url,
        material=text,
        title=url,
    )
    draft_elapsed_ms = int((time.perf_counter() - draft_started) * 1000)
    stage_timings = {
        "metadata_ms": 0,
        "subtitle_ms": 0,
        "audio_ms": audio_elapsed_ms,
        "asr_ms": asr_elapsed_ms,
        "fetch_total_ms": audio_elapsed_ms + asr_elapsed_ms,
        "draft_answer_ms": draft_elapsed_ms,
        "background_total_ms": audio_elapsed_ms + asr_elapsed_ms + draft_elapsed_ms,
    }
    result_summary = {
        "status": "success",
        "text_source": "asr",
        "title": url,
        "duration_sec": 0.0,
        "text_length": len(text),
        "transcript_text": text,
        "content_hash": hashlib.sha1(text.encode("utf-8")).hexdigest(),
        "stage_timings": stage_timings,
        "asr_provider": asr_result.provider or "",
        "asr_model": asr_result.model or "",
        "asr_provider_chain": list(resolve_video_asr_provider_chain(source_type="web_video")),
        "asr_provider_failures": list(asr_result.provider_failures or []),
        "asr_provider_attempts": list(asr_result.provider_attempts or []),
        "audio_segment_count": asr_result.audio_segment_count,
        "audio_segmentation_mode": asr_result.audio_segmentation_mode,
        "audio_segmentation_fallback_reason": asr_result.audio_segmentation_fallback_reason,
        "silence_point_count": asr_result.silence_point_count,
        "cut_point_count": asr_result.cut_point_count,
        **artifact_fields,
        **draft_fields,
    }
    task_job_store.mark_task_succeeded(
        task_id,
        result_summary=result_summary,
        result_source_id=url,
    )
    from tasks.orchestration.turn_stitcher import maybe_attach_task_result

    maybe_attach_task_result(
        session_id=session_id,
        task_id=task_id,
        result_summary=result_summary,
        lane="video",
    )


def run_local_video_asr_task(task_id: str, file_path: str, session_id: str, *, artifact_ref: str | None = None) -> None:
    path = Path(file_path)
    if not path.exists():
        task_job_store.mark_task_failed(task_id, error_code="file_not_found", failure_reason=f"文件不存在: {file_path}")
        return
    started = time.perf_counter()
    duration_sec = probe_local_video_duration_sec(path)
    _mark_video_stage(task_id, stage="video_asr_background", progress=0.1)
    audio_started = time.perf_counter()
    audio_path, audio_error, audio_reason, audio_hint = extract_audio_wav_for_asr(path)
    audio_elapsed_ms = int((time.perf_counter() - audio_started) * 1000)
    if audio_error or audio_path is None:
        _record_video_failure_diagnostics(
            task_id,
            stage_timings={
                "audio_ms": audio_elapsed_ms,
                "asr_ms": 0,
                "draft_answer_ms": 0,
                "background_total_ms": int((time.perf_counter() - started) * 1000),
            },
        )
        task_job_store.mark_task_failed(task_id, error_code=audio_error or "audio_extract_failed", failure_reason=audio_reason or "本地视频音轨提取失败", next_action_hint=audio_hint or "检查 ffmpeg 或视频编码格式后重试。")
        return
    _mark_video_stage(task_id, stage="segment_asr", progress=0.45)
    asr_started = time.perf_counter()
    asr_result = run_parallel_segment_asr(
        audio_path,
        session_id=session_id,
        provider_chain=resolve_video_asr_provider_chain(source_type="local_video"),
        deadline_ms=int(getattr(settings, "v16_video_sync_deadline_ms", 20000) or 20000),
        max_workers=int(getattr(settings, "v16_video_parallel_asr_workers", 6) or 6),
    )
    asr_elapsed_ms = int((time.perf_counter() - asr_started) * 1000)
    audio_path.unlink(missing_ok=True)
    if not asr_result.ok or not asr_result.text.strip():
        _record_video_failure_diagnostics(
            task_id,
            stage_timings={
                "audio_ms": audio_elapsed_ms,
                "asr_ms": asr_elapsed_ms,
                "draft_answer_ms": 0,
                "background_total_ms": int((time.perf_counter() - started) * 1000),
            },
            fetched_extra={
                "asr_provider_chain": list(resolve_video_asr_provider_chain(source_type="local_video")),
                "asr_provider_failures": list(asr_result.provider_failures or []),
                "asr_provider_attempts": list(asr_result.provider_attempts or []),
            },
        )
        task_job_store.mark_task_failed(task_id, error_code=(asr_result.error_code or "local_video_asr_failed")[:200], failure_reason=f"本地视频后台 ASR 失败: {asr_result.failure_reason or asr_result.error_code or 'unknown'}", next_action_hint="检查 ASR provider、额度、网络或音频质量后重试。")
        return
    text = asr_result.text.strip()
    artifact_fields = _artifact_fields(artifact_ref)
    from services.capabilities.answer_draft import final_answer_fields_for_task

    _mark_video_stage(
        task_id,
        stage="answer_draft",
        progress=0.85,
        metadata={
            "video_runtime_diagnostics": {
                "audio_segment_count": asr_result.audio_segment_count,
                "audio_segmentation_mode": asr_result.audio_segmentation_mode,
                "audio_segmentation_fallback_reason": asr_result.audio_segmentation_fallback_reason,
                "silence_point_count": asr_result.silence_point_count,
                "cut_point_count": asr_result.cut_point_count,
            }
        },
    )
    draft_started = time.perf_counter()
    draft_fields = final_answer_fields_for_task(
        lane="video",
        user_query=str(path),
        material=text,
        title=path.name,
    )
    draft_elapsed_ms = int((time.perf_counter() - draft_started) * 1000)
    result_summary = {
        "status": "success",
        "text_source": "asr",
        "title": path.name,
        "duration_sec": float(duration_sec or 0.0),
        "text_length": len(text),
        "transcript_text": text,
        "content_hash": hashlib.sha1(text.encode("utf-8")).hexdigest(),
        "provider": asr_result.provider,
        "model": asr_result.model,
        "stage_timings": {
            "audio_ms": audio_elapsed_ms,
            "asr_ms": asr_elapsed_ms,
            "draft_answer_ms": draft_elapsed_ms,
            "background_total_ms": int((time.perf_counter() - started) * 1000),
        },
        "asr_provider_chain": list(resolve_video_asr_provider_chain(source_type="local_video")),
        "asr_provider_failures": list(asr_result.provider_failures or []),
        "asr_provider_attempts": list(asr_result.provider_attempts or []),
        "audio_segment_count": asr_result.audio_segment_count,
        "audio_segmentation_mode": asr_result.audio_segmentation_mode,
        "audio_segmentation_fallback_reason": asr_result.audio_segmentation_fallback_reason,
        "silence_point_count": asr_result.silence_point_count,
        "cut_point_count": asr_result.cut_point_count,
        **artifact_fields,
        **draft_fields,
    }
    task_job_store.mark_task_succeeded(
        task_id,
        result_summary=result_summary,
        result_source_id=str(path),
    )
    from tasks.orchestration.turn_stitcher import maybe_attach_task_result

    maybe_attach_task_result(
        session_id=session_id,
        task_id=task_id,
        result_summary=result_summary,
        lane="video",
    )


def process_video_background_task(message: VideoTaskMessage) -> None:
    row = task_job_store.get_job(message.task_id) or {}
    meta = row.get("metadata") or {}
    if isinstance(meta, str):
        import json

        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            meta = {}
    artifact_ref = str(meta.get("artifact_ref") or "") or None
    payload = VideoBackgroundTaskPayload(
        task_id=message.task_id,
        source_type=message.source_type,
        source_ref=message.source_ref,
        session_id=message.session_id,
        artifact_ref=artifact_ref,
    )
    if payload.source_type == "web_video":
        run_web_video_asr_task(payload.task_id, payload.source_ref, payload.session_id, artifact_ref=payload.artifact_ref)
        return
    if payload.source_type == "local_video":
        run_local_video_asr_task(payload.task_id, payload.source_ref, payload.session_id, artifact_ref=payload.artifact_ref)
        return
    task_job_store.mark_task_failed(payload.task_id, error_code="unsupported_video_task", failure_reason=f"不支持的视频后台任务类型: {payload.source_type}", next_action_hint="请检查后台任务编排来源。")
