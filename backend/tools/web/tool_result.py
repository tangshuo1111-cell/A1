"""
V16 R2: unified web tool result.

WebToolResult extends the V16 R1 DocumentToolResult instead of creating a
second incompatible shape. Web-specific fields are first-class for tests and
reports, while metadata keeps the same downstream mapping style.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tools.document.tool_result import DocumentToolResult


@dataclass
class WebToolResult(DocumentToolResult):
    source_type: str = "web_url"
    url: str = ""
    final_url: str = ""
    domain: str = ""
    title: str = ""
    extraction_method: str = ""
    fetch_method: str = "static"
    http_status: int = 0
    requires_cookie: bool = False
    cookie_used: bool = False

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = {}
        self.metadata.update(
            {
                "url": self.url,
                "final_url": self.final_url or self.url,
                "domain": self.domain,
                "title": self.title,
                "source_type": self.source_type,
                "extraction_method": self.extraction_method,
                "fetch_method": self.fetch_method,
                "http_status": self.http_status,
                "requires_cookie": self.requires_cookie,
                "cookie_used": bool(self.cookie_used),
                "mcp_mode": self.mcp_mode,
            }
        )

    def to_trace_dict(self) -> dict[str, Any]:
        data = super().to_trace_dict()
        data.update(
            {
                "url": self.url,
                "final_url": self.final_url or self.url,
                "domain": self.domain,
                "title": self.title,
                "extraction_method": self.extraction_method,
                "fetch_method": self.fetch_method,
                "http_status": self.http_status,
                "requires_cookie": self.requires_cookie,
                "cookie_used": bool(self.cookie_used),
            }
        )
        return data
