"""统一视频分段并发 ASR 服务。"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from services.capabilities.video.segment_service import (
    AudioSegment,
    SegmentSplitResult,
    split_audio_for_parallel_asr,
)
from tools.asr import registry as asr_registry
from workers.pools.video_worker_pool import run_in_video_worker_pool


@dataclass(frozen=True)
class ParallelAsrResult:
    ok: bool
    text: str
    provider: str
    model: str
    segments: list[dict]
    error_code: str = ""
    failure_reason: str = ""
    next_action_hint: str = ""
    provider_failures: list[dict] | None = None
    provider_attempts: list[dict] | None = None
    audio_segment_count: int = 0
    audio_segmentation_mode: str = "single_segment"
    audio_segmentation_fallback_reason: str = ""
    silence_point_count: int = 0
    cut_point_count: int = 0


def _cleanup_segments(audio_path: Path, segs: Iterable[AudioSegment]) -> None:
    seg_list = list(segs)
    for seg in seg_list:
        if seg.file_path != audio_path:
            seg.file_path.unlink(missing_ok=True)
    for seg in seg_list:
        parent = seg.file_path.parent
        if parent != audio_path.parent and parent.exists():
            shutil.rmtree(parent, ignore_errors=True)


def run_parallel_segment_asr(
    audio_path: Path,
    *,
    session_id: str,
    provider_chain: list[str] | tuple[str, ...],
    deadline_ms: int,
    target_segment_sec: int = 120,
    max_segment_sec: int = 300,
    max_workers: int = 4,
) -> ParallelAsrResult:
    split_result = split_audio_for_parallel_asr(
        audio_path,
        target_segment_sec=target_segment_sec,
        max_segment_sec=max_segment_sec,
    )
    if isinstance(split_result, list):
        segs = split_result
        split_meta = SegmentSplitResult(segments=segs, mode="parallel_segments")
    else:
        split_meta = split_result
        segs = split_meta.segments

    def _run_one(seg: AudioSegment):
        result = asr_registry.call_tool(
            "asr_transcribe",
            file_path=str(seg.file_path),
            session_id=session_id,
            provider_chain=provider_chain,
            deadline_ms=deadline_ms,
            force_sync=True,
            user_confirmed=True,
        )
        return seg, result

    results: list[tuple[AudioSegment, object]] = []
    try:
        results.extend(
            run_in_video_worker_pool(
                segs,
                _run_one,
                max_workers=max_workers,
                thread_name_prefix="video-seg-asr",
            )
        )
    finally:
        _cleanup_segments(audio_path, segs)

    ordered = sorted(results, key=lambda item: item[0].index)
    text_parts: list[str] = []
    merged_segments: list[dict] = []
    provider = ""
    model = ""
    failures: list[dict] = []
    attempts: list[dict] = []
    for seg, result in ordered:
        status = getattr(result, "status", "")
        result_meta = dict(getattr(result, "metadata", {}) or {})
        raw_attempts = list(result_meta.get("provider_attempts") or [])
        for raw in raw_attempts:
            attempts.append({"segment_index": seg.index, **dict(raw)})
        if status != "success" or not (getattr(result, "text", "") or "").strip():
            failures.append(
                {
                    "index": seg.index,
                    "error_code": getattr(result, "error_code", "") or "segment_failed",
                    "failure_reason": getattr(result, "failure_reason", "") or "segment_failed",
                }
            )
            continue
        provider = provider or str(result_meta.get("provider") or "")
        model = model or str(result_meta.get("provider_type") or "")
        part = (getattr(result, "text", "") or "").strip()
        if part:
            text_parts.append(part)
        raw_segments = list((getattr(result, "structured_data", {}) or {}).get("segments", []))
        if raw_segments:
            for raw in raw_segments:
                merged_segments.append(
                    {
                        **dict(raw),
                        "start_time": float(raw.get("start_time", 0.0) or 0.0) + seg.start_sec,
                        "end_time": float(raw.get("end_time", 0.0) or 0.0) + seg.start_sec,
                    }
                )
        elif part:
            merged_segments.append(
                {
                    "start_time": seg.start_sec,
                    "end_time": seg.end_sec,
                    "text": part,
                }
            )
    if text_parts:
        return ParallelAsrResult(
            ok=True,
            text="\n".join(text_parts).strip(),
            provider=provider,
            model=model,
            segments=merged_segments,
            provider_failures=failures,
            provider_attempts=attempts,
            audio_segment_count=len(segs),
            audio_segmentation_mode=split_meta.mode,
            audio_segmentation_fallback_reason=split_meta.fallback_reason,
            silence_point_count=split_meta.silence_point_count,
            cut_point_count=split_meta.cut_point_count,
        )
    first_failure = failures[0] if failures else {}
    return ParallelAsrResult(
        ok=False,
        text="",
        provider=provider,
        model=model,
        segments=[],
        error_code=str(first_failure.get("error_code") or "parallel_asr_failed"),
        failure_reason=str(first_failure.get("failure_reason") or "parallel_asr_failed"),
        next_action_hint="请检查 ASR provider、网络、额度或音频切段结果。",
        provider_failures=failures,
        provider_attempts=attempts,
        audio_segment_count=len(segs),
        audio_segmentation_mode=split_meta.mode,
        audio_segmentation_fallback_reason=split_meta.fallback_reason,
        silence_point_count=split_meta.silence_point_count,
        cut_point_count=split_meta.cut_point_count,
    )
