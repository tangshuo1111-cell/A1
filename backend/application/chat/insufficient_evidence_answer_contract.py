"""Stable answer contract when canonical exit marks insufficient evidence."""

from __future__ import annotations

INSUFFICIENT_EVIDENCE_ANSWER_PREFIX = (
    "结论：现有材料不足，无法确认。"
    "下面只能说明目前材料能支持的部分，以及仍缺少哪些证据。\n\n"
)

_LIMITATION_MARKERS = (
    "无法确认",
    "证据不足",
    "当前材料不足",
    "基于当前",
    "如果",
    "可能",
    "暂时",
)


def has_limitation_statement(answer: str) -> bool:
    text = str(answer or "")
    return any(marker in text for marker in _LIMITATION_MARKERS)


def apply_insufficient_evidence_answer_contract(answer: str) -> str:
    """Prefix answer with a deterministic insufficiency statement when missing."""
    text = str(answer or "").strip()
    if not text:
        return INSUFFICIENT_EVIDENCE_ANSWER_PREFIX.strip()
    if has_limitation_statement(text):
        return text
    return f"{INSUFFICIENT_EVIDENCE_ANSWER_PREFIX}{text}"
