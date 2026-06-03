"""
V16 R1：txt / md 文档工具（MCP-compatible Adapter）。

复用现有 parse_file_source 逻辑，统一输出 DocumentToolResult。
metadata 补充 V16 要求字段：text_length / file_ext / content_hash 等。
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from tools.document.errors import (
    EMPTY_EXTRACTED_TEXT,
    FILE_NOT_FOUND,
    FILE_TOO_LARGE,
    PARSE_FAILED,
)
from tools.document.limits import MAX_FILE_BYTES, MAX_TEXT_CHARS
from tools.document.quality import assess_quality
from tools.document.registry import DocumentToolSchema, register
from tools.document.tool_result import DocumentToolResult

# ── input / output schema ──────────────────────────────────────────────────
_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "description": "文件路径"},
        "file_content": {
            "type": ["string", "null"],
            "description": "文件内容（bytes 或 str，可选，优先于 file_path 读取）",
        },
        "source_type": {"type": "string", "enum": ["txt", "md"], "default": "txt"},
    },
    "required": ["file_path"],
}

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["success", "failed"]},
        "text": {"type": "string"},
        "metadata": {"type": "object"},
        "quality": {"type": "object"},
        "error_code": {"type": "string"},
    },
}


def _parse_text_document(
    file_path: str,
    file_content: str | bytes | None = None,
    source_type: str = "txt",
) -> DocumentToolResult:
    """
    txt / md 文档解析（MCP-compatible Adapter）。

    mcp_mode = mcp_compatible_adapter（本轮不外置 MCP Server）。
    """
    t0 = time.monotonic()
    path = Path(file_path) if file_path else Path("")
    ext = path.suffix.lower()
    file_name = path.name or "unknown"

    # 确定 source_type
    if ext == ".md":
        _src_type = "md"
    elif ext == ".txt":
        _src_type = "txt"
    else:
        # source_type 参数兜底
        _src_type = source_type if source_type in ("txt", "md") else "txt"

    trace: list[str] = [f"v16:parse_text:start ext={ext} source_type={_src_type}"]

    # 文件大小检查（传入 bytes 时）
    if isinstance(file_content, bytes) and len(file_content) > MAX_FILE_BYTES:
        return DocumentToolResult(
            tool_name=f"parse_{_src_type}_document",
            source_type=_src_type,
            status="failed",
            error_code=FILE_TOO_LARGE,
            failure_reason=f"文件大小超限（{len(file_content)} bytes，最大 {MAX_FILE_BYTES} bytes）",
            next_action_hint="请压缩文件后重试",
            trace=trace,
        )

    # 读取内容
    if file_content is not None:
        if isinstance(file_content, bytes):
            raw_text = file_content.decode("utf-8", errors="replace")
        else:
            raw_text = str(file_content)
    else:
        if not path.exists():
            return DocumentToolResult(
                tool_name=f"parse_{_src_type}_document",
                source_type=_src_type,
                status="failed",
                error_code=FILE_NOT_FOUND,
                failure_reason=f"文件不存在: {file_path}",
                trace=trace,
            )
        try:
            raw_bytes = path.read_bytes()
            if len(raw_bytes) > MAX_FILE_BYTES:
                return DocumentToolResult(
                    tool_name=f"parse_{_src_type}_document",
                    source_type=_src_type,
                    status="failed",
                    error_code=FILE_TOO_LARGE,
                    failure_reason=f"文件大小超限（{len(raw_bytes)} bytes）",
                    next_action_hint="请压缩文件后重试",
                    trace=trace,
                )
            raw_text = raw_bytes.decode("utf-8", errors="replace")
        except (OSError, ValueError, RuntimeError) as e:
            return DocumentToolResult(
                tool_name=f"parse_{_src_type}_document",
                source_type=_src_type,
                status="failed",
                error_code=PARSE_FAILED,
                failure_reason=f"文件读取失败: {e}",
                trace=trace,
            )

    text = raw_text.strip()
    if not text:
        return DocumentToolResult(
            tool_name=f"parse_{_src_type}_document",
            source_type=_src_type,
            status="failed",
            error_code=EMPTY_EXTRACTED_TEXT,
            failure_reason="文件内容为空",
            trace=trace,
        )

    # 截断超长文本
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
        trace.append(f"v16:parse_text:truncated to {MAX_TEXT_CHARS} chars")

    quality = assess_quality(text, _src_type)
    content_hash = quality.get("content_hash", hashlib.md5(text.encode()).hexdigest())

    metadata: dict[str, Any] = {
        "source_type": _src_type,
        "filename": file_name,
        "file_ext": ext,
        "text_length": len(text),
        "parser_name": f"parse_{_src_type}_document",
        "extract_method": "plain_text_read",
        "content_hash": content_hash,
    }

    trace.append(
        f"v16:parse_text:done text_length={len(text)} quality={quality.get('quality_level')}"
    )
    duration_ms = (time.monotonic() - t0) * 1000

    return DocumentToolResult(
        tool_name=f"parse_{_src_type}_document",
        source_type=_src_type,
        status="success",
        text=text,
        metadata=metadata,
        quality=quality,
        warnings=quality.get("warnings", []),
        duration_ms=duration_ms,
        trace=trace,
    )


# ── 注册到 registry ──────────────────────────────────────────────────────────
register(DocumentToolSchema(
    tool_name="parse_txt_document",
    description="解析 txt 纯文本文件，返回 ToolResult",
    input_schema=_INPUT_SCHEMA,
    output_schema=_OUTPUT_SCHEMA,
    call_fn=lambda **kw: _parse_text_document(**kw, source_type="txt"),
))

register(DocumentToolSchema(
    tool_name="parse_md_document",
    description="解析 Markdown 文件，返回 ToolResult",
    input_schema=_INPUT_SCHEMA,
    output_schema=_OUTPUT_SCHEMA,
    call_fn=lambda **kw: _parse_text_document(**kw, source_type="md"),
))
