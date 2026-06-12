"""yt-dlp 工作目录、extract_info、错误归因、cookies 注入。"""

from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from config.settings import settings

logger = logging.getLogger("light_maqa")


def _new_workdir() -> Path:
    """每次调用都新开一个子目录，避免并发 / 多次调用互相覆盖文件。"""
    base = settings.video_tmp_dir
    base.mkdir(parents=True, exist_ok=True)
    sub = base / f"v11r1_{uuid.uuid4().hex[:8]}"
    sub.mkdir(parents=True, exist_ok=False)
    return sub


def _safe_cleanup(workdir: Path) -> None:
    """尽力删除 workdir；失败不抛（清理失败不影响主流程）。"""
    try:
        if workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)
    except (OSError, ValueError, RuntimeError, TimeoutError):  # noqa: BLE001
        logger.debug("v11r1 cleanup failed dir=%s", workdir, exc_info=True)


def _yt_dlp_extract_info(url: str, *, ydl_opts: dict[str, Any]) -> dict[str, Any]:
    """yt-dlp 单点封装：返回 info dict（同步、阻塞）。

    单独出函数是为了让测试可以 monkeypatch 它，**避免真发网络请求**。
    """
    from yt_dlp import (
        YoutubeDL,  # type: ignore[import-untyped]  # 延迟 import：未启用 video URL 时不需要安装
    )

    with YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=True)  # type: ignore[no-any-return]


# 已知 yt-dlp DownloadError / RequestError / ExtractorError 文案 → 归因标签
# （前端按这个分类给提示）
_DL_ERR_REASON_RULES: tuple[tuple[str, str], ...] = (
    ("'latin-1' codec can't encode", "non_ascii_in_url"),
    ("'ascii' codec can't encode", "non_ascii_in_url"),
    ("HTTP Error 412", "http_412_anti_bot"),
    ("HTTP Error 403", "http_403_forbidden"),
    ("HTTP Error 401", "http_401_unauthorized"),
    ("HTTP Error 404", "http_404_not_found"),
    ("Sign in to confirm", "youtube_anti_bot"),
    ("This video is unavailable", "video_unavailable"),
    ("Private video", "video_private"),
    ("members-only", "video_members_only"),
    ("members only", "video_members_only"),
    ("Premieres in", "video_premiere_pending"),
    ("only available", "video_region_locked"),
    ("region", "video_region_locked"),
    ("Requested format is not available", "no_matching_format"),
    ("Login required", "login_required"),
    ("cookies are no longer valid", "cookies_expired"),
)


def _describe_extract_error(e: BaseException) -> str:
    """把 yt-dlp 抛出的异常压成一条对前端有用的错误标签。"""
    name = type(e).__name__
    parts: list[str] = [name]
    if isinstance(e, OSError):
        if getattr(e, "errno", None) is not None:
            parts.append(f"errno={e.errno}")
        if getattr(e, "strerror", None):
            parts.append(f"strerror={str(e.strerror)[:80]}")
        if getattr(e, "filename", None):
            parts.append(f"file={str(e.filename)[:80]}")
    msg = ""
    try:
        msg = str(e) or ""
    except (OSError, ValueError, RuntimeError, TimeoutError):  # noqa: BLE001
        msg = ""
    if msg and name in {"DownloadError", "ExtractorError", "GeoRestrictedError",
                        "UnsupportedError", "RequestError", "TransportError",
                        "HTTPError"}:
        for kw, label in _DL_ERR_REASON_RULES:
            if kw in msg:
                parts.append(f"reason={label}")
                break
    out = ":".join(parts)
    if len(out) > 240:
        out = out[:237] + "..."
    return out


def _apply_cookies_opt(opts: dict[str, Any]) -> str:
    """按 settings.video_cookies_choice() 在 yt-dlp opts 上注入 cookies 源。"""
    if "cookiesfrombrowser" in opts and opts["cookiesfrombrowser"]:
        cb = opts["cookiesfrombrowser"]
        name = ""
        if isinstance(cb, (tuple, list)) and cb:
            name = str(cb[0])
        elif isinstance(cb, str):
            name = cb
        return f"browser:{name}" if name else "browser"
    if "cookiefile" in opts and opts["cookiefile"]:
        return "file"

    kind, value = settings.video_cookies_choice()
    if kind == "browser" and value:
        opts["cookiesfrombrowser"] = (value,)
        return f"browser:{value}"
    if kind == "file" and value:
        opts["cookiefile"] = value
        return "file"
    return "none"
