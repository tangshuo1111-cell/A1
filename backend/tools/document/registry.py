"""
文档工具 MCP-compatible Adapter 注册表。

设计目标：
  1. 每个文档工具注册后具备 input_schema / output_schema / ToolResult / trace /
     可禁用 / 可替换 语义；
  2. Middle / service 通过 registry 调用，不直接 import 具体 parser；
  3. 任何工具被 disable_tool() 后，调用该工具返回 tool_disabled 错误，
     且不会悄悄走旧 parser（测试可验证）。

为什么本轮不外置 MCP Server：
  - 当前项目主链（Main/Middle/Answer）在进程内协作；文档解析涉及
    本地文件字节流，外置 Server 需要 stdio/TCP + 序列化，成本与
    进程管理复杂度不对等，目标是"真实落地"而非"MCP形式化"。
  - 技术方案（V16-V17 技术方案 CSV 第 4-7 行）明确允许 Adapter 过渡，
    条件是：有 tool_name/input_schema/output_schema/ToolResult/error_code/
    metadata/trace/可禁用/可替换。本 registry 均已满足。
  - 后续 若需要真 MCP Server，可把 registry 改为 MCP client
    调用，接口不变。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tools.document.errors import TOOL_DISABLED, TOOL_NOT_FOUND
from tools.document.tool_result import DocumentToolResult

logger = logging.getLogger("light_maqa")


# ── Schema 类型定义 ─────────────────────────────────────────────────────────
@dataclass
class DocumentToolSchema:
    """单个文档工具的注册信息（MCP-compatible Adapter 标准）。"""

    tool_name: str
    description: str
    input_schema: dict[str, Any]    # JSON Schema 风格
    output_schema: dict[str, Any]   # JSON Schema 风格
    call_fn: Callable[..., DocumentToolResult]
    enabled: bool = True


# ── 全局注册表 ──────────────────────────────────────────────────────────────
_REGISTRY: dict[str, DocumentToolSchema] = {}


def register(schema: DocumentToolSchema) -> None:
    """向 registry 注册一个 document tool。可在模块 import 时调用（幂等）。"""
    _REGISTRY[schema.tool_name] = schema
    logger.debug("v16:doc_registry:registered tool=%s", schema.tool_name)


def get_tool(tool_name: str) -> DocumentToolSchema | None:
    return _REGISTRY.get(tool_name)


def is_enabled(tool_name: str) -> bool:
    s = _REGISTRY.get(tool_name)
    return s is not None and s.enabled


def disable_tool(tool_name: str) -> None:
    """禁用工具（测试可用于验证禁用后不走旧链）。"""
    if tool_name in _REGISTRY:
        _REGISTRY[tool_name].enabled = False
        logger.info("v16:doc_registry:disabled tool=%s", tool_name)


def enable_tool(tool_name: str) -> None:
    """重新启用工具。"""
    if tool_name in _REGISTRY:
        _REGISTRY[tool_name].enabled = True


def list_tools() -> list[dict[str, Any]]:
    """返回所有工具的摘要（供 trace / 报告使用）。"""
    return [
        {
            "tool_name": s.tool_name,
            "enabled": s.enabled,
            "mcp_mode": "mcp_compatible_adapter",
            "description": s.description,
        }
        for s in _REGISTRY.values()
    ]


def call_tool(tool_name: str, **kwargs: Any) -> DocumentToolResult:
    """
    通过 registry 调用文档工具。

    - 工具未注册 → error_code=tool_not_found
    - 工具已禁用 → error_code=tool_disabled
    - 工具执行异常 → error_code=parse_failed + failure_reason

    自动记录 duration_ms。
    """
    schema = _REGISTRY.get(tool_name)
    if schema is None:
        return DocumentToolResult(
            tool_name=tool_name,
            status="failed",
            error_code=TOOL_NOT_FOUND,
            failure_reason=f"工具 {tool_name} 未在 registry 注册",
            trace=[f"v16:registry:tool_not_found tool={tool_name}"],
        )

    if not schema.enabled:
        return DocumentToolResult(
            tool_name=tool_name,
            status="failed",
            error_code=TOOL_DISABLED,
            failure_reason=f"工具 {tool_name} 已被禁用",
            trace=[f"v16:registry:tool_disabled tool={tool_name}"],
        )

    t0 = time.monotonic()
    try:
        result = schema.call_fn(**kwargs)
        result.duration_ms = (time.monotonic() - t0) * 1000
        result.trace.insert(0, f"v16:registry:call tool={tool_name} status={result.status}")
        return result
    except Exception as e:  # noqa: BLE001 — 工具边界：任意实现异常收敛为结构化失败
        duration_ms = (time.monotonic() - t0) * 1000
        logger.warning("v16:registry:tool_exception tool=%s err=%s", tool_name, e)
        return DocumentToolResult(
            tool_name=tool_name,
            status="failed",
            error_code="parse_failed",
            failure_reason=f"工具执行异常: {type(e).__name__}: {e}",
            duration_ms=duration_ms,
            trace=[f"v16:registry:exception tool={tool_name} err={type(e).__name__}"],
        )
