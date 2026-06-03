from __future__ import annotations

import importlib.util
from pathlib import Path

from config.settings import settings
from services.capabilities.video.parallel_asr_service import run_parallel_segment_asr
from services.capabilities.video.processing_service import (
    VideoAsrOutcome,
    VideoProbeOutcome,
    VideoProcessingRequest,
    run_video_capability,
)
from services.capabilities.video.provider_chain import resolve_video_asr_provider_chain
from services.capabilities.video.queue_dispatch import queue_web_video_asr_task
from services.capabilities.video.video_contract_runtime import (
    attach_capability_contract_metadata,
    tool_surface_status,
)
from storage import task_job_store
from tasks.orchestration.task_store import create_task_record
from tools.video.errors import (  # noqa: F401 - SUBTITLE_NOT_FOUND 为测试打桩的 re-export 锚点
    SUBTITLE_NOT_FOUND,
    VIDEO_URL_UNSUPPORTED,
    YTDLP_DEPENDENCY_MISSING,
)
from tools.video.tool_result import VideoToolResult
from tools.video.web_video_providers import run_fake_web_video_subtitle, run_ytdlp_subtitle_provider
from video.url_fetch import is_supported_video_url
from video.url_fetch_support import _pick_audio_file
from video.url_fetch_ytdlp import (
    _apply_cookies_opt,
    _new_workdir,
    _safe_cleanup,
    _yt_dlp_extract_info,
)
from video.web_video_chat_context import web_video_long_asr_confirmed


def _download_web_video_audio(url: str) -> tuple[Path | None, Path | None, str]:
    wd = _new_workdir()
    audio_outtmpl = str(wd / "%(id)s.%(ext)s")
    audio_opts: dict[str, object] = {
        "format": "bestaudio*/bestaudio/best",
        "outtmpl": audio_outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": int(settings.video_url_fetch_timeout_sec),
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        "js_runtimes": {"node": {}},
    }
    _apply_cookies_opt(audio_opts)
    try:
        _yt_dlp_extract_info(url, ydl_opts=audio_opts)
        audio_path = _pick_audio_file(wd)
        if audio_path is None:
            _safe_cleanup(wd)
            return None, None, "no_audio_file_after_download"
        return audio_path, wd, ""
    except Exception as exc:  # noqa: BLE001
        _safe_cleanup(wd)
        return None, None, f"yt_dlp_audio_failed:{type(exc).__name__}"


def run_web_video_subtitle_extract(url: str, *, session_id: str = "") -> VideoToolResult:
    task_id = create_task_record(
        task_type="extract_web_video_subtitle",
        source_type="web_video",
        session_id=session_id,
        user_query=url,
    )
    task_job_store.mark_task_running(task_id, stage="fetch_web_video")
    if not settings.v16_enable_web_video:
        task_job_store.mark_task_failed(task_id, error_code="tool_disabled", failure_reason="web video tool disabled")
        return VideoToolResult(
            tool_name="extract_web_video_subtitle",
            source_type="web_video",
            task_id=task_id,
            status="failed",
            error_code="tool_disabled",
            failure_reason="web video tool disabled",
        )
    if not is_supported_video_url(url):
        task_job_store.mark_task_failed(task_id, error_code=VIDEO_URL_UNSUPPORTED, failure_reason="URL 不在视频白名单")
        return VideoToolResult(
            tool_name="extract_web_video_subtitle",
            source_type="web_video",
            task_id=task_id,
            status="failed",
            error_code=VIDEO_URL_UNSUPPORTED,
            failure_reason="URL 不在视频白名单",
        )

    prov = (settings.v16_web_video_subtitle_provider or "yt_dlp").strip().lower()
    if prov not in ("mock", "fake") and importlib.util.find_spec("yt_dlp") is None:
        task_job_store.mark_task_failed(task_id, error_code=YTDLP_DEPENDENCY_MISSING, failure_reason="未安装 yt-dlp")
        return VideoToolResult(
            tool_name="extract_web_video_subtitle",
            source_type="web_video",
            task_id=task_id,
            status="failed",
            error_code=YTDLP_DEPENDENCY_MISSING,
            failure_reason="未安装 yt-dlp",
            next_action_hint="pip install yt-dlp 后重试",
        )

    def probe() -> VideoProbeOutcome:
        if prov in ("mock", "fake"):
            outcome = run_fake_web_video_subtitle(
                ok=True,
                text="fixture",
                subtitle_source="subtitles",
                language="zh-CN",
            )
        else:
            outcome = run_ytdlp_subtitle_provider(
                url,
                automatic_captions=bool(settings.v16_enable_web_video_automatic_caption),
            )
        return VideoProbeOutcome(
            source_type="web_video",
            source_ref=url,
            title=outcome.title or url,
            ok=bool(outcome.ok),
            text=str(outcome.text or ""),
            transcript_source=str(outcome.subtitle_source or ""),
            subtitle_format="subtitle" if outcome.ok else "",
            segments=list(getattr(outcome, "segments", None) or []),
            duration_sec=float(outcome.duration_sec or 0.0),
            duration_ms=float(outcome.duration_ms or 0.0),
            language=str(outcome.language or ""),
            provider=str(outcome.provider or ""),
            provider_type=str(outcome.provider_type or ""),
            production_ready=bool(outcome.production_ready),
            error_code=str(outcome.error_code or ""),
            failure_reason=str(outcome.failure_reason or ""),
            next_action_hint=str(outcome.next_action_hint or "请检查字幕可用性、权限或依赖配置"),
            metadata_extra={
                "url": url,
                "title": outcome.title or url,
                "webpage_url": outcome.webpage_url or url,
                "domain": (outcome.webpage_url or url).split("/")[2] if "://" in (outcome.webpage_url or url) else "",
                "platform": (outcome.webpage_url or url).split("/")[2] if "://" in (outcome.webpage_url or url) else "",
                "language": outcome.language or "",
                "subtitle_language": outcome.language or "",
                "extractor": "yt_dlp",
                "requires_cookie": False,
                "mcp_mode": "mcp_compatible_adapter",
            },
        )

    def duration_probe() -> float:
        return 0.0

    def queue_background() -> None:
        queue_web_video_asr_task(task_id=task_id, url=url, session_id=session_id)

    def run_sync_asr(remaining_budget_ms: int) -> VideoAsrOutcome:
        audio_path, workdir, audio_error = _download_web_video_audio(url)
        if audio_error or audio_path is None:
            return VideoAsrOutcome(
                ok=False,
                error_code=audio_error or "web_video_audio_failed",
                failure_reason="网页视频音频下载失败",
                next_action_hint="请检查视频 cookies、网络与下载权限。",
            )
        try:
            asr_result = run_parallel_segment_asr(
                audio_path,
                session_id=session_id,
                provider_chain=resolve_video_asr_provider_chain(source_type="web_video"),
                deadline_ms=max(1, remaining_budget_ms),
            )
        finally:
            if workdir is not None:
                _safe_cleanup(workdir)
        if asr_result.ok and (asr_result.text or "").strip():
            return VideoAsrOutcome(
                ok=True,
                text=(asr_result.text or "").strip(),
                provider=str(asr_result.provider or ""),
                model=str(asr_result.model or ""),
                segments=list(asr_result.segments or []),
                metadata_extra={
                    "provider": "yt_dlp+asr",
                    "provider_type": "web_video_parallel_asr",
                    "production_ready": True,
                    "production_capable": True,
                    "requires_cookie": False,
                    "provider_failures": list(asr_result.provider_failures or []),
                },
            )
        err = asr_result.error_code or "web_video_asr_failed"
        hint = "检查 cookies、音频下载、ASR 配置与付费开关"
        if "tencent_flash_failed" in err or "APIConnectionError" in err:
            hint = "ASR 已发起但调用失败，请检查网络、额度、SecretId / SecretKey 是否可用"
        elif "yt_dlp_audio_failed" in err or "no_audio_file_after_download" in err:
            hint = "音频下载失败，请先检查视频 cookies 是否可用"
        return VideoAsrOutcome(
            ok=False,
            error_code=err[:80],
            failure_reason="网页视频 ASR 兜底失败",
            next_action_hint=hint,
            metadata_extra={"provider_failures": list(asr_result.provider_failures or [])},
        )

    capability_outcome = run_video_capability(
        VideoProcessingRequest(
            source_type="web_video",
            source_ref=url,
            title=url,
            task_id=task_id,
            session_id=session_id,
            confirmed=bool(web_video_long_asr_confirmed.get()),
            probe=probe,
            duration_probe=duration_probe,
            queue_background=queue_background,
            run_sync_asr=run_sync_asr,
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
        tool_name="extract_web_video_subtitle",
        source_type="web_video",
        source_ref=url,
        title=processed.title or url,
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
