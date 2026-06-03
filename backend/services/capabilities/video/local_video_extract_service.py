from __future__ import annotations

from pathlib import Path

import tools.asr  # noqa: F401
from config.settings import settings
from services.capabilities.video.audio_service import extract_audio_wav_for_asr
from services.capabilities.video.duration_probe import probe_local_video_duration_sec
from services.capabilities.video.parallel_asr_service import run_parallel_segment_asr
from services.capabilities.video.processing_service import (
    VideoAsrOutcome,
    VideoProbeOutcome,
    VideoProcessingRequest,
    run_video_capability,
)
from services.capabilities.video.provider_chain import resolve_video_asr_provider_chain
from services.capabilities.video.queue_dispatch import queue_local_video_asr_task
from services.capabilities.video.video_contract_runtime import (
    attach_capability_contract_metadata,
    tool_surface_status,
)
from storage import task_job_store
from tasks.orchestration.task_store import create_task_record
from tools.asr import errors as asr_errors
from tools.video.embedded_subtitle import extract_embedded_subtitle
from tools.video.errors import SUBTITLE_PARSE_FAILED
from tools.video.subtitle_parser import parse_subtitle_file, subtitle_segments_to_text
from tools.video.tool_result import VideoToolResult
from video.web_video_chat_context import web_video_long_asr_confirmed


def run_local_video_subtitle_extract(file_path: str, *, session_id: str = "") -> VideoToolResult:
    task_id = create_task_record(
        task_type="extract_local_video_subtitle",
        source_type="local_video",
        session_id=session_id,
        user_query=file_path,
    )
    task_job_store.mark_task_running(task_id, stage="subtitle_lookup")
    path = Path(file_path)
    if not settings.v16_enable_local_video:
        task_job_store.mark_task_failed(task_id, error_code="tool_disabled", failure_reason="local video tool disabled")
        return VideoToolResult(
            tool_name="extract_local_video_subtitle",
            source_type="local_video",
            task_id=task_id,
            status="failed",
            error_code="tool_disabled",
            failure_reason="local video tool disabled",
        )
    if not path.exists():
        task_job_store.mark_task_failed(task_id, error_code="file_not_found", failure_reason=f"文件不存在: {file_path}")
        return VideoToolResult(
            tool_name="extract_local_video_subtitle",
            source_type="local_video",
            source_ref=str(path),
            title=path.name or str(path),
            task_id=task_id,
            status="failed",
            error_code="file_not_found",
            failure_reason=f"文件不存在: {file_path}",
            next_action_hint="请确认本地 MP4 路径，或先成功下载文件后再重试",
            trace=["v16:video:local file_missing"],
        )

    def probe() -> VideoProbeOutcome:
        candidates = [path.with_suffix(".srt"), path.with_suffix(".vtt"), path.with_suffix(".txt")]
        subtitle_path = next((cand for cand in candidates if cand.exists()), None)
        if subtitle_path is not None:
            try:
                segments, subtitle_format = parse_subtitle_file(subtitle_path)
            except (ValueError, OSError, UnicodeDecodeError) as e:
                return VideoProbeOutcome(
                    source_type="local_video",
                    source_ref=str(path),
                    title=path.name,
                    ok=False,
                    error_code=SUBTITLE_PARSE_FAILED,
                    failure_reason=f"字幕解析失败: {e}",
                    next_action_hint="请检查字幕文件内容，或后续使用 ASR",
                    metadata_extra={"filename": path.name, "file_ext": path.suffix.lower()},
                )
            text = subtitle_segments_to_text(segments)
            return VideoProbeOutcome(
                source_type="local_video",
                source_ref=str(path),
                title=path.name,
                ok=bool(text),
                text=text,
                transcript_source="subtitle_file",
                subtitle_format=subtitle_format,
                segments=list(segments or []),
                duration_sec=segments[-1]["end_time"] if segments else 0.0,
                metadata_extra={
                    "filename": path.name,
                    "file_ext": path.suffix.lower(),
                    "extract_method": "subtitle_sidecar",
                    "parser_name": "extract_local_video_subtitle",
                },
                error_code="" if text else "subtitle_empty",
                failure_reason="" if text else "字幕文件存在但没有可用文本",
                next_action_hint="请检查字幕文件内容，或后续使用 ASR",
            )
        emb = extract_embedded_subtitle(path)
        if emb.ok:
            return VideoProbeOutcome(
                source_type="local_video",
                source_ref=str(path),
                title=path.name,
                ok=True,
                text=emb.text,
                transcript_source="embedded",
                subtitle_format=emb.subtitle_format,
                segments=list(emb.segments or []),
                duration_ms=float(emb.duration_ms or 0.0),
                metadata_extra={
                    "filename": path.name,
                    "file_ext": path.suffix.lower(),
                    "extract_method": "subtitle_embedded",
                    "embedded_stream_index": emb.stream_index,
                    "parser_name": "extract_local_video_subtitle",
                },
            )
        return VideoProbeOutcome(
            source_type="local_video",
            source_ref=str(path),
            title=path.name,
            ok=False,
            error_code=str(emb.error_code or ""),
            failure_reason=str(emb.failure_reason or ""),
            next_action_hint=str(emb.next_action_hint or "请提供 .srt/.vtt/.txt 字幕，或使用 ASR"),
            metadata_extra={
                "filename": path.name,
                "file_ext": path.suffix.lower(),
                "embedded_error_code": emb.error_code,
                "embedded_failure_reason": emb.failure_reason,
            },
        )

    def duration_probe() -> float:
        return probe_local_video_duration_sec(path)

    def queue_background() -> None:
        queue_local_video_asr_task(task_id=task_id, file_path=str(path), session_id=session_id)

    def run_sync_asr(remaining_budget_ms: int) -> VideoAsrOutcome:
        audio_path, audio_error, audio_reason, audio_hint = extract_audio_wav_for_asr(path)
        if audio_error or audio_path is None:
            return VideoAsrOutcome(
                ok=False,
                error_code=audio_error or "audio_extract_failed",
                failure_reason=audio_reason or "本地视频音轨提取失败",
                next_action_hint=audio_hint or "检查 ffmpeg 或视频编码格式后重试。",
            )
        try:
            asr_result = run_parallel_segment_asr(
                audio_path,
                session_id=session_id,
                provider_chain=resolve_video_asr_provider_chain(source_type="local_video"),
                deadline_ms=max(1, remaining_budget_ms),
            )
        finally:
            audio_path.unlink(missing_ok=True)
        if asr_result.ok and (asr_result.text or "").strip():
            return VideoAsrOutcome(
                ok=True,
                text=(asr_result.text or "").strip(),
                provider=str(asr_result.provider or ""),
                model=str(asr_result.model or ""),
                segments=list(asr_result.segments or []),
                metadata_extra={"provider_failures": list(asr_result.provider_failures or [])},
            )
        return VideoAsrOutcome(
            ok=False,
            error_code=str(asr_result.error_code or "asr_failed"),
            failure_reason=str(asr_result.failure_reason or "本地视频后台 ASR 失败"),
            next_action_hint=str(asr_result.next_action_hint or "检查 ASR provider、额度、网络或改用字幕文件。"),
            metadata_extra={"provider_failures": list(asr_result.provider_failures or [])},
        )

    capability_outcome = run_video_capability(
        VideoProcessingRequest(
            source_type="local_video",
            source_ref=str(path),
            title=path.name,
            task_id=task_id,
            session_id=session_id,
            confirmed=bool(web_video_long_asr_confirmed.get()),
            probe=probe,
            duration_probe=duration_probe,
            queue_background=queue_background,
            run_sync_asr=run_sync_asr,
            short_threshold_reason=asr_errors.ASR_REQUIRES_USER_CONFIRMATION,
        )
    )
    processed = capability_outcome.result
    if capability_outcome.advice.suggested_mode == "demote_to_async":
        queue_background()
    metadata = dict(processed.metadata or {})
    metadata = attach_capability_contract_metadata(
        metadata, capability_outcome.fact, capability_outcome.advice
    )
    surface_status = tool_surface_status(
        legacy_status=processed.status, advice=capability_outcome.advice
    )

    if surface_status == "success":
        task_job_store.mark_task_succeeded(
            task_id,
            result_summary={
                "status": "success",
                "text_source": processed.transcript_source,
                "segments": len(processed.segments or []),
            },
        )
    elif surface_status != "queued":
        task_job_store.mark_task_failed(
            task_id,
            error_code=processed.error_code,
            failure_reason=processed.failure_reason,
            next_action_hint=processed.next_action_hint,
        )

    return VideoToolResult(
        tool_name="extract_local_video_subtitle",
        source_type="local_video",
        source_ref=str(path),
        title=processed.title or path.name,
        transcript_source=processed.transcript_source,
        subtitle_format=processed.subtitle_format,
        segments=list(processed.segments or []),
        task_id=task_id,
        status=surface_status,
        text=processed.text,
        metadata=metadata,
        quality=dict(processed.quality or {}),
        error_code=processed.error_code,
        failure_reason=processed.failure_reason,
        next_action_hint=processed.next_action_hint,
        trace=list(processed.trace or []),
    )
