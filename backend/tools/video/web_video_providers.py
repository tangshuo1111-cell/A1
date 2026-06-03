"""
V16 R4-D：网页视频字幕 — yt-dlp provider（仅字幕 / transcript，不下载完整视频）。

测试可通过 monkeypatch ``run_ytdlp_subtitle_provider`` 或注入 ``extract_info_fn``。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

from config.settings import settings
from tools.video import errors as video_errors

logger = logging.getLogger("light_maqa")

# 语言优先级：zh-CN → zh → en → 其余首个可用
SUBTITLE_LANG_PRIORITY: tuple[str, ...] = ("zh-CN", "zh-Hans", "zh", "en", "en-US")


@dataclass
class WebVideoSubtitleOutcome:
    ok: bool
    text: str = ""
    error_code: str = ""
    failure_reason: str = ""
    next_action_hint: str = ""
    duration_ms: float = 0.0
    provider: str = "yt_dlp"
    provider_type: str = "web_video_subtitle"
    production_ready: bool = True
    subtitle_source: str = ""  # subtitles | automatic_captions
    language: str = ""
    title: str = ""
    duration_sec: float = 0.0
    webpage_url: str = ""
    metadata_extra: dict[str, Any] = field(default_factory=dict)


def _ordered_lang_keys(requested: dict[str, Any]) -> list[str]:
    keys = [str(k) for k in requested]
    if not keys:
        return []
    ordered: list[str] = []
    for pref in SUBTITLE_LANG_PRIORITY:
        for k in keys:
            kl = k.lower()
            pl = pref.lower()
            if k == pref or kl.startswith(pl) or pl in kl:  # noqa: SIM102
                if k not in ordered:
                    ordered.append(k)
    for k in keys:
        if k not in ordered:
            ordered.append(k)
    return ordered


def _subtitle_bucket(info: dict[str, Any], lang: str) -> str:
    subs = info.get("subtitles") or {}
    autos = info.get("automatic_captions") or {}
    if lang in subs and subs[lang]:
        return "subtitles"
    if lang in autos and autos[lang]:
        return "automatic_captions"
    for k, v in subs.items():
        if v and (k == lang or k.startswith(lang) or lang.startswith(k)):
            return "subtitles"
    for k, v in autos.items():
        if v and (k == lang or k.startswith(lang) or lang.startswith(k)):
            return "automatic_captions"
    return "subtitles"


def _read_text_from_sub_info(sub_info: dict[str, Any], workdir: Path, lang: str) -> str:
    fp = (sub_info.get("filepath") or "").strip()
    if not fp:
        return ""
    p = Path(fp)
    if not p.exists():
        for cand in workdir.glob(f"*.{lang}.*"):
            if cand.is_file():
                p = cand
                break
        if not p.exists():
            for cand in workdir.iterdir():
                if cand.is_file() and cand.suffix.lower() in (".vtt", ".srt"):
                    p = cand
                    break
    if not p.exists():
        return ""
    try:
        raw = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    from video.url_fetch import _strip_subtitle_markup

    return _strip_subtitle_markup(raw).strip()


def _is_bilibili_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "bilibili.com" or host.endswith(".bilibili.com") or host == "b23.tv"


def _load_cookie_jar_from_settings() -> MozillaCookieJar | None:
    kind, value = settings.video_cookies_choice()
    if kind != "file" or not value:
        return None
    path = Path(value)
    if not path.is_file():
        return None
    jar = MozillaCookieJar()
    try:
        jar.load(str(path), ignore_discard=True, ignore_expires=True)
    except (OSError, ValueError, RuntimeError, TimeoutError):  # noqa: BLE001
        return None
    return jar


def _http_json(url: str, *, params: dict[str, Any], referer: str, jar: MozillaCookieJar | None) -> dict[str, Any]:
    from urllib.parse import urlencode

    q = urlencode({k: v for k, v in params.items() if v is not None})
    full_url = f"{url}?{q}" if q else url
    opener = build_opener(HTTPCookieProcessor(jar)) if jar is not None else build_opener()
    req = Request(
        full_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": referer,
        },
    )
    with opener.open(req, timeout=int(settings.video_url_fetch_timeout_sec)) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw or "{}")


def _fetch_bilibili_standard_subtitle(
    url: str,
    *,
    info: dict[str, Any] | None = None,
    json_getter: Callable[..., dict[str, Any]] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    getter = json_getter or _http_json
    bvid = str((info or {}).get("id") or "").strip()
    if not bvid:
        parsed = urlparse(url)
        segs = [seg for seg in parsed.path.split("/") if seg]
        if "video" in segs:
            idx = segs.index("video")
            if idx + 1 < len(segs):
                bvid = segs[idx + 1]
    if not bvid:
        return "", "", {"bilibili_reason": "missing_bvid"}

    jar = _load_cookie_jar_from_settings()
    referer = f"https://www.bilibili.com/video/{bvid}/"
    view = getter(
        "https://api.bilibili.com/x/web-interface/view",
        params={"bvid": bvid},
        referer=referer,
        jar=jar,
    )
    view_data = view.get("data") or {}
    aid = view_data.get("aid")
    pages = view_data.get("pages") or [{}]
    cid = pages[0].get("cid") if isinstance(pages, list) and pages else None
    if not aid or not cid:
        return "", "", {"bilibili_reason": "missing_aid_or_cid", "bvid": bvid}

    player = getter(
        "https://api.bilibili.com/x/player/v2",
        params={"aid": aid, "cid": cid, "bvid": bvid},
        referer=referer,
        jar=jar,
    )
    subtitles = (((player.get("data") or {}).get("subtitle") or {}).get("subtitles") or [])
    if not subtitles:
        return "", "", {
            "bilibili_reason": "subtitle_track_not_found",
            "bvid": bvid,
            "aid": aid,
            "cid": cid,
        }

    first = subtitles[0] if isinstance(subtitles[0], dict) else {}
    sub_url = str(first.get("subtitle_url") or "").strip()
    if not sub_url:
        return "", "", {"bilibili_reason": "subtitle_url_missing", "bvid": bvid, "aid": aid, "cid": cid}
    if sub_url.startswith("//"):
        sub_url = "https:" + sub_url
    sub_json = getter(sub_url, params={}, referer=referer, jar=jar)
    body = sub_json.get("body") or []
    lines: list[str] = []
    for item in body:
        if not isinstance(item, dict):
            continue
        line = str(item.get("content") or "").strip()
        if line:
            lines.append(line)
    text = "\n".join(lines).strip()
    lang = str(first.get("lan") or first.get("lan_doc") or "").strip()
    return text, lang, {
        "bvid": bvid,
        "aid": aid,
        "cid": cid,
        "subtitle_track_count": len(subtitles),
        "subtitle_source_url_present": bool(sub_url),
    }


def classify_ytdlp_error(stage: str, error: str, info: dict[str, Any] | None) -> tuple[str, str, str]:
    low = (error or "").lower()
    inf = info or {}
    if inf.get("is_live") is True:
        return video_errors.LIVE_STREAM_NOT_SUPPORTED, "直播流不在支持范围", "请使用非直播点播地址"
    if "drm" in low:
        return video_errors.DRM_NOT_SUPPORTED, "当前视频受 DRM 保护", "V16 不绕过 DRM"
    if "live" in low:
        return video_errors.LIVE_STREAM_NOT_SUPPORTED, "直播流不在支持范围", "请使用点播视频"
    if "reason=login_required" in low or "sign in to confirm" in low or "login required" in low:
        return video_errors.VIDEO_REQUIRES_LOGIN, "需要登录或站点拒绝匿名访问", "配置 cookie 或使用可公开访问的视频"
    if "private video" in low or "members only" in low:
        return video_errors.ACCESS_DENIED, "私有或会员专享视频", "无权限抓取该视频"
    if "unsupportederror" in low or "unsupported url" in low or "no suitable extractor" in low:
        return video_errors.VIDEO_SITE_NOT_SUPPORTED, "站点或 URL 不受支持", "换用 yt-dlp 支持的站点"
    if "reason=http_403" in low or "http error 403" in low:
        return video_errors.ACCESS_DENIED, "HTTP 403 被拒绝", "检查网络、地区或反爬限制"
    if "reason=non_ascii_in_url" in low or "non_ascii" in low:
        return video_errors.VIDEO_URL_UNSUPPORTED, "URL 含非 ASCII 或格式异常", "检查 URL 是否正确"
    if stage == "subtitle" or "no_subtitle" in low:
        return video_errors.SUBTITLE_NOT_FOUND, "未找到可用字幕轨道", "确认视频提供字幕或开启自动字幕"
    return video_errors.VIDEO_PROVIDER_ERROR, (error or "yt-dlp 失败")[:220], "检查网络、代理与 yt-dlp 版本"


def run_fake_web_video_subtitle(
    *,
    ok: bool = True,
    text: str = "fixture transcript",
    error_code: str = "",
    failure_reason: str = "",
    subtitle_source: str = "subtitles",
    language: str = "zh-CN",
) -> WebVideoSubtitleOutcome:
    """仅测试/fixture：production_ready 恒为 False。"""
    if ok:
        return WebVideoSubtitleOutcome(
            ok=True,
            text=text,
            production_ready=False,
            subtitle_source=subtitle_source,
            language=language,
            title="fixture",
            webpage_url="https://example.com/watch?v=fake",
        )
    return WebVideoSubtitleOutcome(
        ok=False,
        error_code=error_code or video_errors.SUBTITLE_NOT_FOUND,
        failure_reason=failure_reason or "fixture failure",
        production_ready=False,
    )


def run_ytdlp_subtitle_provider(
    url: str,
    *,
    automatic_captions: bool = True,
    extract_info_fn: Callable[..., dict[str, Any]] | None = None,
    workdir: Path | None = None,
) -> WebVideoSubtitleOutcome:
    from video.url_fetch import (  # noqa: PLC0415
        _apply_cookies_opt,
        _describe_extract_error,
        _new_workdir,
        _safe_cleanup,
        _yt_dlp_extract_info,
        is_supported_video_url,
    )

    t0 = time.perf_counter()
    webpage_url = (url or "").strip()

    def _ms() -> float:
        return (time.perf_counter() - t0) * 1000.0

    if not is_supported_video_url(webpage_url):
        c, r, h = classify_ytdlp_error("domain", "url_not_in_whitelist", {})
        return WebVideoSubtitleOutcome(ok=False, error_code=c, failure_reason=r, next_action_hint=h, duration_ms=_ms())

    try:
        webpage_url.encode("ascii")
    except (UnicodeEncodeError, AttributeError):
        return WebVideoSubtitleOutcome(
            ok=False,
            error_code=video_errors.VIDEO_URL_UNSUPPORTED,
            failure_reason="URL 含非 ASCII",
            next_action_hint="确保 URL 仅含 ASCII",
            duration_ms=_ms(),
        )

    extract_fn = extract_info_fn or _yt_dlp_extract_info
    own_workdir = workdir is None
    wd: Path = workdir if workdir is not None else _new_workdir()

    sub_outtmpl = str(wd / "%(id)s.%(ext)s")
    sub_langs = list(SUBTITLE_LANG_PRIORITY) + ["en-orig", "en"]
    sub_opts: dict[str, Any] = {
        "writesubtitles": True,
        "writeautomaticsub": bool(automatic_captions),
        "subtitleslangs": sub_langs,
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
    _apply_cookies_opt(sub_opts)

    info: dict[str, Any] = {}
    try:
        info = extract_fn(webpage_url, ydl_opts=sub_opts) or {}
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:  # noqa: BLE001
        logger.warning("ytdlp subtitle extract failed url=%s err=%r", webpage_url, e, exc_info=True)
        if own_workdir:
            _safe_cleanup(wd)
        detail = f"{type(e).__name__}:{e!s}"
        code, reason, hint = classify_ytdlp_error("metadata", detail, {})
        return WebVideoSubtitleOutcome(
            ok=False,
            error_code=code,
            failure_reason=reason,
            next_action_hint=hint,
            duration_ms=_ms(),
            metadata_extra={"yt_dlp_error": _describe_extract_error(e)},
        )

    if info.get("is_live") is True:
        if own_workdir:
            _safe_cleanup(wd)
        return WebVideoSubtitleOutcome(
            ok=False,
            error_code=video_errors.LIVE_STREAM_NOT_SUPPORTED,
            failure_reason="直播流不在支持范围",
            next_action_hint="请使用非直播点播地址",
            duration_ms=_ms(),
            title=str(info.get("title") or "").strip(),
            webpage_url=webpage_url,
        )

    title = str(info.get("title") or "").strip() or webpage_url
    duration_sec = float(info.get("duration") or 0.0)
    requested = info.get("requested_subtitles") or {}

    # B 站补强：yt-dlp 常只暴露 danmaku，不代表站点有标准字幕轨。
    # 这里补查官方字幕接口；有标准字幕就走标准字幕，没有就明确失败，不把弹幕当字幕。
    if _is_bilibili_url(webpage_url):
        text, lang, meta = _fetch_bilibili_standard_subtitle(webpage_url, info=info)
        if text:
            if own_workdir:
                _safe_cleanup(wd)
            return WebVideoSubtitleOutcome(
                ok=True,
                text=text,
                duration_ms=_ms(),
                subtitle_source="subtitles",
                language=lang or "zh-CN",
                title=title,
                duration_sec=duration_sec,
                webpage_url=str(info.get("webpage_url") or webpage_url),
                production_ready=True,
                metadata_extra={
                    "provider_variant": "bilibili_api_subtitle",
                    "cookies_trace": "applied_via_settings",
                    **meta,
                },
            )
        if meta.get("bilibili_reason") == "subtitle_track_not_found":
            if own_workdir:
                _safe_cleanup(wd)
            return WebVideoSubtitleOutcome(
                ok=False,
                error_code=video_errors.SUBTITLE_NOT_FOUND,
                failure_reason="Bilibili 该视频没有可提取的标准字幕轨，当前仅检测到弹幕或无字幕",
                next_action_hint="更换带标准字幕轨的视频，或走 ASR/OCR 方案。",
                duration_ms=_ms(),
                title=title,
                duration_sec=duration_sec,
                webpage_url=str(info.get("webpage_url") or webpage_url),
                metadata_extra={
                    "provider_variant": "bilibili_api_subtitle",
                    "cookies_trace": "applied_via_settings",
                    **meta,
                },
            )

    if not requested:
        subs = info.get("subtitles") or {}
        autos = info.get("automatic_captions") or {}
        if not subs and autos and not automatic_captions:
            if own_workdir:
                _safe_cleanup(wd)
            return WebVideoSubtitleOutcome(
                ok=False,
                error_code=video_errors.AUTOMATIC_CAPTION_DISABLED,
                failure_reason="仅自动字幕可用且已禁用自动字幕",
                next_action_hint="设置 V16_ENABLE_WEB_VIDEO_AUTOMATIC_CAPTION=true",
                duration_ms=_ms(),
                title=title,
                duration_sec=duration_sec,
                webpage_url=webpage_url,
            )
        if own_workdir:
            _safe_cleanup(wd)
        return WebVideoSubtitleOutcome(
            ok=False,
            error_code=video_errors.SUBTITLE_NOT_FOUND,
            failure_reason="未下载到任何字幕文件",
            next_action_hint="确认视频含字幕或自动字幕",
            duration_ms=_ms(),
            title=title,
            duration_sec=duration_sec,
            webpage_url=webpage_url,
        )

    for lang in _ordered_lang_keys(requested):
        sub_info = requested.get(lang)
        if not isinstance(sub_info, dict):
            continue
        try:
            raw_text = _read_text_from_sub_info(sub_info, wd, lang)
        except (OSError, ValueError, RuntimeError, TimeoutError) as e:  # noqa: BLE001
            if own_workdir:
                _safe_cleanup(wd)
            return WebVideoSubtitleOutcome(
                ok=False,
                error_code=video_errors.SUBTITLE_PARSE_FAILED,
                failure_reason=f"字幕解析失败: {type(e).__name__}",
                next_action_hint="检查字幕文件编码与格式",
                duration_ms=_ms(),
            )
        if not raw_text:
            continue
        bucket = _subtitle_bucket(info, lang)
        if own_workdir:
            _safe_cleanup(wd)
        return WebVideoSubtitleOutcome(
            ok=True,
            text=raw_text,
            duration_ms=_ms(),
            subtitle_source=bucket,
            language=lang,
            title=title,
            duration_sec=duration_sec,
            webpage_url=str(info.get("webpage_url") or webpage_url),
            production_ready=True,
            metadata_extra={"cookies_trace": "applied_via_settings"},
        )

    if own_workdir:
        _safe_cleanup(wd)
    had_files = any(isinstance(requested[k], dict) and (requested[k].get("filepath") or "") for k in requested)
    if had_files:
        return WebVideoSubtitleOutcome(
            ok=False,
            error_code=video_errors.SUBTITLE_EMPTY,
            failure_reason="字幕文件无有效文本",
            next_action_hint="尝试其他语言或检查站点字幕质量",
            duration_ms=_ms(),
            title=title,
            webpage_url=webpage_url,
        )
    return WebVideoSubtitleOutcome(
        ok=False,
        error_code=video_errors.SUBTITLE_DOWNLOAD_FAILED,
        failure_reason="未能从磁盘读取已请求的字幕",
        next_action_hint="检查临时目录权限与 yt-dlp 写入",
        duration_ms=_ms(),
        title=title,
        webpage_url=webpage_url,
    )


__all__ = [
    "SUBTITLE_LANG_PRIORITY",
    "WebVideoSubtitleOutcome",
    "classify_ytdlp_error",
    "run_fake_web_video_subtitle",
    "run_ytdlp_subtitle_provider",
]
