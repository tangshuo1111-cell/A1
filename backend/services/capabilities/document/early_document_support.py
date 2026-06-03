"""Early document prepare flow — complex gather 文档侧编排。"""

from __future__ import annotations

from typing import Any

from agents.main_agent import AgnoCollaborationPlan
from services.capabilities.knowledge.pending_ingestion_service import (
    prepare_file_source,
    prepare_web_url_source,
)
from services.capabilities.knowledge.pending_service import (
    SOURCE_TYPE_TEXT_FILE,
    SOURCE_TYPE_WEB_URL,
)

from .types import EarlyDocumentOutcome


def _plan_allows_tool(plan: object, tool_name: str) -> bool:
    allowed = getattr(plan, "tools_allowed", None)
    if allowed is None:
        return True
    allowed_set = set(allowed)
    if "*" in allowed_set or "__all__" in allowed_set:
        return True
    if not allowed_set:
        return False
    return tool_name in allowed_set


def run_early_document_prepare_flow(
    *,
    plan: AgnoCollaborationPlan,
    session_id: str,
    file_content: str | bytes | None,
    blocked_failures: list[dict[str, Any]],
) -> EarlyDocumentOutcome:
    """文档/网页 prepare 早期阶段：进入统一调度，由 pending_flow 最终收口。"""
    out = EarlyDocumentOutcome()
    prepare_intent = getattr(plan, "v13_prepare_intent", None)
    if prepare_intent is None:
        return out
    source_type = str(getattr(prepare_intent, "source_type", "") or "")
    raw_source = str(getattr(prepare_intent, "raw_source", "") or "")
    out.source_type = source_type
    if source_type == SOURCE_TYPE_TEXT_FILE:
        if not _plan_allows_tool(plan, "prepare_file"):
            blocked_failures.append({
                "tool": "prepare_file",
                "reason": "not_allowed_by_plan",
                "recoverable": False,
            })
            out.error_code = "not_allowed_by_plan"
            return out
        try:
            out.pending_item_early = prepare_file_source(
                raw_source,
                session_id=session_id,
                file_content=file_content,
            )
        except Exception as exc:  # noqa: BLE001
            out.error_code = f"prepare_file_failed:{type(exc).__name__}"
        return out
    if source_type == SOURCE_TYPE_WEB_URL:
        if not _plan_allows_tool(plan, "prepare_web_url"):
            blocked_failures.append({
                "tool": "prepare_web_url",
                "reason": "not_allowed_by_plan",
                "recoverable": False,
            })
            out.error_code = "not_allowed_by_plan"
            return out
        try:
            out.pending_item_early = prepare_web_url_source(
                raw_source,
                session_id=session_id,
            )
        except Exception as exc:  # noqa: BLE001
            out.error_code = f"prepare_web_url_failed:{type(exc).__name__}"
        return out
    return out
