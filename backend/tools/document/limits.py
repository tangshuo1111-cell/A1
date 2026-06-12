"""
文档处理上限配置。

优先从 settings 读；若未配置则使用保守默认值。
超限时工具必须返回明确 error_code，不能卡死。
"""

from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if not v:
        return default
    try:
        return int(v.strip())
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if not v:
        return default
    try:
        return float(v.strip())
    except ValueError:
        return default


# ── 文件大小上限 ──────────────────────────────────────────────────────────
MAX_FILE_MB: int = _env_int("V16_MAX_FILE_MB", 20)
MAX_FILE_BYTES: int = MAX_FILE_MB * 1024 * 1024

# ── PDF 上限 ──────────────────────────────────────────────────────────────
MAX_PDF_PAGES: int = _env_int("V16_MAX_PDF_PAGES", 100)

# ── Excel 上限 ────────────────────────────────────────────────────────────
MAX_EXCEL_SHEETS: int = _env_int("V16_MAX_EXCEL_SHEETS", 10)
MAX_EXCEL_ROWS: int = _env_int("V16_MAX_EXCEL_ROWS", 5000)
MAX_EXCEL_CELLS: int = _env_int("V16_MAX_EXCEL_CELLS", 50_000)

# ── Word 上限 ─────────────────────────────────────────────────────────────
MAX_DOCX_PARAGRAPHS: int = _env_int("V16_MAX_DOCX_PARAGRAPHS", 2000)

# ── 文本上限 ──────────────────────────────────────────────────────────────
MAX_TEXT_CHARS: int = _env_int("V16_MAX_TEXT_CHARS", 200_000)

# ── 质量判断阈值 ──────────────────────────────────────────────────────────
# 有效文本比率：低于此值判定为扫描版 / 低质量
SCANNED_TEXT_RATIO_THRESHOLD: float = _env_float("V16_SCANNED_TEXT_RATIO", 0.1)
LOW_QUALITY_TEXT_RATIO: float = _env_float("V16_LOW_QUALITY_TEXT_RATIO", 0.3)
MIN_USEFUL_TEXT_LENGTH: int = _env_int("V16_MIN_USEFUL_TEXT_LENGTH", 30)
