"""
PDF 文档工具（MCP-compatible Adapter）。

技术路线（按技术方案 CSV 第 7 行 + Q3 拍板）：
  - PyMuPDF (fitz) 主解析：提取文本、页码、块信息
  - pdfplumber 表格 / 布局兜底
  - 两者都未安装 → error_code=pdf_parser_missing，不静默降级
  - pypdf 不作为默认主实现

扫描 PDF 检测：
  - 基于 valid_text_ratio（来自 quality.py）和 page 密度判断
  - 检测到扫描版 → status=failed, error_code=scanned_pdf_requires_ocr
  - is_scanned=True，next_action_hint=需要 OCR

metadata 至少包含：
  source_type=pdf / filename / page_count / page_number /
  block_index / table_index / is_scanned / extract_method /
  parser_name / content_hash
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
    PDF_ENCRYPTED,
    PDF_PARSER_MISSING,
    SCANNED_PDF_REQUIRES_OCR,
    UNSUPPORTED_FILE_TYPE,
)
from tools.document.limits import MAX_FILE_BYTES, MAX_PDF_PAGES, SCANNED_TEXT_RATIO_THRESHOLD
from tools.document.quality import assess_quality
from tools.document.registry import DocumentToolSchema, register
from tools.document.tool_result import DocumentToolResult

_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string"},
        "file_content": {"type": ["object", "null"]},
    },
    "required": ["file_path"],
}
_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "text": {"type": "string"},
        "metadata": {"type": "object"},
        "quality": {"type": "object"},
        "error_code": {"type": "string"},
    },
}


def _is_scanned_by_density(
    text: str, page_count: int
) -> bool:
    """基于文本密度判断是否为扫描版 PDF。"""
    if page_count == 0:
        return True
    chars_per_page = len((text or "").strip()) / page_count
    # 每页少于 50 个有效字符认为是扫描版
    return chars_per_page < 50


def _parse_with_pymupdf(
    content_bytes: bytes, max_pages: int
) -> tuple[str, list[dict], int, bool, str]:
    """
    用 PyMuPDF 解析 PDF。
    返回 (text, pages_meta, page_count, is_encrypted, error_msg)。
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return "", [], 0, False, "PyMuPDF not installed"

    try:
        doc = fitz.open(stream=content_bytes, filetype="pdf")
    except (OSError, ValueError, RuntimeError) as e:
        return "", [], 0, False, f"fitz.open failed: {e}"

    if doc.is_encrypted:
        doc.close()
        return "", [], doc.page_count, True, "pdf_encrypted"

    page_count = doc.page_count
    pages_meta: list[dict] = []
    all_text_parts: list[str] = []

    for page_num in range(min(page_count, max_pages)):
        page = doc[page_num]
        page_text = page.get_text("text")
        blocks = page.get_text("blocks")  # list of (x0,y0,x1,y1,text,block_no,block_type)

        block_texts: list[str] = []
        for bi, block in enumerate(blocks):  # noqa: B007
            if len(block) >= 5 and block[6] == 0:  # block_type 0 = text
                bt = str(block[4]).strip()
                if bt:
                    block_texts.append(bt)

        page_clean = page_text.strip()
        if page_clean:
            all_text_parts.append(f"[页码 {page_num + 1}]\n{page_clean}")

        pages_meta.append({
            "page_number": page_num + 1,
            "block_count": len(block_texts),
            "text_length": len(page_clean),
        })

    doc.close()
    text = "\n\n".join(all_text_parts)
    return text, pages_meta, page_count, False, ""


def _parse_with_pdfplumber(
    content_bytes: bytes, max_pages: int
) -> tuple[str, list[dict], int, str]:
    """
    用 pdfplumber 解析 PDF（表格 / 布局兜底）。
    返回 (text, pages_meta, page_count, error_msg)。
    """
    try:
        import pdfplumber
    except ImportError:
        return "", [], 0, "pdfplumber not installed"

    import io
    try:
        pdf = pdfplumber.open(io.BytesIO(content_bytes))
    except (OSError, ValueError, RuntimeError) as e:
        return "", [], 0, f"pdfplumber.open failed: {e}"

    page_count = len(pdf.pages)
    all_parts: list[str] = []
    pages_meta: list[dict] = []

    for page_num in range(min(page_count, max_pages)):
        page = pdf.pages[page_num]
        page_text = (page.extract_text() or "").strip()

        tables = page.extract_tables() or []
        table_texts: list[str] = []
        for ti, table in enumerate(tables):
            rows = []
            for row in (table or []):
                row_cells = [str(c) if c else "" for c in (row or [])]
                if any(row_cells):
                    rows.append(" | ".join(row_cells))
            if rows:
                table_texts.append(f"[表格{ti}]\n" + "\n".join(rows))

        combined = page_text
        if table_texts:
            combined += "\n" + "\n".join(table_texts)

        if combined.strip():
            all_parts.append(f"[页码 {page_num + 1}]\n{combined.strip()}")
        pages_meta.append({
            "page_number": page_num + 1,
            "text_length": len(combined.strip()),
            "table_count": len(tables),
        })

    pdf.close()
    text = "\n\n".join(all_parts)
    return text, pages_meta, page_count, ""


def _parse_pdf(
    file_path: str,
    file_content: bytes | None = None,
) -> DocumentToolResult:
    """PDF 文档解析 MCP-compatible Adapter。"""
    t0 = time.monotonic()
    path = Path(file_path)
    file_name = path.name or "unknown"
    trace: list[str] = [f"v16:parse_pdf:start file={file_name}"]

    if path.suffix.lower() != ".pdf":
        return DocumentToolResult(
            tool_name="parse_pdf",
            source_type="pdf",
            status="failed",
            error_code=UNSUPPORTED_FILE_TYPE,
            failure_reason=f"不支持的文件类型 {path.suffix}，parse_pdf 只接受 .pdf",
            trace=trace,
        )

    # 读取
    if file_content is not None:
        if len(file_content) > MAX_FILE_BYTES:
            return DocumentToolResult(
                tool_name="parse_pdf", source_type="pdf", status="failed",
                error_code=FILE_TOO_LARGE, failure_reason="文件大小超限", trace=trace,
            )
        content_bytes = file_content
    else:
        if not path.exists():
            return DocumentToolResult(
                tool_name="parse_pdf", source_type="pdf", status="failed",
                error_code=FILE_NOT_FOUND, failure_reason=f"文件不存在: {file_path}", trace=trace,
            )
        content_bytes = path.read_bytes()
        if len(content_bytes) > MAX_FILE_BYTES:
            return DocumentToolResult(
                tool_name="parse_pdf", source_type="pdf", status="failed",
                error_code=FILE_TOO_LARGE, failure_reason="文件大小超限", trace=trace,
            )

    # ── 尝试 PyMuPDF 主路径 ───────────────────────────────────────────────
    text, pages_meta, page_count, is_encrypted, err = _parse_with_pymupdf(
        content_bytes, MAX_PDF_PAGES
    )
    extract_method = "pymupdf"

    if is_encrypted:
        return DocumentToolResult(
            tool_name="parse_pdf", source_type="pdf", status="failed",
            error_code=PDF_ENCRYPTED,
            failure_reason="PDF 已加密，无法提取文本",
            next_action_hint="请解除 PDF 密码保护后重试",
            metadata={"source_type": "pdf", "filename": file_name, "is_scanned": False,
                      "page_count": page_count, "extract_method": "pymupdf"},
            trace=trace,
        )

    if err == "PyMuPDF not installed":
        trace.append("v16:parse_pdf:pymupdf_missing, try pdfplumber")
        text, pages_meta, page_count, plumber_err = _parse_with_pdfplumber(
            content_bytes, MAX_PDF_PAGES
        )
        extract_method = "pdfplumber"

        if plumber_err == "pdfplumber not installed":
            return DocumentToolResult(
                tool_name="parse_pdf", source_type="pdf", status="failed",
                error_code=PDF_PARSER_MISSING,
                failure_reason="PyMuPDF 和 pdfplumber 均未安装",
                next_action_hint="请执行 pip install PyMuPDF pdfplumber",
                trace=trace,
            )
        if plumber_err:
            return DocumentToolResult(
                tool_name="parse_pdf", source_type="pdf", status="failed",
                error_code=PARSE_FAILED, failure_reason=f"pdfplumber 解析失败: {plumber_err}",
                trace=trace,
            )
    elif err:
        # PyMuPDF 安装了但解析失败，尝试 pdfplumber 兜底
        trace.append(f"v16:parse_pdf:pymupdf_failed reason={err[:80]}, try pdfplumber")
        text2, pages_meta2, page_count2, plumber_err = _parse_with_pdfplumber(
            content_bytes, MAX_PDF_PAGES
        )
        if text2:
            text = text2
            pages_meta = pages_meta2
            page_count = page_count2
            extract_method = "pdfplumber_fallback"
        else:
            return DocumentToolResult(
                tool_name="parse_pdf", source_type="pdf", status="failed",
                error_code=PARSE_FAILED,
                failure_reason=f"PyMuPDF: {err}; pdfplumber: {plumber_err}",
                trace=trace,
            )

    if page_count > MAX_PDF_PAGES:
        trace.append(f"v16:parse_pdf:truncated to {MAX_PDF_PAGES} pages (total {page_count})")

    # ── 扫描 PDF 检测 ──────────────────────────────────────────────────────
    is_scanned = _is_scanned_by_density(text, page_count or 1)
    if not is_scanned and text:
        # 双重检测：quality 里的 valid_text_ratio
        from tools.document.quality import _valid_text_ratio
        vtr = _valid_text_ratio(text)
        if vtr < SCANNED_TEXT_RATIO_THRESHOLD and page_count > 0:
            is_scanned = True

    if is_scanned:
        trace.append("v16:parse_pdf:detected_scanned_pdf")
        scanned_metadata = {
            "source_type": "pdf",
            "filename": file_name,
            "page_count": page_count,
            "page_number": None,
            "block_index": None,
            "table_index": None,
            "is_scanned": True,
            "extract_method": extract_method,
            "parser_name": "parse_pdf",
            "content_hash": "",
        }
        return DocumentToolResult(
            tool_name="parse_pdf", source_type="pdf",
            status="failed",
            error_code=SCANNED_PDF_REQUIRES_OCR,
            failure_reason="检测到扫描版 PDF（每页文本密度极低），无法直接提取文本",
            next_action_hint="需要 OCR 才能提取内容，请使用 ocr_document 工具处理",
            metadata=scanned_metadata,
            quality={"quality_level": "failed", "text_length": 0, "valid_text_ratio": 0.0,
                     "is_scanned": True},
            trace=trace,
        )

    if not text.strip():
        return DocumentToolResult(
            tool_name="parse_pdf", source_type="pdf", status="failed",
            error_code=EMPTY_EXTRACTED_TEXT,
            failure_reason="PDF 提取后文本为空",
            metadata={"source_type": "pdf", "filename": file_name, "page_count": page_count,
                      "is_scanned": False, "extract_method": extract_method, "parser_name": "parse_pdf"},
            trace=trace,
        )

    quality = assess_quality(text, "pdf")
    content_hash = quality.get("content_hash", hashlib.md5(text.encode()).hexdigest())

    metadata: dict[str, Any] = {
        "source_type": "pdf",
        "filename": file_name,
        "page_count": page_count,
        "page_number": 1,      # 第一页起始
        "block_index": 0,
        "table_index": 0,
        "is_scanned": False,
        "extract_method": extract_method,
        "parser_name": "parse_pdf",
        "content_hash": content_hash,
        "pages_summary": pages_meta[:5],  # 前5页摘要
    }

    structured_data: dict[str, Any] = {
        "pages": pages_meta,
        "page_count": page_count,
    }

    duration_ms = (time.monotonic() - t0) * 1000
    trace.append(
        f"v16:parse_pdf:done method={extract_method} pages={page_count} "
        f"text_length={len(text)} quality={quality.get('quality_level')}"
    )

    return DocumentToolResult(
        tool_name="parse_pdf",
        source_type="pdf",
        status="success",
        text=text,
        structured_data=structured_data,
        metadata=metadata,
        quality=quality,
        warnings=quality.get("warnings", []),
        duration_ms=duration_ms,
        trace=trace,
    )


register(DocumentToolSchema(
    tool_name="parse_pdf",
    description="解析文本 PDF 文件，保留页码，检测扫描版，返回 ToolResult",
    input_schema=_INPUT_SCHEMA,
    output_schema=_OUTPUT_SCHEMA,
    call_fn=_parse_pdf,
))
