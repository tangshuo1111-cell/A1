"""Text and text-file source parsers."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from ._common import (
    _SUPPORTED_TEXT_EXTS,
    SOURCE_TYPE_TEXT,
    SOURCE_TYPE_TEXT_FILE,
    SourcePayload,
    _failed_payload,
    _make_source_id,
    _now_iso,
    logger,
)


# ── 1. 文本来源 ──────────────────────────────────────────────────────────
def parse_text_source(
    text: str,
    *,
    session_id: str = "",
    title: str = "",
) -> tuple[SourcePayload, str, str]:
    """
    直接文本 prepare。

    返回 (payload, parser_name, error_code)。
    error_code 为空表示成功。
    """
    parser_name = "text_direct"
    t = (text or "").strip()
    if not t:
        return _failed_payload(
            source_type=SOURCE_TYPE_TEXT,
            raw_source="",
            title=title or "(空文本)",
            error_code="empty_content",
            parser_name=parser_name,
        ), parser_name, "empty_content"

    sid = _make_source_id("text", str(uuid.uuid4())[:8], "")
    meta: dict[str, Any] = {
        "title": title or sid,
        "parser_name": parser_name,
        "created_at": _now_iso(),
        "source_type": SOURCE_TYPE_TEXT,
        "chunk_index": 0,
    }
    payload = SourcePayload(
        source_type=SOURCE_TYPE_TEXT,
        source_id=sid,
        title=title or "(直接文本)",
        text=t,
        metadata=meta,
        raw_source="",
    )
    return payload, parser_name, ""


# ── 2. 文本文件来源（.txt / .md）──────────────────────────────────────────
def parse_file_source(
    file_path: str | Path,
    *,
    file_content: str | bytes | None = None,
) -> tuple[SourcePayload, str, str]:
    """
    文件 prepare（支持 .txt / .md）。

    file_content：
    - 若提供（来自前端上传的内容），直接使用，不读文件系统
    - 若不提供，从 file_path 读取

    返回 (payload, parser_name, error_code)。
    """
    parser_name = "text_file_parser"
    path = Path(file_path) if file_path else Path("")
    ext = path.suffix.lower()
    file_name = path.name or "unknown"

    if ext not in _SUPPORTED_TEXT_EXTS:
        return _failed_payload(
            source_type=SOURCE_TYPE_TEXT_FILE,
            raw_source=str(path),
            title=file_name,
            error_code="unsupported_format",
            parser_name=parser_name,
            extra_meta={"file_name": file_name, "file_ext": ext},
        ), parser_name, "unsupported_format"

    # 读取内容
    if file_content is not None:
        if isinstance(file_content, bytes):
            try:
                raw_text = file_content.decode("utf-8", errors="replace")
            except (UnicodeDecodeError, ValueError):
                raw_text = file_content.decode("latin-1", errors="replace")
        else:
            raw_text = str(file_content)
    else:
        if not path.exists():
            return _failed_payload(
                source_type=SOURCE_TYPE_TEXT_FILE,
                raw_source=str(path),
                title=file_name,
                error_code="file_not_found",
                parser_name=parser_name,
                extra_meta={"file_name": file_name, "file_ext": ext},
            ), parser_name, "file_not_found"
        try:
            raw_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning("parse_file_source read failed: %s", e)
            return _failed_payload(
                source_type=SOURCE_TYPE_TEXT_FILE,
                raw_source=str(path),
                title=file_name,
                error_code="parse_failed",
                parser_name=parser_name,
                extra_meta={"file_name": file_name, "file_ext": ext},
            ), parser_name, "parse_failed"

    text = raw_text.strip()
    if not text:
        return _failed_payload(
            source_type=SOURCE_TYPE_TEXT_FILE,
            raw_source=str(path),
            title=file_name,
            error_code="empty_content",
            parser_name=parser_name,
        ), parser_name, "empty_content"

    title = file_name
    sid = _make_source_id("file", file_name)
    meta: dict[str, Any] = {
        "title": title,
        "file_name": file_name,
        "file_ext": ext,
        "file_path": str(path),
        "parser_name": parser_name,
        "created_at": _now_iso(),
        "source_type": SOURCE_TYPE_TEXT_FILE,
        "chunk_index": 0,
    }
    payload = SourcePayload(
        source_type=SOURCE_TYPE_TEXT_FILE,
        source_id=sid,
        title=title,
        text=text,
        metadata=meta,
        raw_source=str(path),
    )
    return payload, parser_name, ""
