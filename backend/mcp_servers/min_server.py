"""
最小真实 MCP Server（stdio + FastMCP），用于与 middle_agent 联调。

运行（一般由客户端自动拉起，无需手敲）：
  python -m mcp_servers.min_server

提供工具：
- ping：健康检查
- echo：回显文本（演示用）
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

app = FastMCP(
    "light_maqa_min",
    instructions="LightMultiAgentQA 最小 stdio MCP 演示，仅用于验证真实 MCP 链路。",
)


@app.tool()
def ping() -> str:
    """健康检查，返回 pong。"""
    return "pong"


@app.tool()
def echo(text: str) -> str:
    """回显输入，用于验证 tool 参数传递。"""
    return f"echo:{text}"


def main() -> None:
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
