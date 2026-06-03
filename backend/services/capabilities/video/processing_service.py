"""统一视频处理能力层。

网页视频链和本地视频链都应通过这里完成：
- 字幕 probe 成功后的同步收口
- 无字幕后的排队/同步 ASR 决策
- 统一 timing / metadata / trace 生成

工具层只负责输入适配，不在各自文件里再维护一套完整后处理逻辑。
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from config.settings import settings
from services.capabilities.contracts import CapabilityAdvice, CapabilityFact, QualityLevel
from services.capabilities.video.duration_probe import (
    should_force_video_background,
    should_queue_video_background,
)
from tools.asr import errors as asr_errors


@dataclass
class VideoProbeOutcome:
    source_type: str
    source_ref: str
    title: str
    ok: bool
    text: str = ""
    transcript_source: str = ""
    subtitle_format: str = ""
    segments: list[dict[str, Any]] = field(default_factory=list)
    duration_sec: float = 0.0
    duration_ms: float = 0.0
    language: str = ""
    provider: str = ""
    provider_type: str = ""
    production_ready: bool = False
    error_code: str = ""
    failure_reason: str = ""
    next_action_hint: str = ""
    metadata_extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoAsrOutcome:
    ok: bool
    text: str = ""
    provider: str = ""
    model: str = ""
    segments: list[dict[str, Any]] = field(default_factory=list)
    metadata_extra: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    failure_reason: str = ""
    next_action_hint: str = ""


@dataclass
class VideoProcessingResult:
    status: str
    source_type: str
    source_ref: str
    title: str
    text: str = ""
    transcript_source: str = ""
    subtitle_format: str = ""
    segments: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    failure_reason: str = ""
    next_action_hint: str = ""
    trace: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VideoCapabilityOutcome:
    fact: CapabilityFact
    advice: CapabilityAdvice
    result: VideoProcessingResult


@dataclass
class VideoProcessingRequest:
    source_type: str
    source_ref: str
    title: str
    task_id: str
    session_id: str
    confirmed: bool
    probe: Callable[[], VideoProbeOutcome]
    duration_probe: Callable[[], float]
    queue_background: Callable[[], None]
    run_sync_asr: Callable[[int], VideoAsrOutcome]
    short_threshold_reason: str = asr_errors.ASR_REQUIRES_USER_CONFIRMATION
    max_duration_error: str = "video_too_long"
    clock: Any | None = None


def _quality_level(text: str) -> str:
    return "good" if len(text) >= 40 else "usable"


def _content_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _quality_level_from_result(result: VideoProcessingResult) -> QualityLevel:
    meta = dict(result.metadata or {})
    raw = str(meta.get("quality_level") or (result.quality or {}).get("quality_level") or "usable")
    if raw in {"good", "usable", "poor", "empty"}:
        return raw  # type: ignore[return-value]
    if result.status == "success" and (result.text or "").strip():
        return "good" if len((result.text or "").strip()) >= 40 else "usable"
    if result.status == "failed":
        return "poor"
    return "usable"


def result_to_capability_pair(
    result: VideoProcessingResult,
    *,
    probe_elapsed_ms: int = 0,
) -> tuple[CapabilityFact, CapabilityAdvice]:
    meta = dict(result.metadata or {})
    probe_ms = int(meta.get("video_probe_elapsed_ms") or probe_elapsed_ms or 0)
    duration_raw = meta.get("duration_sec", meta.get("duration"))
    duration_sec = float(duration_raw) if duration_raw not in (None, "") else None

    subtitle_available: bool | None = None
    if result.status == "success":
        subtitle_available = result.transcript_source in {
            "subtitles",
            "subtitle_file",
            "embedded",
            "subtitle",
        }

    fact = CapabilityFact(
        lane="video",
        probe_elapsed_ms=probe_ms,
        duration_sec=duration_sec,
        subtitle_available=subtitle_available,
        estimated_sync_cost_ms=int(meta.get("remaining_sync_budget_ms") or 0),
        quality_level=_quality_level_from_result(result),
        artifact_ref=(str(meta.get("artifact_ref")) if meta.get("artifact_ref") else None),
        error_code=result.error_code or "",
        failure_reason=result.failure_reason or "",
        metadata={
            **meta,
            "source_type": result.source_type,
            "source_ref": result.source_ref,
            "background_task_id": meta.get("background_task_id"),
        },
    )

    if result.status == "deferred":
        advice = CapabilityAdvice(
            suggested_mode="demote_to_async",
            reason=str(meta.get("queue_reason") or "duration_over_short_threshold"),
            next_action_hint=result.next_action_hint or "",
        )
    elif result.error_code in {
        asr_errors.ASR_REQUIRES_USER_CONFIRMATION,
        "asr_requires_user_confirmation",
    }:
        advice = CapabilityAdvice(
            suggested_mode="needs_user_confirm",
            reason=result.error_code or "asr_requires_user_confirmation",
            next_action_hint=result.next_action_hint or "",
        )
    elif result.status == "failed":
        advice = CapabilityAdvice(
            suggested_mode="sync_ok",
            reason=result.error_code or "processing_failed",
            next_action_hint=result.next_action_hint or "",
        )
    else:
        advice = CapabilityAdvice(
            suggested_mode="sync_ok",
            reason="subtitle_or_asr_success" if (result.text or "").strip() else "sync_complete",
            next_action_hint=result.next_action_hint or "",
        )
    return fact, advice


def _subtitle_success_result(
    *,
    probe: VideoProbeOutcome,
    probe_elapsed_ms: int,
) -> VideoProcessingResult:
    text = (probe.text or "").strip()
    metadata = {
        "source_type": probe.source_type,
        "transcript_source": probe.transcript_source,
        "subtitle_source": probe.transcript_source,
        "subtitle_format": probe.subtitle_format,
        "duration": probe.duration_sec,
        "provider": probe.provider,
        "provider_type": probe.provider_type,
        "production_ready": probe.production_ready,
        "content_hash": _content_hash(text),
        "quality_level": _quality_level(text),
        "video_probe_elapsed_ms": probe_elapsed_ms,
        "sync_strategy": "subtitle_probe_sync",
        **dict(probe.metadata_extra or {}),
    }
    return VideoProcessingResult(
        status="success",
        source_type=probe.source_type,
        source_ref=probe.source_ref,
        title=probe.title,
        text=text,
        transcript_source=probe.transcript_source,
        subtitle_format=probe.subtitle_format,
        segments=list(probe.segments or []),
        metadata=metadata,
        quality={
            "quality_level": metadata["quality_level"],
            "text_length": len(text),
            "segment_count": len(probe.segments or []),
        },
        trace=[f"video_processing:subtitle_success source={probe.source_type}"],
    )


def run_video_processing(request: VideoProcessingRequest) -> VideoProcessingResult:
    started_at = time.perf_counter()
    probe = request.probe()
    probe_elapsed_ms = max(
        int((time.perf_counter() - started_at) * 1000),
        int(probe.duration_ms or 0),
    )

    if probe.ok:
        text = (probe.text or "").strip()
        if text:
            return _subtitle_success_result(
                probe=probe,
                probe_elapsed_ms=probe_elapsed_ms,
            )
        return VideoProcessingResult(
            status="failed",
            source_type=request.source_type,
            source_ref=request.source_ref,
            title=request.title,
            error_code="subtitle_empty",
            failure_reason="字幕抽取成功但没有可用文本",
            next_action_hint="请检查字幕源，或继续使用 ASR。",
            trace=[f"video_processing:subtitle_empty source={request.source_type}"],
        )

    duration_sec = float(probe.duration_sec or request.duration_probe() or 0.0)
    should_queue, queue_reason = should_queue_video_background(
        duration_sec=duration_sec,
        confirmed=request.confirmed,
    )
    remaining_budget_ms = max(
        0,
        int(getattr(settings, "v16_video_sync_deadline_ms", 20000) or 20000) - probe_elapsed_ms,
    )
    target_segment_sec = int(getattr(settings, "v16_video_target_segment_sec", 120) or 120)
    max_workers = int(getattr(settings, "v16_video_parallel_asr_workers", 4) or 4)
    estimated_segment_asr_ms = int(
        getattr(settings, "v16_video_estimated_segment_asr_ms", 18000) or 18000
    )
    estimated_segments = max(1, math.ceil(duration_sec / max(target_segment_sec, 1))) if duration_sec > 0 else 1
    estimated_waves = max(1, math.ceil(estimated_segments / max(max_workers, 1)))
    estimated_sync_cost_ms = estimated_waves * estimated_segment_asr_ms
    force_background, force_background_reason = should_force_video_background(
        remaining_budget_ms=remaining_budget_ms,
        probe_elapsed_ms=probe_elapsed_ms,
        source_type=request.source_type,
        subtitle_available=False,
        duration_sec=duration_sec,
        clock=request.clock,
    )

    if (
        duration_sec > 0
        and queue_reason == request.short_threshold_reason
        and not request.confirmed
    ):
        return VideoProcessingResult(
            status="failed",
            source_type=request.source_type,
            source_ref=request.source_ref,
            title=request.title,
            error_code=request.short_threshold_reason,
            failure_reason="视频超过短音频阈值，需用户确认后再走 ASR",
            next_action_hint="确认长视频可走 ASR 后重试，系统将转为后台任务。",
            metadata={
                "source_type": request.source_type,
                "duration_sec": duration_sec,
                **dict(probe.metadata_extra or {}),
            },
            trace=[f"video_processing:confirm_required source={request.source_type} duration={duration_sec:.0f}s"],
        )

    if should_queue or force_background:
        queue_reason = force_background_reason or queue_reason or "duration_over_short_threshold"
        return VideoProcessingResult(
            status="deferred",
            source_type=request.source_type,
            source_ref=request.source_ref,
            title=request.title,
            metadata={
                "source_type": request.source_type,
                "duration_sec": duration_sec,
                "background_task_id": request.task_id,
                "queue_reason": queue_reason,
                "video_probe_elapsed_ms": probe_elapsed_ms,
                "remaining_sync_budget_ms": remaining_budget_ms,
                "estimated_sync_cost_ms": estimated_sync_cost_ms,
                "estimated_audio_segment_count": estimated_segments,
                "sync_strategy": "background_after_probe",
                **dict(probe.metadata_extra or {}),
            },
            next_action_hint="视频建议转后台处理，请由 Orchestration 入队并轮询任务结果。",
            trace=[f"video_processing:deferred source={request.source_type} task_id={request.task_id}"],
        )

    asr = request.run_sync_asr(remaining_budget_ms)
    if asr.ok and (asr.text or "").strip():
        text = (asr.text or "").strip()
        metadata = {
            "source_type": request.source_type,
            "transcript_source": "asr",
            "subtitle_source": "asr",
            "subtitle_format": "asr",
            "provider": asr.provider,
            "model": asr.model,
            "duration": duration_sec,
            "content_hash": _content_hash(text),
            "quality_level": _quality_level(text),
            "video_probe_elapsed_ms": probe_elapsed_ms,
            "remaining_sync_budget_ms": remaining_budget_ms,
            "estimated_sync_cost_ms": estimated_sync_cost_ms,
            "estimated_audio_segment_count": estimated_segments,
            "sync_strategy": "sync_asr_after_probe",
            **dict(probe.metadata_extra or {}),
            **dict(asr.metadata_extra or {}),
        }
        return VideoProcessingResult(
            status="success",
            source_type=request.source_type,
            source_ref=request.source_ref,
            title=request.title,
            text=text,
            transcript_source="asr",
            subtitle_format="asr",
            segments=list(asr.segments or []),
            metadata=metadata,
            quality={
                "quality_level": metadata["quality_level"],
                "text_length": len(text),
                "segment_count": len(asr.segments or []),
            },
            trace=[f"video_processing:asr_success source={request.source_type} provider={asr.provider}"],
        )

    return VideoProcessingResult(
        status="failed",
        source_type=request.source_type,
        source_ref=request.source_ref,
        title=request.title,
        error_code=asr.error_code or probe.error_code or "asr_failed",
        failure_reason=asr.failure_reason or probe.failure_reason or "ASR 失败",
        next_action_hint=asr.next_action_hint or probe.next_action_hint or "请检查字幕、音频与 ASR 配置。",
        metadata={
            "source_type": request.source_type,
            "duration_sec": duration_sec,
            "video_probe_elapsed_ms": probe_elapsed_ms,
            "remaining_sync_budget_ms": remaining_budget_ms,
            **dict(probe.metadata_extra or {}),
            **dict(asr.metadata_extra or {}),
        },
        trace=[f"video_processing:failed source={request.source_type} error={asr.error_code or probe.error_code or 'asr_failed'}"],
    )


def run_video_capability(
    request: VideoProcessingRequest,
    *,
    clock: Any | None = None,
) -> VideoCapabilityOutcome:
    if clock is not None:
        request = replace(request, clock=clock)
    result = run_video_processing(request)
    probe_ms = int((result.metadata or {}).get("video_probe_elapsed_ms") or 0)
    fact, advice = result_to_capability_pair(result, probe_elapsed_ms=probe_ms)
    return VideoCapabilityOutcome(fact=fact, advice=advice, result=result)
