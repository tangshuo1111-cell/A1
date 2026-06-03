from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tools.video.errors import TASK_QUEUE_UNAVAILABLE, TOOL_DISABLED, TOOL_NOT_FOUND
from tools.video.tool_result import VideoToolResult

logger = logging.getLogger("light_maqa")


@dataclass
class VideoToolSchema:
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    call_fn: Callable[..., VideoToolResult]
    enabled: bool = True


_REGISTRY: dict[str, VideoToolSchema] = {}


def register(schema: VideoToolSchema) -> None:
    _REGISTRY[schema.tool_name] = schema


def disable_tool(tool_name: str) -> None:
    if tool_name in _REGISTRY:
        _REGISTRY[tool_name].enabled = False


def enable_tool(tool_name: str) -> None:
    if tool_name in _REGISTRY:
        _REGISTRY[tool_name].enabled = True


def call_tool(tool_name: str, **kwargs: Any) -> VideoToolResult:
    schema = _REGISTRY.get(tool_name)
    if schema is None:
        return VideoToolResult(
            tool_name=tool_name,
            status="failed",
            error_code=TOOL_NOT_FOUND,
            failure_reason=f"工具 {tool_name} 未注册",
        )
    if not schema.enabled:
        return VideoToolResult(
            tool_name=tool_name,
            status="failed",
            error_code=TOOL_DISABLED,
            failure_reason=f"工具 {tool_name} 已禁用",
        )
    t0 = time.monotonic()
    try:
        result = schema.call_fn(**kwargs)
        result.duration_ms = (time.monotonic() - t0) * 1000
        result.trace.insert(0, f"v16:video_registry:call tool={tool_name} status={result.status}")
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning("v16:video_registry exception tool=%s err=%s", tool_name, e)
        return VideoToolResult(
            tool_name=tool_name,
            status="failed",
            error_code=TASK_QUEUE_UNAVAILABLE,
            failure_reason=f"工具执行异常: {type(e).__name__}: {e}",
            duration_ms=(time.monotonic() - t0) * 1000,
        )

