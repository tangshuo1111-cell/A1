"""OCR document source parser."""

from __future__ import annotations

from pathlib import Path

from ._common import (
    SOURCE_TYPE_OCR_DOCUMENT,
    SourcePayload,
    _failed_payload,
    _make_source_id,
    _now_iso,
)


def parse_ocr_document_source(
    file_path: str,
    *,
    estimated_cost: float = 0.0,
    session_id: str = "",
) -> tuple[SourcePayload, str, str]:
    import tools.ocr  # noqa: F401
    from tools.ocr.registry import call_tool

    result = call_tool("ocr_document", file_path=file_path, estimated_cost=estimated_cost, session_id=session_id)
    parser_name = result.tool_name
    if not result.is_committable:
        return _failed_payload(
            source_type=SOURCE_TYPE_OCR_DOCUMENT,
            raw_source=file_path,
            title=Path(file_path).name,
            error_code=result.error_code or "ocr_failed",
            parser_name=parser_name,
            extra_meta={"file_path": file_path, "task_id": result.task_id, "failure_reason": result.failure_reason},
        ), parser_name, result.error_code or "ocr_failed"
    meta = dict(result.metadata or {})
    meta.update({"parser_name": parser_name, "created_at": _now_iso(), "chunk_index": 0, "task_id": result.task_id})
    if result.task_id:
        meta["v16_task_id"] = result.task_id
    payload = SourcePayload(
        source_type=SOURCE_TYPE_OCR_DOCUMENT,
        source_id=_make_source_id("ocr_document", file_path),
        title=Path(file_path).name,
        text=result.text.strip(),
        metadata=meta,
        raw_source=file_path,
    )
    return payload, parser_name, ""
