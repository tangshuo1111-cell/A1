"""Document source parser (docx / xlsx / pdf)."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from ._common import (
    SOURCE_TYPE_DOCX,
    SOURCE_TYPE_OCR_DOCUMENT,
    SOURCE_TYPE_PDF,
    SOURCE_TYPE_TEXT_FILE,
    SOURCE_TYPE_XLSX,
    SourcePayload,
    _failed_payload,
    _make_source_id,
    _now_iso,
)

# ── 文档来源 parser（docx / xlsx / pdf）───────────────────────────────
_DOC_EXT_TO_SOURCE_TYPE: dict[str, str] = {
    ".docx": SOURCE_TYPE_DOCX,
    ".xlsx": SOURCE_TYPE_XLSX,
    ".xlsm": SOURCE_TYPE_XLSX,
    ".pdf": SOURCE_TYPE_PDF,
}
_DOC_EXT_TO_TOOL: dict[str, str] = {
    ".docx": "parse_docx",
    ".xlsx": "parse_excel",
    ".xlsm": "parse_excel",
    ".pdf": "parse_pdf",
}


def parse_document_source(
    file_path: str | Path,
    *,
    file_content: str | bytes | None = None,
) -> tuple[SourcePayload, str, str]:
    """
    文档类文件（docx / xlsx / pdf）→ ToolResult → SourcePayload。

    通过 document tool registry 调用对应的 MCP-compatible Adapter。
    失败时返回带 error_code 的 SourcePayload（text 为空）。

    返回 (payload, parser_name, error_code)。
    """
    import tools.document  # noqa: F401 — 触发所有工具注册
    from tools.document.errors import SCANNED_PDF_REQUIRES_OCR
    from tools.document.registry import call_tool

    path = Path(file_path) if file_path else Path("")
    ext = path.suffix.lower()
    file_name = path.name or "unknown"

    tool_name = _DOC_EXT_TO_TOOL.get(ext)
    source_type = _DOC_EXT_TO_SOURCE_TYPE.get(ext)
    if not tool_name or not source_type:
        return _failed_payload(
            source_type=SOURCE_TYPE_TEXT_FILE,
            raw_source=str(path),
            title=file_name,
            error_code="unsupported_file_type",
            parser_name="parse_document_source",
            extra_meta={"file_name": file_name, "file_ext": ext},
        ), "parse_document_source", "unsupported_file_type"

    raw_bytes: bytes | None = None
    if file_content is not None:
        if isinstance(file_content, bytes):
            raw_bytes = file_content
        else:
            raw_bytes = str(file_content).encode("utf-8", errors="replace")

    result = call_tool(tool_name, file_path=str(path), file_content=raw_bytes)

    parser_name = result.tool_name
    error_code = result.error_code or ""

    if tool_name == "parse_pdf" and error_code == SCANNED_PDF_REQUIRES_OCR:
        import tools.ocr  # noqa: F401 — 注册 OCR 工具

        from .ocr import parse_ocr_document_source

        # 上传链路：字节不在磁盘上，OCR 工具按 file_path 读盘，需先把上传字节落临时文件。
        _ocr_path = str(path)
        _tmp_ocr_path: Path | None = None
        if raw_bytes is not None and not path.exists():
            import tempfile

            _suffix = ext or ".pdf"
            _fd, _tmp_name = tempfile.mkstemp(suffix=_suffix, prefix="v16_ocr_")
            try:
                with __import__("os").fdopen(_fd, "wb") as _fh:
                    _fh.write(raw_bytes)
                _tmp_ocr_path = Path(_tmp_name)
                _ocr_path = _tmp_name
            except OSError:
                _tmp_ocr_path = None
        try:
            payload_o, parser_o, err_o = parse_ocr_document_source(_ocr_path, estimated_cost=0.0, session_id="")
        finally:
            if _tmp_ocr_path is not None:
                with contextlib.suppress(OSError):
                    _tmp_ocr_path.unlink(missing_ok=True)
        if not err_o:
            return payload_o, parser_o, ""
        return _failed_payload(
            source_type=SOURCE_TYPE_OCR_DOCUMENT,
            raw_source=str(path),
            title=file_name,
            error_code=err_o,
            parser_name=parser_o,
            extra_meta={
                "file_name": file_name,
                "file_ext": ext,
                "failure_reason": "扫描 PDF 需 OCR；OCR 跟进失败",
                "prior_pdf_error": SCANNED_PDF_REQUIRES_OCR,
            },
        ), parser_o, err_o

    if not result.is_committable:
        return _failed_payload(
            source_type=source_type,
            raw_source=str(path),
            title=file_name,
            error_code=error_code or "parse_failed",
            parser_name=parser_name,
            extra_meta={
                "file_name": file_name,
                "file_ext": ext,
                "failure_reason": result.failure_reason,
                "next_action_hint": result.next_action_hint,
                "tool_trace": result.trace[:5],
            },
        ), parser_name, error_code or "parse_failed"

    text = result.text.strip()
    meta: dict[str, Any] = {
        "title": file_name,
        "file_name": file_name,
        "file_ext": ext,
        "source_type": source_type,
        "parser_name": parser_name,
        "created_at": _now_iso(),
        "chunk_index": 0,
        "v16_tool_name": result.tool_name,
        "v16_mcp_mode": result.mcp_mode,
        "v16_extract_method": result.metadata.get("extract_method", ""),
        "v16_quality_level": result.quality.get("quality_level", ""),
        "v16_text_length": result.quality.get("text_length", len(text)),
        "v16_valid_text_ratio": result.quality.get("valid_text_ratio", 0.0),
        "v16_content_hash": result.metadata.get("content_hash", ""),
    }
    for k, v in (result.metadata or {}).items():
        if k not in meta:
            meta[k] = v

    sid = _make_source_id(source_type, file_name)
    payload = SourcePayload(
        source_type=source_type,
        source_id=sid,
        title=file_name,
        text=text,
        metadata=meta,
        raw_source=str(path),
    )
    return payload, parser_name, ""
