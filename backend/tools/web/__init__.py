"""V16 R2 web tools package.

Importing this package registers all web MCP-compatible adapters.
"""

from tools.web import (
    errors,
    fetch_dynamic_page,
    fetch_web_page,
    fetch_with_cookie,
    limits,
    quality,
    registry,
    tool_result,
)

__all__ = [
    "errors",
    "limits",
    "fetch_dynamic_page",
    "fetch_web_page",
    "fetch_with_cookie",
    "quality",
    "registry",
    "tool_result",
]
