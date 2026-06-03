"""台账 G-005「video_flow」：MiddleAgent 视频编排薄入口（决策与 gather 已迁 capabilities/video）。"""

from __future__ import annotations

from typing import Any

from agents.main_agent import AgnoCollaborationPlan
from services.capabilities.document.early_document_support import run_early_document_prepare_flow
from services.capabilities.document.types import EarlyDocumentOutcome
from services.capabilities.video import mcp_video_support as _mcp_video_support
from services.capabilities.video import web_video_gather as _web_video_gather
from services.capabilities.video.mcp_video_support import McpVideoPendingOutcome
from services.capabilities.video.video_decision import (
    pan_jubu_celue_video,
    pan_jubu_celue_video_url,
    resolve_mcp_video_decision,
    shibie_video_url_yitu,
    shibie_video_yitu,
    video_url_yitu_from_plan_or_message,
)
from services.capabilities.video.web_video_gather import EarlyWebVideoOutcome

from .material_policy import _is_tool_allowed


def run_early_web_video_flow(
    *,
    video_url_decision: str,
    video_url_yitu: dict[str, Any],
    plan: AgnoCollaborationPlan,
    session_id: str,
    blocked_failures: list[dict[str, Any]],
    fetch_video_text_fn: Any | None = None,
) -> EarlyWebVideoOutcome:
    return _web_video_gather.run_early_web_video_flow(
        video_url_decision=video_url_decision,
        video_url_yitu=video_url_yitu,
        plan=plan,
        session_id=session_id,
        blocked_failures=blocked_failures,
        is_tool_allowed=_is_tool_allowed,
        fetch_video_text_fn=fetch_video_text_fn,
    )


def run_mcp_video_tool_and_pending(
    *,
    mcp_video_decision: str,
    video_yitu: dict[str, Any],
    plan: AgnoCollaborationPlan,
    session_id: str,
    blocked_failures: list[dict[str, Any]],
) -> McpVideoPendingOutcome:
    return _mcp_video_support.run_mcp_video_tool_and_pending(
        mcp_video_decision=mcp_video_decision,
        video_yitu=video_yitu,
        plan=plan,
        session_id=session_id,
        blocked_failures=blocked_failures,
        is_tool_allowed=_is_tool_allowed,
    )


def run_video_probe_stage(
    *,
    video_url_decision: str,
    video_url_yitu: dict[str, Any],
    plan: AgnoCollaborationPlan,
    session_id: str,
    blocked_failures: list[dict[str, Any]],
    fetch_video_text_fn: Any | None = None,
) -> EarlyWebVideoOutcome:
    return run_early_web_video_flow(
        video_url_decision=video_url_decision,
        video_url_yitu=video_url_yitu,
        plan=plan,
        session_id=session_id,
        blocked_failures=blocked_failures,
        fetch_video_text_fn=fetch_video_text_fn,
    )


__all__ = [
    "EarlyDocumentOutcome",
    "EarlyWebVideoOutcome",
    "McpVideoPendingOutcome",
    "run_early_document_prepare_flow",
    "pan_jubu_celue_video",
    "pan_jubu_celue_video_url",
    "resolve_mcp_video_decision",
    "run_early_web_video_flow",
    "run_video_probe_stage",
    "run_mcp_video_tool_and_pending",
    "shibie_video_url_yitu",
    "shibie_video_yitu",
    "video_url_yitu_from_plan_or_message",
]
