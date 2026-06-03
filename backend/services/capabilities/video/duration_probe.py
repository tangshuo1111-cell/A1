from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

from config.feature_flags import is_enabled
from config.settings import settings
from tools.video.errors import VIDEO_TOO_LONG


def probe_local_video_duration_sec(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        proc = subprocess.run([ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", str(path)], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0.0
    if proc.returncode != 0:
        return 0.0
    try:
        payload = json.loads((proc.stdout or b"{}").decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        return 0.0
    fmt = payload.get("format") or {}
    try:
        return float(fmt.get("duration") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def should_queue_video_background(*, duration_sec: float, confirmed: bool) -> tuple[bool, str]:
    short_thr = int(getattr(settings, "v16_asr_short_threshold_sec", 900) or 900)
    long_thr = int(getattr(settings, "v16_asr_long_threshold_sec", 7200) or 7200)
    if not duration_sec or duration_sec <= 0:
        return False, ""
    if duration_sec > long_thr:
        return False, VIDEO_TOO_LONG
    if duration_sec > short_thr:
        return confirmed, "asr_requires_user_confirmation"
    return False, ""


def should_force_video_background(
    *,
    remaining_budget_ms: int,
    probe_elapsed_ms: int,
    source_type: str,
    subtitle_available: bool,
    duration_sec: float,
    clock: Any | None = None,
) -> tuple[bool, str]:
    if subtitle_available:
        return False, ""
    if clock is not None:
        if is_enabled("ENABLE_BUDGET_CLOCK_V2"):
            remaining_budget_ms = clock.remaining_ms()
            sync_asr_budget_ms = clock.child_budget(
                int(getattr(settings, "v16_video_sync_asr_budget_ms", 9000) or 9000)
            )
            probe_budget_ms = clock.child_budget(
                int(getattr(settings, "v16_video_probe_budget_ms", 6000) or 6000)
            )
        else:
            sync_asr_budget_ms = int(getattr(settings, "v16_video_sync_asr_budget_ms", 9000) or 9000)
            probe_budget_ms = int(getattr(settings, "v16_video_probe_budget_ms", 6000) or 6000)
    else:
        sync_asr_budget_ms = int(getattr(settings, "v16_video_sync_asr_budget_ms", 9000) or 9000)
        probe_budget_ms = int(getattr(settings, "v16_video_probe_budget_ms", 6000) or 6000)
    if remaining_budget_ms <= 0:
        return True, "deadline_exhausted"
    if probe_elapsed_ms >= probe_budget_ms:
        return True, "probe_budget_exceeded"
    if remaining_budget_ms <= sync_asr_budget_ms:
        return True, "remaining_budget_low"
    if duration_sec > 0:
        target_segment_sec = int(getattr(settings, "v16_video_target_segment_sec", 120) or 120)
        max_workers = int(getattr(settings, "v16_video_parallel_asr_workers", 4) or 4)
        estimated_segment_asr_ms = int(
            getattr(settings, "v16_video_estimated_segment_asr_ms", 18000) or 18000
        )
        estimated_segments = max(1, math.ceil(duration_sec / max(target_segment_sec, 1)))
        estimated_waves = max(1, math.ceil(estimated_segments / max(max_workers, 1)))
        estimated_sync_cost_ms = estimated_waves * estimated_segment_asr_ms
        if estimated_sync_cost_ms >= remaining_budget_ms:
            return True, "estimated_sync_cost_over_budget"
    _ = source_type
    return False, ""
