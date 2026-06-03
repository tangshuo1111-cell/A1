"""统一视频音频切段服务。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from config.settings import settings


@dataclass(frozen=True)
class AudioSegment:
    index: int
    file_path: Path
    start_sec: float
    end_sec: float


@dataclass(frozen=True)
class SegmentSplitResult:
    segments: list[AudioSegment]
    mode: str
    fallback_reason: str = ""
    silence_point_count: int = 0
    cut_point_count: int = 0


_SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")


def _ffprobe_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
            capture_output=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return 0.0
        payload = json.loads((proc.stdout or b"{}").decode("utf-8", errors="replace") or "{}")
        return float((payload.get("format") or {}).get("duration") or 0.0)
    except Exception:  # noqa: BLE001
        return 0.0


def _detect_silence_cut_points(path: Path) -> list[float]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    silence_noise = str(getattr(settings, "v16_video_silence_noise_db", "-35dB") or "-35dB")
    silence_min = float(getattr(settings, "v16_video_silence_min_sec", 0.6) or 0.6)
    cmd = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-i",
        str(path),
        "-af",
        f"silencedetect=n={silence_noise}:d={silence_min}",
        "-f",
        "null",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180)
    except Exception:  # noqa: BLE001
        return []
    stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
    points: list[float] = []
    for match in _SILENCE_END_RE.finditer(stderr):
        try:
            points.append(float(match.group(1)))
        except (TypeError, ValueError):
            continue
    return sorted({p for p in points if p > 0.0})


def _choose_cut_points(
    *,
    duration: float,
    target_segment_sec: int,
    max_segment_sec: int,
    silence_points: list[float],
) -> list[float]:
    if duration <= 0:
        return []
    target = max(60, min(int(target_segment_sec or 120), int(max_segment_sec or 300)))
    max_seg = max(target, int(max_segment_sec or 300))
    if duration <= target:
        return []

    cuts: list[float] = []
    current = 0.0
    silence_points = sorted([p for p in silence_points if 0.0 < p < duration])
    while (duration - current) > target:
        preferred = current + target
        max_allowed = min(current + max_seg, duration)
        candidate = None
        nearby_candidates = [
            p for p in silence_points
            if current + 60 <= p <= max_allowed
        ]
        if nearby_candidates:
            candidate = min(nearby_candidates, key=lambda p: abs(p - preferred))
        if candidate is None:
            candidate = max_allowed
        if candidate <= current:
            break
        cuts.append(candidate)
        current = candidate
    return cuts


def _single_segment(audio_path: Path, *, duration: float, mode: str, fallback_reason: str = "") -> SegmentSplitResult:
    return SegmentSplitResult(
        segments=[AudioSegment(index=0, file_path=audio_path, start_sec=0.0, end_sec=duration)],
        mode=mode,
        fallback_reason=fallback_reason,
        silence_point_count=0,
        cut_point_count=0,
    )


def _split_audio_by_points(audio_path: Path, *, cut_points: list[float], duration: float) -> SegmentSplitResult:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not cut_points:
        return _single_segment(
            audio_path,
            duration=duration,
            mode="single_segment",
            fallback_reason="ffmpeg_unavailable_or_no_cut_points",
        )
    tmp_dir = Path(tempfile.mkdtemp(prefix="video_asr_segments_"))
    out: list[AudioSegment] = []
    points = [0.0, *cut_points, duration]
    for idx in range(len(points) - 1):
        start = float(points[idx])
        end = float(points[idx + 1])
        duration_sec = max(end - start, 0.001)
        seg_path = tmp_dir / f"seg_{idx:03d}.wav"
        cmd = [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(audio_path),
            "-t",
            f"{duration_sec:.3f}",
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(seg_path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=180)
        except Exception:  # noqa: BLE001
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return _single_segment(
                audio_path,
                duration=duration,
                mode="single_segment_fallback",
                fallback_reason="segment_transcode_exception",
            )
        if proc.returncode != 0 or not seg_path.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return _single_segment(
                audio_path,
                duration=duration,
                mode="single_segment_fallback",
                fallback_reason="segment_transcode_failed",
            )
        out.append(AudioSegment(index=idx, file_path=seg_path, start_sec=start, end_sec=end))
    return SegmentSplitResult(
        segments=out,
        mode="parallel_segments",
        silence_point_count=0,
        cut_point_count=len(cut_points),
    )


def split_audio_for_parallel_asr(
    audio_path: Path,
    *,
    target_segment_sec: int | None = None,
    max_segment_sec: int | None = None,
) -> SegmentSplitResult:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return _single_segment(
            audio_path,
            duration=_ffprobe_duration(audio_path),
            mode="single_segment_fallback",
            fallback_reason="ffmpeg_unavailable",
        )
    target = int(target_segment_sec or getattr(settings, "v16_video_target_segment_sec", 120) or 120)
    max_seg = int(max_segment_sec or getattr(settings, "v16_video_max_segment_sec", 300) or 300)
    seg_sec = max(60, min(target, max_seg))
    duration = _ffprobe_duration(audio_path)
    if duration and duration <= seg_sec:
        return _single_segment(
            audio_path,
            duration=duration,
            mode="single_segment",
            fallback_reason="duration_within_target",
        )
    silence_points = _detect_silence_cut_points(audio_path)
    cut_points = _choose_cut_points(
        duration=duration,
        target_segment_sec=seg_sec,
        max_segment_sec=max_seg,
        silence_points=silence_points,
    )
    result = _split_audio_by_points(audio_path, cut_points=cut_points, duration=duration)
    return SegmentSplitResult(
        segments=result.segments,
        mode=result.mode,
        fallback_reason=result.fallback_reason,
        silence_point_count=len(silence_points),
        cut_point_count=len(cut_points),
    )
