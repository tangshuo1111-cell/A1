"""V16 R2 web MCP-compatible Adapter registry."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tools.web.errors import FETCH_FAILED, TOOL_DISABLED, TOOL_NOT_FOUND
from tools.web.tool_result import WebToolResult

logger = logging.getLogger("light_maqa")


@dataclass
class WebToolSchema:
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    call_fn: Callable[..., WebToolResult]
    enabled: bool = True


_REGISTRY: dict[str, WebToolSchema] = {}


def register(schema: WebToolSchema) -> None:
    _REGISTRY[schema.tool_name] = schema
    logger.debug("v16:web_registry:registered tool=%s", schema.tool_name)


def get_tool(tool_name: str) -> WebToolSchema | None:
    return _REGISTRY.get(tool_name)


def disable_tool(tool_name: str) -> None:
    if tool_name in _REGISTRY:
        _REGISTRY[tool_name].enabled = False
        logger.info("v16:web_registry:disabled tool=%s", tool_name)


def enable_tool(tool_name: str) -> None:
    if tool_name in _REGISTRY:
        _REGISTRY[tool_name].enabled = True


def is_enabled(tool_name: str) -> bool:
    s = _REGISTRY.get(tool_name)
    return bool(s and s.enabled)


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "tool_name": s.tool_name,
            "enabled": s.enabled,
            "mcp_mode": "mcp_compatible_adapter",
            "description": s.description,
            "input_schema": s.input_schema,
            "output_schema": s.output_schema,
        }
        for s in _REGISTRY.values()
    ]


def call_tool(tool_name: str, **kwargs: Any) -> WebToolResult:
    schema = _REGISTRY.get(tool_name)
    if schema is None:
        return WebToolResult(
            tool_name=tool_name,
            status="failed",
            error_code=TOOL_NOT_FOUND,
            failure_reason=f"工具 {tool_name} 未在 web registry 注册",
            trace=[f"v16:web_registry:tool_not_found tool={tool_name}"],
        )
    if not schema.enabled:
        return WebToolResult(
            tool_name=tool_name,
            status="failed",
            error_code=TOOL_DISABLED,
            failure_reason=f"工具 {tool_name} 已被禁用",
            trace=[f"v16:web_registry:tool_disabled tool={tool_name}"],
        )
    t0 = time.monotonic()
    try:
        result = schema.call_fn(**kwargs)
        result.duration_ms = (time.monotonic() - t0) * 1000
        result.trace.insert(0, f"v16:web_registry:call tool={tool_name} status={result.status}")
        return result
    except Exception as e:  # noqa: BLE001
        logger.warning("v16:web_registry:tool_exception tool=%s err=%s", tool_name, e)
        return WebToolResult(
            tool_name=tool_name,
            status="failed",
            error_code=FETCH_FAILED,
            failure_reason=f"工具执行异常: {type(e).__name__}: {e}",
            duration_ms=(time.monotonic() - t0) * 1000,
            trace=[f"v16:web_registry:exception tool={tool_name} err={type(e).__name__}"],
        )
