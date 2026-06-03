"""
V16 R4-C：内嵌字幕提取（ffprobe 探测 + ffmpeg 导出 SRT 文本）。

不在模块 import 时依赖 ffprobe/ffmpeg；通过 shutil.which + subprocess 运行时检测。
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.video import errors as video_errors
from tools.video.subtitle_parser import parse_subtitle_file, subtitle_segments_to_text

logger = logging.getLogger("light_maqa")

RunCmd = Callable[..., subprocess.CompletedProcess[bytes]]


def _default_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(cmd, **kwargs)


def find_first_subtitle_stream_index(ffprobe_json: dict[str, Any]) -> int | None:
    streams = ffprobe_json.get("streams")
    if not isinstance(streams, list):
        return None
    for s in streams:
        if not isinstance(s, dict):
            continue
        if s.get("codec_type") != "subtitle":
            continue
        try:
            return int(s.get("index", -1))
        except (TypeError, ValueError):
            continue
    return None


@dataclass
class EmbeddedSubtitleOutcome:
    ok: bool
    text: str = ""
    segments: list[dict[str, Any]] = field(default_factory=list)
    subtitle_format: str = "srt"
    stream_index: int = -1
    error_code: str = ""
    failure_reason: str = ""
    next_action_hint: str = ""
    duration_ms: float = 0.0


def extract_embedded_subtitle(
    video_path: Path,
    *,
    run_cmd: RunCmd | None = None,
) -> EmbeddedSubtitleOutcome:
    import time

    t0 = time.perf_counter()
    run = run_cmd or _default_run
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return EmbeddedSubtitleOutcome(
            ok=False,
            error_code=video_errors.FFPROBE_DEPENDENCY_MISSING,
            failure_reason="未找到 ffprobe 可执行文件",
            next_action_hint="安装 FFmpeg 并把 ffprobe 加入 PATH",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return EmbeddedSubtitleOutcome(
            ok=False,
            error_code=video_errors.FFMPEG_DEPENDENCY_MISSING,
            failure_reason="未找到 ffmpeg 可执行文件",
            next_action_hint="安装 FFmpeg 并把 ffmpeg 加入 PATH",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    try:
        proc = run(
            [
                ffprobe,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                str(video_path),
            ],
            capture_output=True,
            timeout=60,
        )
    except (OSError, ValueError, RuntimeError) as e:  # noqa: BLE001
        logger.warning("ffprobe failed: %s", e)
        return EmbeddedSubtitleOutcome(
            ok=False,
            error_code=video_errors.EMBEDDED_SUBTITLE_EXTRACT_FAILED,
            failure_reason=f"ffprobe 执行失败: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    if proc.returncode != 0:
        return EmbeddedSubtitleOutcome(
            ok=False,
            error_code=video_errors.EMBEDDED_SUBTITLE_EXTRACT_FAILED,
            failure_reason=(proc.stderr or b"").decode("utf-8", errors="replace")[:500] or "ffprobe 非零退出",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    try:
        meta = json.loads(proc.stdout.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        return EmbeddedSubtitleOutcome(
            ok=False,
            error_code=video_errors.EMBEDDED_SUBTITLE_EXTRACT_FAILED,
            failure_reason="ffprobe 输出非 JSON",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    idx = find_first_subtitle_stream_index(meta)
    if idx is None:
        return EmbeddedSubtitleOutcome(
            ok=False,
            error_code=video_errors.EMBEDDED_SUBTITLE_NOT_FOUND,
            failure_reason="未检测到内嵌字幕轨道",
            next_action_hint="使用 sidecar 字幕或 ASR",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    try:
        proc2 = run(
            [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(video_path),
                "-map",
                f"0:{idx}",
                "-f",
                "srt",
                "pipe:1",
            ],
            capture_output=True,
            timeout=120,
        )
    except (OSError, ValueError, RuntimeError) as e:  # noqa: BLE001
        return EmbeddedSubtitleOutcome(
            ok=False,
            error_code=video_errors.EMBEDDED_SUBTITLE_EXTRACT_FAILED,
            failure_reason=f"ffmpeg 执行失败: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    if proc2.returncode != 0:
        return EmbeddedSubtitleOutcome(
            ok=False,
            error_code=video_errors.EMBEDDED_SUBTITLE_EXTRACT_FAILED,
            failure_reason=(proc2.stderr or b"").decode("utf-8", errors="replace")[:500] or "ffmpeg 提取字幕失败",
            next_action_hint="检查字幕编码或容器格式",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    raw = (proc2.stdout or b"").decode("utf-8", errors="replace").strip()
    if not raw:
        return EmbeddedSubtitleOutcome(
            ok=False,
            error_code=video_errors.EMBEDDED_SUBTITLE_EMPTY,
            failure_reason="ffmpeg 导出字幕为空",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".srt", delete=False, encoding="utf-8") as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        segments, subtitle_format = parse_subtitle_file(tmp_path)
    except (OSError, ValueError, RuntimeError) as e:  # noqa: BLE001
        Path(tmp_path).unlink(missing_ok=True)
        return EmbeddedSubtitleOutcome(
            ok=False,
            error_code=video_errors.EMBEDDED_SUBTITLE_EXTRACT_FAILED,
            failure_reason=f"解析导出 SRT 失败: {e}",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    Path(tmp_path).unlink(missing_ok=True)
    text = subtitle_segments_to_text(segments)
    if not text:
        return EmbeddedSubtitleOutcome(
            ok=False,
            error_code=video_errors.EMBEDDED_SUBTITLE_EMPTY,
            failure_reason="内嵌字幕解析后无文本",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    return EmbeddedSubtitleOutcome(
        ok=True,
        text=text,
        segments=[dict(s) for s in segments],
        subtitle_format=subtitle_format,
        stream_index=idx,
        duration_ms=(time.perf_counter() - t0) * 1000.0,
    )
