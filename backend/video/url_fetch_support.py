"""探测元数据、ASR 时长门闸、音频文件与 basename 辅助。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from config.settings import settings

from .fetch_result import FetchVideoResult
from .url_fetch_ytdlp import (
    _apply_cookies_opt,
    _describe_extract_error,
    _new_workdir,
    _safe_cleanup,
    _yt_dlp_extract_info,
)
from .url_validate import is_supported_video_url

logger = logging.getLogger("light_maqa")


def web_video_asr_duration_gate(
    duration_sec: float,
    *,
    cookies_used: str,
    source_url: str,
    title: str,
    source_basename: str,
) -> FetchVideoResult | None:
    """字幕缺席、即将走 ASR 前的时长策略：通过返回 None；否则返回 failure。"""
    from video.web_video_chat_context import web_video_long_asr_confirmed

    d = float(duration_sec or 0.0)
    auto_max = int(getattr(settings, "v16_web_video_asr_fallback_max_sec", 900) or 900)
    abs_max = int(getattr(settings, "v16_web_video_asr_abs_max_sec", 7200) or 7200)
    effective_max = min(int(settings.video_max_audio_seconds), abs_max)
    ex: dict[str, Any] = {
        "cookies": cookies_used,
        "asr_auto_max_sec": auto_max,
        "asr_effective_max_sec": effective_max,
        "asr_abs_max_sec": abs_max,
    }
    if d > effective_max:
        return FetchVideoResult.failure(
            stage="audio",
            error=f"duration_exceeds_limit:{d:.0f}s>max:{effective_max}s",
            source_url=source_url,
            title=title,
            source_basename=source_basename,
            duration_sec=d,
            extra=ex,
        )
    if d > auto_max and not web_video_long_asr_confirmed.get():
        return FetchVideoResult.failure(
            stage="policy",
            error="web_video_asr_needs_confirmation",
            source_url=source_url,
            title=title,
            source_basename=source_basename,
            duration_sec=d,
            extra={**ex, "duration_sec": d},
        )
    return None


def probe_web_video_metadata(url: str) -> dict[str, Any]:
    """yt-dlp 仅取元数据（skip_download），供 /video/metadata 与前端确认长视频。"""
    if not is_supported_video_url(url):
        return {"ok": False, "error": "url_not_in_whitelist"}
    try:
        url.encode("ascii")
    except (UnicodeEncodeError, AttributeError):
        bad_chars = "".join(sorted({c for c in (url or "") if ord(c) > 127}))[:32]
        return {"ok": False, "error": f"url_contains_non_ascii:{bad_chars}"}

    auto_max = int(getattr(settings, "v16_web_video_asr_fallback_max_sec", 900) or 900)
    abs_max = int(getattr(settings, "v16_web_video_asr_abs_max_sec", 7200) or 7200)
    effective_max = min(int(settings.video_max_audio_seconds), abs_max)
    wd = _new_workdir()
    cookies_used = "none"
    try:
        sub_outtmpl = str(wd / "%(id)s.%(ext)s")
        sub_opts: dict[str, Any] = {
            "skip_download": True,
            "ignore_no_formats_error": True,
            "outtmpl": sub_outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "socket_timeout": int(settings.video_url_fetch_timeout_sec),
            "js_runtimes": {"node": {}},
        }
        cookies_used = _apply_cookies_opt(sub_opts)
        info = _yt_dlp_extract_info(url, ydl_opts=sub_opts) or {}
        duration = float(info.get("duration") or 0.0)
        title = str(info.get("title") or "").strip()
        return {
            "ok": True,
            "duration_sec": duration,
            "title": title,
            "asr_auto_max_sec": auto_max,
            "asr_effective_max_sec": effective_max,
            "asr_abs_max_sec": abs_max,
            "cookies": cookies_used,
        }
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:  # noqa: BLE001
        logger.warning(
            "probe_web_video_metadata failed url=%s cookies=%s err=%r",
            url,
            cookies_used,
            e,
            exc_info=True,
        )
        return {
            "ok": False,
            "error": _describe_extract_error(e),
            "cookies": cookies_used,
            "asr_auto_max_sec": auto_max,
            "asr_effective_max_sec": effective_max,
            "asr_abs_max_sec": abs_max,
        }
    finally:
        _safe_cleanup(wd)


def _pick_audio_file(workdir: Path) -> Path | None:
    """yt-dlp 下载完 audio-only 后，挑出实际产出的音频文件。"""
    for ext in ("m4a", "mp3", "webm", "opus", "ogg", "wav", "aac"):
        for p in workdir.glob(f"*.{ext}"):
            if p.is_file() and p.stat().st_size > 0:
                return p
    candidates = [
        p for p in workdir.iterdir()
        if p.is_file() and p.suffix.lower() not in (".vtt", ".srt", ".json", ".info")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_size)


def _basename_from_info(info: dict[str, Any], url: str) -> str:
    """优先用 yt-dlp 抓到的 video id；退到 URL 末段。"""
    vid = (info.get("id") or info.get("display_id") or "").strip()
    if vid:
        return f"{vid}.video"
    return _basename_from_url(url)


def _basename_from_url(url: str) -> str:
    try:
        u = urlparse(url)
        host = (u.hostname or "url").replace(".", "_")
        last = (u.path.rsplit("/", 1)[-1] or "video").strip() or "video"
        if "." not in last:
            last += ".video"
        return f"{host}_{last}"
    except (ValueError, TypeError):
        return "video.video"
