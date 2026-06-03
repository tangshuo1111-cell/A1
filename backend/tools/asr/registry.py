from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tools.document.tool_result import DocumentToolResult


@dataclass
class AsrToolSchema:
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    call_fn: Callable[..., DocumentToolResult]
    enabled: bool = True


_REGISTRY: dict[str, AsrToolSchema] = {}


def register(schema: AsrToolSchema) -> None:
    _REGISTRY[schema.tool_name] = schema


def disable_tool(tool_name: str) -> None:
    if tool_name in _REGISTRY:
        _REGISTRY[tool_name].enabled = False


def enable_tool(tool_name: str) -> None:
    if tool_name in _REGISTRY:
        _REGISTRY[tool_name].enabled = True


def call_tool(tool_name: str, **kwargs: Any) -> DocumentToolResult:
    schema = _REGISTRY.get(tool_name)
    if schema is None:
        return DocumentToolResult(tool_name=tool_name, source_type="asr_transcript", status="failed", error_code="tool_not_found", failure_reason=f"工具 {tool_name} 未注册")
    if not schema.enabled:
        return DocumentToolResult(tool_name=tool_name, source_type="asr_transcript", status="failed", error_code="tool_disabled", failure_reason=f"工具 {tool_name} 已禁用")
    return schema.call_fn(**kwargs)

