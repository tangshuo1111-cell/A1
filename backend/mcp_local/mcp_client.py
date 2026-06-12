"""
MCP 调用出口：可选真实 stdio MCP（子进程 FastMCP Server），失败则回退进程内模拟。

【注意】项目目录勿再命名为 `mcp/`，否则会遮蔽官方 `mcp` 包导致 stdio 联调失败。

新增「业务型 tool」概念：
- `BUSINESS_TOOL_NAMES` 列出主链可调用的业务型 MCP tool（当前唯一：`video_to_text`）；
- 这类 tool **必须** 走真子进程 stdio MCP——失败时明确返回 `transport=stdio_error`，
  **不允许** 静默回退到进程内模拟（否则就成了"普通函数互调冒充 MCP"）；
- 联调用 demo tool（ping / echo）保持原有行为：可走 stdio，也可回退本地模拟。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from config.settings import settings

# 本地模拟：name -> handler(arguments) -> JSON 可序列化对象
_LOCAL_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {}

# 当前收口唯一的业务型 MCP tool 名单（与 mcp_local.stdio_real 保持一致）
BUSINESS_TOOL_NAMES: set[str] = {"video_to_text"}


def is_business_tool(name: str) -> bool:
    """判断给定 tool 是否为业务型 MCP tool（必须走真 stdio）。"""
    return name in BUSINESS_TOOL_NAMES


def register_local_tool(name: str, fn: Callable[[dict[str, Any]], Any]) -> None:
    """注册进程内 MCP 风格工具（模拟用）。

    起：业务型 MCP tool **不允许** 在本表注册，避免被冒充为"真 MCP 调用"。
    """
    if name in BUSINESS_TOOL_NAMES:
        raise ValueError(
            f"业务型 MCP tool {name!r} 不允许注册本地模拟 handler——必须走真子进程 stdio MCP",
        )
    _LOCAL_HANDLERS[name] = fn


def _call_stdio(name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """走子进程 MCP；失败返回 None（业务型 tool 调用方需特殊处理，见 `call_mcp_tool`）。

    业务型 tool 强制走 stdio（无视 `mcp_use_stdio` env），demo tool 仍受 env 控制。
    """
    if not settings.enable_mcp:
        return None
    if not is_business_tool(name) and not settings.mcp_use_stdio:
        return None
    try:
        from mcp_local.stdio_real import call_tool_via_stdio

        return call_tool_via_stdio(name, arguments or {})
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "name": name,
            "error": str(e),
            "transport": "stdio_error",
            "note": "stdio MCP 调用异常",
        }


def call_mcp_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    统一 MCP tool 调用出口。

    transport 取值：
    - `mcp_stdio`：真子进程 MCP server 调用成功
    - `in_process_simulated`：仅 demo tool 在 stdio 未启用 / 失败时回退到本地模拟
    - `stdio_error`：业务型 tool 调用 stdio 失败（**不**回退本地模拟，明确收口为失败）
    - `none`：未知 tool

    约束：业务型 tool（`BUSINESS_TOOL_NAMES`）失败时返回明确失败，
    **不**伪装成功、**不**静默吞掉、**不**回退到 in_process_simulated。
    """
    stdio_res = _call_stdio(name, arguments)
    if stdio_res is not None and stdio_res.get("ok") and stdio_res.get("transport") == "mcp_stdio":
        return stdio_res

    if is_business_tool(name):
        # 业务型 tool：失败收口为失败，绝不回退本地模拟
        if stdio_res is not None:
            return stdio_res
        return {
            "ok": False,
            "name": name,
            "error": f"业务型 MCP tool {name!r} 必须走 stdio，但 ENABLE_MCP=False 或 stdio 未可用",
            "transport": "stdio_error",
        }

    # demo / 联调 tool：保留原有"可回退本地模拟"行为
    if name in _LOCAL_HANDLERS:
        try:
            payload = _LOCAL_HANDLERS[name](arguments)
            out = {
                "ok": True,
                "name": name,
                "result": payload,
                "transport": "in_process_simulated",
                "note": "进程内模拟，不是外部 MCP Server",
            }
            if stdio_res and not stdio_res.get("ok"):
                out["stdio_fallback_reason"] = stdio_res.get("error", "")
            return out
        except Exception as e:  # noqa: BLE001
            return {
                "ok": False,
                "name": name,
                "error": str(e),
                "transport": "in_process_simulated",
            }
    return {
        "ok": False,
        "name": name,
        "error": f"未知工具: {name}（stdio 未成功且未注册本地模拟）",
        "transport": "none",
    }


def _tool_ping(_arguments: dict[str, Any]) -> dict[str, Any]:
    return {"message": "pong", "detail": "本地 MCP 模拟链路可达"}


register_local_tool("ping", _tool_ping)
