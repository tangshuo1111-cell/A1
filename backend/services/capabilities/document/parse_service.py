"""Document parse orchestration — registry-backed quick parse entry."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

from services.capabilities.contracts import CapabilityAdvice, CapabilityFact, QualityLevel
from tools.document.errors import SCANNED_PDF_REQUIRES_OCR
from tools.document.tool_result import DocumentToolResult


def _ensure_document_tools_registered() -> None:
    import tools.document  # noqa: F401


def call_parse_tool(tool_name: str, **kwargs: Any) -> DocumentToolResult:
    _ensure_document_tools_registered()
    from tools.document import registry

    return registry.call_tool(tool_name, **kwargs)


def resolve_tool_for_path(file_path: str | Path) -> str:
    ext = Path(file_path).suffix.lower()
    if ext in {".txt"}:
        return "parse_txt_document"
    if ext in {".md", ".markdown"}:
        return "parse_md_document"
    if ext == ".docx":
        return "parse_docx"
    if ext in {".xlsx", ".xlsm"}:
        return "parse_excel"
    if ext == ".pdf":
        return "parse_pdf"
    return "parse_txt_document"


def parse_text_or_table(
    file_path: str | Path,
    *,
    file_content: str | bytes | None = None,
    session_id: str = "",
) -> DocumentToolResult:
    del session_id
    tool_name = resolve_tool_for_path(file_path)
    kwargs: dict[str, Any] = {"file_path": str(file_path)}
    if file_content is not None:
        kwargs["file_content"] = file_content
    return call_parse_tool(tool_name, **kwargs)


def parse_pdf_quick(
    file_path: str | Path,
    *,
    file_content: str | bytes | None = None,
    session_id: str = "",
) -> DocumentToolResult:
    del session_id
    kwargs: dict[str, Any] = {"file_path": str(file_path)}
    if file_content is not None:
        kwargs["file_content"] = file_content
    return call_parse_tool("parse_pdf", **kwargs)


def _quality_from_parse_result(result: DocumentToolResult | None, *, has_material: bool) -> str:
    if has_material:
        level = str((result.quality or {}).get("quality_level", "") if result else "").strip()
        if level in {"good", "usable", "poor", "empty"}:
            return level
        return "usable"
    if result is not None and result.error_code:
        return "empty"
    return "empty"


def probe_document_capability(
    *,
    inline_text: str | None = None,
    file_content: str | bytes | None = None,
    file_path: str | Path | None = None,
    session_id: str = "",
    clock: Any | None = None,
) -> tuple[CapabilityFact, CapabilityAdvice, DocumentToolResult | None]:
    """Probe document parse / OCR need; returns facts + advice only (§9 / D1)."""
    del clock
    started = time.perf_counter()
    parse_result: DocumentToolResult | None = None
    page_count: int | None = None
    parser_name = ""
    ocr_required = False

    text = (inline_text or "").strip()
    if not text and isinstance(file_content, str) and file_content.strip():
        text = file_content.strip()
    if text:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        fact = CapabilityFact(
            lane="document",
            probe_elapsed_ms=elapsed_ms,
            page_count=1,
            ocr_required=False,
            quality_level="usable",
            metadata={"parser_name": "inline_text", "extract_quality": "usable"},
        )
        advice = CapabilityAdvice(
            suggested_mode="sync_ok",
            reason="inline_text_ready",
            next_action_hint="可继续 fast 文档摘要。",
        )
        return fact, advice, None

    path = Path(file_path) if file_path else None
    if path is None and isinstance(file_content, (bytes, bytearray)) and file_content:
        path = Path("upload.bin")

    if path is not None:
        parse_result = parse_text_or_table(path, file_content=file_content, session_id=session_id)
        parser_name = str(parse_result.tool_name or resolve_tool_for_path(path))
        page_count_raw = (parse_result.metadata or {}).get("page_count")
        try:
            page_count = int(page_count_raw) if page_count_raw is not None else None
        except (TypeError, ValueError):
            page_count = None
        ocr_required = parse_result.error_code == SCANNED_PDF_REQUIRES_OCR or bool(
            (parse_result.metadata or {}).get("ocr_required")
        )
        has_text = parse_result.status == "success" and bool((parse_result.text or "").strip())
        quality_level = _quality_from_parse_result(parse_result, has_material=has_text)
    else:
        has_text = False
        quality_level = "empty"

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if ocr_required:
        advice = CapabilityAdvice(
            suggested_mode="demote_to_async",
            reason="ocr_required",
            next_action_hint="扫描版 PDF 需 OCR，建议转后台 document_ocr 任务。",
        )
    elif has_text:
        advice = CapabilityAdvice(
            suggested_mode="sync_ok",
            reason="document_parse_ok",
            next_action_hint="可继续 fast 文档摘要。",
        )
    else:
        advice = CapabilityAdvice(
            suggested_mode="needs_user_confirm",
            reason=parse_result.error_code if parse_result else "document_empty",
            next_action_hint="未能提取文档正文，建议 complex 或 OCR。",
        )

    fact = CapabilityFact(
        lane="document",
        probe_elapsed_ms=elapsed_ms,
        page_count=page_count,
        ocr_required=ocr_required,
        quality_level=cast(QualityLevel, quality_level),
        metadata={
            "parser_name": parser_name,
            "extract_quality": quality_level,
            "error_code": parse_result.error_code if parse_result else "",
        },
    )
    return fact, advice, parse_result


def extract_inline_material(
    *,
    inline_text: str | None = None,
    file_content: str | bytes | None = None,
    file_path: str | Path | None = None,
    session_id: str = "",
) -> tuple[str, list[str], DocumentToolResult | None]:
    """Fast path：优先 inline 文本；否则尝试轻量 parse。"""
    text = (inline_text or "").strip()
    if text:
        return text, ["capability.document.parse_quick"], None
    if isinstance(file_content, str) and file_content.strip():
        return file_content.strip(), ["capability.document.parse_quick"], None
    if file_path:
        result = parse_text_or_table(file_path, file_content=file_content, session_id=session_id)
        if result.status == "success" and (result.text or "").strip():
            cap = (
                "capability.document.parse_pdf_quick"
                if Path(file_path).suffix.lower() == ".pdf"
                else "capability.document.parse_text_or_table"
            )
            return str(result.text).strip(), [cap], result
        return "", ["capability.document.parse_text_or_table"], result
    if isinstance(file_content, (bytes, bytearray)) and file_content:
        try:
            decoded = bytes(file_content).decode("utf-8").strip()
        except UnicodeDecodeError:
            decoded = ""
        if decoded:
            return decoded, ["capability.document.parse_quick"], None
    return "", [], None
