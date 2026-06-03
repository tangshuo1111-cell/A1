"""
MCP 工具出口（tools 层薄封装）。

真实实现仍在 mcp_local；此处仅固定「工具分层」边界，避免业务直接依赖子包路径。
"""

from mcp_local import mcp_client

__all__ = ["mcp_client"]
