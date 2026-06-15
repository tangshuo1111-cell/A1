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


def apply_insufficient_evidence_answer_contract(answer: str, *, max_chars: int | None = None) -> str:
    """Prefix answer with a deterministic insufficiency statement when missing.

    When ``max_chars`` is provided the final string is capped to it so the
    contract prefix never breaks the configured output budget.
    """
    text = str(answer or "").strip()
    if not text:
        result = INSUFFICIENT_EVIDENCE_ANSWER_PREFIX.strip()
    elif has_limitation_statement(text):
        result = text
    else:
        result = f"{INSUFFICIENT_EVIDENCE_ANSWER_PREFIX}{text}"
    if max_chars is not None and max_chars > 0 and len(result) > max_chars:
        result = result[:max_chars]
    return result
