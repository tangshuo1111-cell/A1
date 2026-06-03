"""`fetch_video_text` 主链：字幕优先，无字幕走 ASR。"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from config.settings import settings

from .fetch_result import FetchVideoResult
from .subtitle_text import _read_subtitle_text_from_files
from .url_fetch_support import (
    _basename_from_info,
    _basename_from_url,
    _pick_audio_file,
    web_video_asr_duration_gate,
)
from .url_fetch_ytdlp import (
    _apply_cookies_opt,
    _describe_extract_error,
    _new_workdir,
    _safe_cleanup,
    _yt_dlp_extract_info,
)
from .url_validate import is_supported_video_url

logger = logging.getLogger("light_maqa")


def fetch_video_text(
    url: str,
    *,
    prefer_subtitles: bool = True,
    allow_asr: bool = True,
    workdir: Path | None = None,
    extract_info: Any = None,
    transcribe: Any = None,
) -> FetchVideoResult:
    """V11 R1 主链：URL → 文本。

    流程（任何一步失败都返回 FetchVideoResult.failure）：
        0. 域名白名单校验
        1. yt-dlp 抓字幕 + 视频元数据（首选 subtitles → 退到 automatic_captions）
        2. 字幕拿到 → 直接返回 ok_subtitle
        3. 字幕没拿到 → 改下 audio-only → 调云 ASR → 返回 ok_asr
        4. 不允许 ASR / ASR 不可用 / ASR 失败 → 返回 failure
    """
    started_at = time.perf_counter()

    if not is_supported_video_url(url):
        return FetchVideoResult.failure(
            stage="domain",
            error="url_not_in_whitelist",
            source_url=url or "",
        )

    try:
        url.encode("ascii")
    except (UnicodeEncodeError, AttributeError):
        bad_chars = "".join(sorted({c for c in (url or "") if ord(c) > 127}))[:32]
        return FetchVideoResult.failure(
            stage="domain",
            error=f"url_contains_non_ascii:{bad_chars}",
            source_url=url or "",
        )

    own_workdir = workdir is None
    wd: Path = workdir if workdir is not None else _new_workdir()
    extract_fn = extract_info or _yt_dlp_extract_info
    cookies_used = "none"

    info: dict[str, Any] = {}
    sub_text = ""
    sub_lang = ""
    metadata_ms = 0
    subtitle_ms = 0
    audio_ms = 0
    asr_ms = 0
    if prefer_subtitles:
        sub_outtmpl = str(wd / "%(id)s.%(ext)s")
        sub_opts: dict[str, Any] = {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["zh-CN", "zh", "zh-Hans", "en", "en-US"],
            "subtitlesformat": "vtt/srt/best",
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
        try:
            _t_meta = time.perf_counter()
            info = extract_fn(url, ydl_opts=sub_opts) or {}
            metadata_ms = int((time.perf_counter() - _t_meta) * 1000)
        except (OSError, ValueError, RuntimeError, TimeoutError) as e:  # noqa: BLE001
            metadata_ms = int((time.perf_counter() - _t_meta) * 1000) if "_t_meta" in locals() else 0
            logger.warning(
                "v11 video url metadata stage failed url=%s cookies=%s err=%r",
                url, cookies_used, e, exc_info=True,
            )
            if own_workdir:
                _safe_cleanup(wd)
            return FetchVideoResult.failure(
                stage="metadata",
                error=f"yt_dlp_metadata_failed:{_describe_extract_error(e)}",
                source_url=url,
                extra={
                    "cookies": cookies_used,
                    "metadata_ms": metadata_ms,
                    "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
                },
            )
        try:
            _t_sub = time.perf_counter()
            sub_text, sub_lang = _read_subtitle_text_from_files(info, wd)
            subtitle_ms = int((time.perf_counter() - _t_sub) * 1000)
        except (OSError, ValueError, RuntimeError, TimeoutError):  # noqa: BLE001
            subtitle_ms = int((time.perf_counter() - _t_sub) * 1000) if "_t_sub" in locals() else 0
            sub_text, sub_lang = "", ""

    title = str(info.get("title") or "").strip() or _basename_from_url(url)
    duration = float(info.get("duration") or 0.0)
    source_basename = _basename_from_info(info, url)

    if sub_text:
        if own_workdir:
            _safe_cleanup(wd)
        result = FetchVideoResult.ok_subtitle(
            text=sub_text,
            title=title,
            source_url=url,
            source_basename=source_basename,
            duration_sec=duration,
            extra={
                "subtitle_lang": sub_lang,
                "cookies": cookies_used,
                "metadata_ms": metadata_ms,
                "subtitle_ms": subtitle_ms,
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
            },
        )
        return result

    if not allow_asr:
        if own_workdir:
            _safe_cleanup(wd)
        return FetchVideoResult.failure(
            stage="subtitle",
            error="no_subtitle_and_asr_disabled_by_caller",
            source_url=url,
            title=title,
            source_basename=source_basename,
            duration_sec=duration,
            extra={
                "cookies": cookies_used,
                "metadata_ms": metadata_ms,
                "subtitle_ms": subtitle_ms,
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
            },
        )
    if not settings.asr_enabled or (transcribe is None and not settings.asr_effective):
        if own_workdir:
            _safe_cleanup(wd)
        return FetchVideoResult.failure(
            stage="asr",
            error="no_subtitle_and_asr_unavailable",
            source_url=url,
            title=title,
            source_basename=source_basename,
            duration_sec=duration,
            extra={
                "cookies": cookies_used,
                "metadata_ms": metadata_ms,
                "subtitle_ms": subtitle_ms,
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
            },
        )
    gate = web_video_asr_duration_gate(
        duration,
        cookies_used=cookies_used,
        source_url=url,
        title=title,
        source_basename=source_basename,
    )
    if gate is not None:
        if own_workdir:
            _safe_cleanup(wd)
        return gate

    audio_outtmpl = str(wd / "%(id)s.%(ext)s")
    audio_opts: dict[str, Any] = {
        "format": "bestaudio*/bestaudio/best",
        "outtmpl": audio_outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": int(settings.video_url_fetch_timeout_sec),
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        "js_runtimes": {"node": {}},
    }
    cookies_used = _apply_cookies_opt(audio_opts)
    try:
        _t_audio = time.perf_counter()
        info2 = extract_fn(url, ydl_opts=audio_opts) or {}
        audio_ms = int((time.perf_counter() - _t_audio) * 1000)
        info = {**info, **info2}
        title = str(info.get("title") or "").strip() or title
        duration = float(info.get("duration") or duration)
        source_basename = _basename_from_info(info, url) or source_basename
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:  # noqa: BLE001
        audio_ms = int((time.perf_counter() - _t_audio) * 1000) if "_t_audio" in locals() else 0
        logger.warning(
            "v11 video url audio stage failed url=%s cookies=%s err=%r",
            url, cookies_used, e, exc_info=True,
        )
        if own_workdir:
            _safe_cleanup(wd)
        return FetchVideoResult.failure(
            stage="audio",
            error=f"yt_dlp_audio_failed:{_describe_extract_error(e)}",
            source_url=url,
            title=title,
            source_basename=source_basename,
            duration_sec=duration,
            extra={
                "cookies": cookies_used,
                "metadata_ms": metadata_ms,
                "subtitle_ms": subtitle_ms,
                "audio_ms": audio_ms,
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
            },
        )

    audio_path = _pick_audio_file(wd)
    if not audio_path:
        if own_workdir:
            _safe_cleanup(wd)
        return FetchVideoResult.failure(
            stage="audio",
            error="no_audio_file_after_download",
            source_url=url,
            title=title,
            source_basename=source_basename,
            duration_sec=duration,
            extra={
                "cookies": cookies_used,
                "metadata_ms": metadata_ms,
                "subtitle_ms": subtitle_ms,
                "audio_ms": audio_ms,
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
            },
        )

    if transcribe is None:
        from llm.asr import transcribe_audio as _transcribe

        transcribe_fn = _transcribe
    else:
        transcribe_fn = transcribe

    _t_asr = time.perf_counter()
    asr_res = transcribe_fn(audio_path)
    asr_ms = int((time.perf_counter() - _t_asr) * 1000)
    if own_workdir:
        _safe_cleanup(wd)

    if not getattr(asr_res, "available", False) or not getattr(asr_res, "text", ""):
        return FetchVideoResult.failure(
            stage="asr",
            error=f"asr_failed:{getattr(asr_res, 'error', 'unknown')}",
            source_url=url,
            title=title,
            source_basename=source_basename,
            duration_sec=duration,
            extra={
                "cookies": cookies_used,
                "metadata_ms": metadata_ms,
                "subtitle_ms": subtitle_ms,
                "audio_ms": audio_ms,
                "asr_ms": asr_ms,
                "asr_provider_chain": list(getattr(asr_res, "provider_chain", []) or []),
                "asr_provider_failures": list(getattr(asr_res, "provider_failures", []) or []),
                "asr_provider_attempts": list(getattr(asr_res, "provider_attempts", []) or []),
                "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
            },
        )

    result = FetchVideoResult.ok_asr(
        text=asr_res.text,
        title=title,
        source_url=url,
        source_basename=source_basename,
        duration_sec=duration,
        provider=getattr(asr_res, "provider", "") or settings.asr_provider,
        model=getattr(asr_res, "model", "") or settings.asr_model,
        extra={
            "cookies": cookies_used,
            "metadata_ms": metadata_ms,
            "subtitle_ms": subtitle_ms,
            "audio_ms": audio_ms,
            "asr_ms": asr_ms,
            "asr_provider_chain": list(getattr(asr_res, "provider_chain", []) or []),
            "asr_provider_failures": list(getattr(asr_res, "provider_failures", []) or []),
            "asr_provider_attempts": list(getattr(asr_res, "provider_attempts", []) or []),
            "elapsed_ms": int((time.perf_counter() - started_at) * 1000),
        },
    )
    return result
