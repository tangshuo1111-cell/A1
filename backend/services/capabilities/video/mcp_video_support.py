"""Local MCP video_to_text → pending prepare."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mcp_local import mcp_client
from services.capabilities.knowledge.pending_ingestion_service import prepare_video_source
from services.capabilities.knowledge.pending_service import SOURCE_TYPE_LOCAL_VIDEO

logger = logging.getLogger("light_maqa")


@dataclass
class McpVideoPendingOutcome:
    mcp_video_text: str | None = None
    mcp_video_path: str | None = None
    mcp_video_ok: bool = False
    mcp_video_error: str = ""
    mcp_video_pending_id: str | None = None
    mcp_video_ingest_error: str = ""
    mcp_video_pending_item: Any = None
    mcp_video_source: str | None = None


def run_mcp_video_tool_and_pending(
    *,
    mcp_video_decision: str,
    video_yitu: dict[str, Any],
    plan: Any,
    session_id: str,
    blocked_failures: list[dict[str, Any]],
    is_tool_allowed: Callable[[Any, str], bool],
) -> McpVideoPendingOutcome:
    out = McpVideoPendingOutcome()
    out.mcp_video_path = video_yitu.get("mp4_path")
    if mcp_video_decision != "call_video_to_text":
        return out
    if not is_tool_allowed(plan, "mcp_video_to_text"):
        out.mcp_video_error = "not_allowed_by_plan"
        blocked_failures.append({
            "tool": "mcp_video_to_text",
            "reason": "not_allowed_by_plan",
            "recoverable": False,
        })
        return out
    mcp_res = mcp_client.call_mcp_tool("video_to_text", {"mp4_path": video_yitu["mp4_path"]})
    transport = str(mcp_res.get("transport", ""))
    if transport != "mcp_stdio" or not mcp_res.get("ok"):
        out.mcp_video_error = str(
            mcp_res.get("error") or f"业务型 MCP 调用未走真 stdio (transport={transport})"
        )
        return out
    joined = ((mcp_res.get("result") or {}).get("message")) or ""
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(joined) if joined else {}
    except json.JSONDecodeError as je:
        out.mcp_video_error = f"video_to_text 返回非 JSON: {je}"
    if payload.get("ok"):
        out.mcp_video_ok = True
        out.mcp_video_text = str(payload.get("text") or "") or None
        out.mcp_video_source = str(payload.get("source_id") or "") or None
        if payload.get("source_path"):
            out.mcp_video_path = str(payload["source_path"])
    elif not out.mcp_video_error:
        out.mcp_video_error = str(payload.get("error") or "video_to_text 失败")
    if out.mcp_video_ok and out.mcp_video_text:
        try:
            pending = prepare_video_source(
                source_type=SOURCE_TYPE_LOCAL_VIDEO,
                raw_source=out.mcp_video_path or out.mcp_video_source or "",
                video_text=out.mcp_video_text,
                session_id=session_id,
                title=out.mcp_video_source or "",
                text_source="subtitle",
            )
            out.mcp_video_pending_id = pending.pending_id
            out.mcp_video_pending_item = pending
        except Exception as exc:  # noqa: BLE001
            out.mcp_video_ingest_error = (
                f"prepare_video_source 失败: {type(exc).__name__}: {str(exc)[:120]}"
            )
    return out
