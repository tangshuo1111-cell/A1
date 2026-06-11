"""Thin compat surface for shared fast-path helpers (Round 17)."""

from __future__ import annotations

def _wants_full_web_text(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    markers = (
        "全文提取",
        "提取全文",
        "整个网页的全文",
        "网页全文",
        "完整正文",
        "原文提取",
        "把整个网页的全文提取出来",
        "把网页全文提取出来",
    )
    return any(marker in text for marker in markers)


def _extract_page_body_from_material(material: str) -> str:
    text = (material or "").strip()
    if "[网页正文]" not in text or "正文:\n" not in text:
        return ""
    body = text.split("正文:\n", 1)[1]
    if "\n\n[搜索补充]\n" in body:
        body = body.split("\n\n[搜索补充]\n", 1)[0]
    return body.strip()

from application.chat.executors.fast_lanes.fast_capability_policy import (
    CROSS_LANE_GENERAL_CAPABILITIES,
    FAST_CAPABILITY_WHITELIST,
    cross_lane_violation_for_capabilities,
)
from application.chat.executors.fast_lanes.fast_llm import run_fast_llm_answer, summarize_fast_material

__all__ = [
    "FAST_CAPABILITY_WHITELIST",
    "CROSS_LANE_GENERAL_CAPABILITIES",
    "cross_lane_violation_for_capabilities",
    "run_fast_llm_answer",
    "summarize_fast_material",
    "_wants_full_web_text",
    "_extract_page_body_from_material",
]

