"""
视频 URL -> 文本（yt-dlp 下字幕优先；无字幕走云 ASR 兜底）。

公开 API（均可从本模块直接 import）：
    FetchVideoResult
    is_supported_video_url(url) -> bool
    extract_video_url(message) -> str | None
    probe_web_video_metadata(url) -> dict[str, Any]
    fetch_video_text(url, ...) -> FetchVideoResult

实现：`url_fetch_ytdlp` / `url_fetch_support` / `url_fetch_main`。
"""

from __future__ import annotations

# Re-export from split modules (preserve backward compat for all importers)
from .fetch_result import FetchVideoResult  # noqa: F401
from .subtitle_text import (  # noqa: F401
    _read_subtitle_text_from_files,
    _strip_subtitle_markup,
)
from .url_fetch_main import fetch_video_text  # noqa: F401
from .url_fetch_support import probe_web_video_metadata  # noqa: F401
from .url_fetch_ytdlp import (  # noqa: F401
    _apply_cookies_opt,
    _describe_extract_error,
    _new_workdir,
    _safe_cleanup,
    _yt_dlp_extract_info,
)
from .url_validate import (  # noqa: F401
    _URL_REGEX,
    _host_matches_whitelist,
    extract_video_url,
    is_supported_video_url,
)

__all__ = [
    "FetchVideoResult",
    "extract_video_url",
    "fetch_video_text",
    "is_supported_video_url",
]
