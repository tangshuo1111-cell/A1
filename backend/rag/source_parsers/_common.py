"""Shared helpers for source_parsers submodules."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from rag.pending_schema import (  # noqa: F401
    SOURCE_TYPE_ASR_TRANSCRIPT,
    SOURCE_TYPE_DOCX,
    SOURCE_TYPE_LOCAL_VIDEO,
    SOURCE_TYPE_OCR_DOCUMENT,
    SOURCE_TYPE_PDF,
    SOURCE_TYPE_TEXT,
    SOURCE_TYPE_TEXT_FILE,
    SOURCE_TYPE_WEB_SEARCH,
    SOURCE_TYPE_WEB_URL,
    SOURCE_TYPE_WEB_VIDEO,
    SOURCE_TYPE_XLSX,
    SourcePayload,
)

logger = logging.getLogger("light_maqa")

_SUPPORTED_TEXT_EXTS = {".txt", ".md"}


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _make_source_id(prefix: str, raw: str, suffix: str = "") -> str:
    """生成稳定、可读的 source_id。"""
    clean = re.sub(r"[^\w.\-/]+", "_", raw)[:80]
    return f"{prefix}/{clean}{suffix}"


def _extract_html_title(html: str) -> str:
    """简单提取 HTML <title> 标签内容。"""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:200]
    return ""


def _failed_payload(
    *,
    source_type: str,
    raw_source: str,
    title: str,
    error_code: str,
    parser_name: str,
    extra_meta: dict[str, Any] | None = None,
) -> SourcePayload:
    """构造失败时的空 payload（text 为空）。"""
    meta: dict[str, Any] = {
        "title": title,
        "parser_name": parser_name,
        "created_at": _now_iso(),
        "source_type": source_type,
        "error_code": error_code,
        "chunk_index": 0,
    }
    if extra_meta:
        meta.update(extra_meta)
    return SourcePayload(
        source_type=source_type,
        source_id=_make_source_id(source_type, raw_source or "error"),
        title=title,
        text="",
        metadata=meta,
        raw_source=raw_source,
    )
