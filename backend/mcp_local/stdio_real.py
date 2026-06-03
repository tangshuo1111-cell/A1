"""
通过官方 `mcp` 包启动子进程 FastMCP Server 并调用单个 tool（同步封装）。
依赖：pip install mcp（依赖见 pyproject.toml / requirements.lock）

V7 第 1 轮：新增按 **业务型 tool 名** 分流到对应 server module 的最小路由表。
- `video_to_text` → `mcp_servers.video_min_server`（首条业务型 MCP server，本轮当前收口唯一）
- 其它 tool → 走 `settings.mcp_stdio_module`（默认仍是 ping/echo demo `mcp_servers.min_server`）

`BUSINESS_TOOL_SERVERS` 是当前 V7 第 1 轮的收口表，**只允许有一条**业务型映射；
要新增条目必须先升版（V7 后续轮）并通过任务看板。
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from config.settings import settings

# V7 第 1 轮：业务型 MCP tool → 对应 server module。
# 当前收口唯一：video_to_text。明确不是 ping/echo/demo。
BUSINESS_TOOL_SERVERS: dict[str, str] = {
    "video_to_text": "mcp_servers.video_min_server",
}


def _resolve_server_module(tool_name: str) -> str:
    """按 tool 名解析对应的 server module；找不到时回退 settings 默认。"""
    mod = BUSINESS_TOOL_SERVERS.get(tool_name)
    if mod:
        return mod
    return settings.mcp_stdio_module.strip() or "mcp_servers.min_server"


def _tool_result_to_payload(result: Any) -> dict[str, Any]:
    texts: list[str] = []
    for block in getattr(result, "content", None) or []:
        t = getattr(block, "text", None)
        if t is not None:
            texts.append(str(t))
    return {
        "texts": texts,
        "joined": "\n".join(texts),
        "is_error": bool(getattr(result, "isError", False)),
    }


async def _call_tool_async(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    mod = _resolve_server_module(name)
    env = os.environ.copy()
    backend_root = str(settings.project_root / "backend")
    old_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = backend_root if not old_pythonpath else f"{backend_root}{os.pathsep}{old_pythonpath}"
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", mod],
        cwd=str(settings.project_root),
        env=env,
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool(name, arguments or {})
        payload = _tool_result_to_payload(result)
        ok = not payload["is_error"]
        return {
            "ok": ok,
            "name": name,
            "result": {"message": payload["joined"] or "(empty)", "texts": payload["texts"]},
            "transport": "mcp_stdio",
            "note": f"子进程 MCP 模块 {mod!r}",
        }


def call_tool_via_stdio(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """同步入口，供 middle_agent / mcp_client 调用。"""
    try:
        return asyncio.run(_call_tool_async(name, arguments))
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "name": name,
            "error": str(e),
            "transport": "stdio_error",
        }
