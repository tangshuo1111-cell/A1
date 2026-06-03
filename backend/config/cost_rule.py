"""
统一成本与性能规则。

所有 AI/ASR/OCR/搜索/视频相关的硬限制集中在此文件。
业务代码通过 `from config.cost_rule import COST` 使用。
超限时应返回明确错误，不静默降级。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


@dataclass(frozen=True)
class CostRule:
    """成本与性能默认规则表。"""

    # --- LLM ---
    ai_max_calls_per_turn: int = field(default_factory=lambda: _env_int("AI_MAX_CALLS_PER_TURN", 5))
    ai_max_input_chars: int = field(default_factory=lambda: _env_int("AI_MAX_INPUT_CHARS", 16000))
    max_output_chars: int = field(default_factory=lambda: _env_int("MAX_OUTPUT_CHARS", 4000))
    max_estimated_cost_usd: float = field(
        default_factory=lambda: _env_float("MAX_ESTIMATED_COST_USD", 0.05),
    )

    # --- RAG / Knowledge ---
    knowledge_max_chunks: int = field(default_factory=lambda: _env_int("KNOWLEDGE_MAX_CHUNKS", 5))
    rag_max_top_k: int = field(default_factory=lambda: _env_int("RAG_MAX_TOP_K", 12))

    # --- Web Search / Fetch ---
    web_search_max_results: int = field(
        default_factory=lambda: _env_int("WEB_SEARCH_MAX_RESULTS", 5),
    )
    web_search_max_query_chars: int = field(
        default_factory=lambda: _env_int("WEB_SEARCH_MAX_QUERY_CHARS", 200),
    )
    web_fetch_timeout_sec: int = field(
        default_factory=lambda: _env_int("WEB_FETCH_TIMEOUT_SEC", 15),
    )
    web_fetch_max_pages: int = field(
        default_factory=lambda: _env_int("WEB_FETCH_MAX_PAGES", 5),
    )
    web_page_max_chars: int = field(
        default_factory=lambda: _env_int("WEB_PAGE_MAX_CHARS", 30000),
    )

    # --- Tools ---
    tool_max_steps: int = field(default_factory=lambda: _env_int("TOOL_MAX_STEPS", 8))

    # --- Video / ASR ---
    video_fetch_timeout_sec: int = field(
        default_factory=lambda: _env_int("VIDEO_FETCH_TIMEOUT_SEC", 90),
    )
    video_asr_auto_seconds: int = field(
        default_factory=lambda: _env_int("VIDEO_ASR_AUTO_SECONDS", 900),
    )
    video_asr_confirm_seconds: int = field(
        default_factory=lambda: _env_int("VIDEO_ASR_CONFIRM_SECONDS", 3600),
    )
    video_asr_max_seconds: int = field(
        default_factory=lambda: _env_int("VIDEO_ASR_MAX_SECONDS", 3600),
    )

    # --- Upload ---
    upload_max_mb: int = field(default_factory=lambda: _env_int("UPLOAD_MAX_MB", 50))

    # --- OCR ---
    ocr_max_pages: int = field(default_factory=lambda: _env_int("OCR_MAX_PAGES", 20))

    # --- Task ---
    task_timeout_sec: int = field(default_factory=lambda: _env_int("TASK_TIMEOUT_SEC", 120))
    session_max_tasks: int = field(default_factory=lambda: _env_int("SESSION_MAX_TASKS", 1))


COST = CostRule()
