"""
V16 R1：文档工具内容质量判断。

assess_quality(text, source_type) → quality dict

规则（最低线）：
  - 空文本         → quality_level = "failed"
  - 极短文本       → quality_level = "low"
  - valid_text_ratio < SCANNED 阈值 → 可能扫描件
  - 重复率 > 0.8   → quality_level = "low"
  - 正常           → quality_level = "good" 或 "usable"

不使用 LLM；纯规则统计。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from tools.document.limits import (
    LOW_QUALITY_TEXT_RATIO,
    MIN_USEFUL_TEXT_LENGTH,
    SCANNED_TEXT_RATIO_THRESHOLD,
)


def _valid_text_ratio(text: str) -> float:
    """计算有效文本字符比率（排除空白、特殊控制字符后的占比）。"""
    if not text:
        return 0.0
    total = len(text)
    valid = len(re.sub(r"[\x00-\x1f\x7f\s]+", "", text))
    return valid / total


def _duplicate_ratio(text: str, chunk_size: int = 50) -> float:
    """粗粒度重复率：把文本分成 chunk_size 长度的块，看重复块占比。"""
    if not text or len(text) < chunk_size * 2:
        return 0.0
    chunks = [text[i : i + chunk_size] for i in range(0, len(text) - chunk_size + 1, chunk_size)]
    if not chunks:
        return 0.0
    unique = len(set(chunks))
    return 1.0 - unique / len(chunks)


def _detect_language(text: str) -> str:
    """极简语言检测：仅区分 zh / en / unknown，不引入 langdetect 等重库。"""
    if not text:
        return "unknown"
    sample = text[:500]
    zh_count = len(re.findall(r"[\u4e00-\u9fff]", sample))
    en_count = len(re.findall(r"[a-zA-Z]", sample))
    if zh_count > en_count and zh_count > 10:
        return "zh"
    if en_count > zh_count and en_count > 10:
        return "en"
    return "unknown"


def assess_quality(
    text: str,
    source_type: str = "",
    *,
    extra_hints: dict | None = None,
) -> dict[str, Any]:
    """
    对文档解析结果做内容质量评估。

    返回 quality dict，至少包含：
      text_length, valid_text_ratio, duplicate_ratio,
      language_detected, content_quality, quality_level, warnings
    """
    t = (text or "").strip()
    warnings: list[str] = []

    text_length = len(t)
    if text_length == 0:
        return {
            "text_length": 0,
            "valid_text_ratio": 0.0,
            "duplicate_ratio": 0.0,
            "language_detected": "unknown",
            "content_quality": "empty",
            "quality_level": "failed",
            "warnings": ["文本为空"],
            "content_hash": "",
        }

    vtr = _valid_text_ratio(t)
    dup = _duplicate_ratio(t)
    lang = _detect_language(t)
    content_hash = hashlib.md5(t.encode("utf-8", errors="replace")).hexdigest()

    # ── quality_level 判定 ───────────────────────────────────────────────
    if text_length < MIN_USEFUL_TEXT_LENGTH:
        quality_level = "low"
        content_quality = "too_short"
        warnings.append(f"文本过短（{text_length} 字符）")
    elif vtr < SCANNED_TEXT_RATIO_THRESHOLD:
        # 极低有效字符比率 → 疑似扫描件或乱码
        quality_level = "failed"
        content_quality = "scanned_or_corrupted"
        warnings.append(f"有效字符比率过低（{vtr:.2%}），可能为扫描件或乱码")
    elif vtr < LOW_QUALITY_TEXT_RATIO:
        quality_level = "low"
        content_quality = "low_valid_ratio"
        warnings.append(f"有效字符比率偏低（{vtr:.2%}）")
    elif dup > 0.8:
        quality_level = "low"
        content_quality = "high_duplicate"
        warnings.append(f"内容重复率较高（{dup:.2%}）")
    elif dup > 0.5:
        quality_level = "usable"
        content_quality = "moderate_duplicate"
        warnings.append(f"内容有一定重复（{dup:.2%}）")
    else:
        quality_level = "good"
        content_quality = "ok"

    return {
        "text_length": text_length,
        "valid_text_ratio": round(vtr, 4),
        "duplicate_ratio": round(dup, 4),
        "language_detected": lang,
        "content_quality": content_quality,
        "quality_level": quality_level,
        "warnings": warnings,
        "content_hash": content_hash,
    }
