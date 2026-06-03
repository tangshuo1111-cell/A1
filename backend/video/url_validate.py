"""视频 URL 白名单检测与提取。"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from config.settings import settings

_URL_REGEX = re.compile(
    r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+"
)


def _host_matches_whitelist(host: str, whitelist: frozenset[str]) -> bool:
    """host 命中白名单：完全相等或是白名单条目的子域。"""
    h = (host or "").strip().lower()
    if not h:
        return False
    for w in whitelist:
        if not w:
            continue
        if h == w or h.endswith("." + w):
            return True
    return False


def is_supported_video_url(url: str | None) -> bool:
    """是否在 settings.video_url_domains 白名单内。"""
    if not url or not isinstance(url, str):
        return False
    if not settings.video_url_enabled:
        return False
    s = url.strip()
    if not s.lower().startswith(("http://", "https://")):
        return False
    try:
        u = urlparse(s)
    except (ValueError, TypeError):
        return False
    return _host_matches_whitelist(u.hostname or "", settings.video_url_domain_set())


def extract_video_url(message: str | None) -> str | None:
    """从自由文本里抽出第一个白名单内的视频 URL。"""
    if not message or not isinstance(message, str):
        return None
    if not settings.video_url_enabled:
        return None
    for m in _URL_REGEX.finditer(message):
        cand = m.group(0).rstrip(".,;:)]}>")
        if is_supported_video_url(cand):
            return cand
    return None
