"""
V16 R1：文档工具包入口。

import 本包时自动注册所有文档工具到 registry。
"""

from tools.document import (
    errors,
    limits,
    parse_docx,
    parse_excel,
    parse_pdf,
    parse_text,
    quality,
    registry,
    tool_result,
)

__all__ = [
    "errors",
    "limits",
    "parse_docx",
    "parse_excel",
    "parse_pdf",
    "parse_text",
    "quality",
    "registry",
    "tool_result",
]
