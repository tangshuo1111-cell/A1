"""Small deterministic quality checks for extracted web text."""

from __future__ import annotations

import re
from collections import Counter

from tools.web.limits import MIN_WEB_TEXT_CHARS

_NAV_WORDS = {
    "home", "login", "sign", "subscribe", "menu", "privacy", "terms",
    "copyright", "about", "contact", "next", "previous",
    "首页", "登录", "注册", "菜单", "隐私", "版权", "关于", "联系",
}


def assess_web_text(text: str) -> dict[str, object]:
    t = (text or "").strip()
    length = len(t)
    if not t:
        return {
            "text_length": 0,
            "valid_text_ratio": 0.0,
            "boilerplate_ratio": 1.0,
            "duplicate_ratio": 0.0,
            "quality_level": "failed",
            "warnings": ["empty_extracted_text"],
        }

    valid_chars = sum(1 for ch in t if ch.isalnum() or ch.isspace() or "\u4e00" <= ch <= "\u9fff")
    valid_ratio = round(valid_chars / max(length, 1), 4)

    words = re.findall(r"[\w\u4e00-\u9fff]+", t.lower())
    nav_hits = sum(1 for w in words if w in _NAV_WORDS)
    boilerplate_ratio = round(nav_hits / max(len(words), 1), 4)

    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if lines:
        counts = Counter(lines)
        duplicate_chars = sum(len(line) * (count - 1) for line, count in counts.items() if count > 1)
        duplicate_ratio = round(duplicate_chars / max(length, 1), 4)
    else:
        duplicate_ratio = 0.0

    warnings: list[str] = []
    if length < MIN_WEB_TEXT_CHARS:
        warnings.append("text_too_short")
    if valid_ratio < 0.55:
        warnings.append("invalid_text_ratio")
    if boilerplate_ratio > 0.25:
        warnings.append("high_boilerplate_ratio")
    if duplicate_ratio > 0.45:
        warnings.append("high_duplicate_ratio")

    if length < 20 or valid_ratio < 0.35:
        level = "failed"
    elif warnings:
        level = "low" if length < MIN_WEB_TEXT_CHARS or boilerplate_ratio > 0.35 else "usable"
    else:
        level = "good"

    return {
        "text_length": length,
        "valid_text_ratio": valid_ratio,
        "boilerplate_ratio": boilerplate_ratio,
        "duplicate_ratio": duplicate_ratio,
        "language_detected": "unknown",
        "quality_level": level,
        "warnings": warnings,
    }
