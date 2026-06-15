"""Orchestration handoff: inline v13_text_content → temporary_material answer path."""

from __future__ import annotations

from dataclasses import replace
from typing import Any


def apply_inline_document_plan_handoff(
    plan: Any,
    *,
    v13_text_content: str | None,
    inline_document_promoted: bool = False,
) -> Any:
    if not inline_document_promoted:
        return plan
    inline = (v13_text_content or "").strip()
    if not inline:
        return plan
    if getattr(plan, "v13_prepare_intent", None) is not None:
        return plan

    return replace(
        plan,
        answer_mode="temporary_material",
        needs_retrieval=False,
        needs_pending=False,
        pending_reference="none",
    )
