"""Video source parsers (local and web)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._common import (
    SOURCE_TYPE_LOCAL_VIDEO,
    SOURCE_TYPE_WEB_VIDEO,
    SourcePayload,
    _failed_payload,
    _make_source_id,
    _now_iso,
)


# ── V13 R2：视频来源 parser ─────────────────────────────────────────────────
def parse_video_source(
    *,
    source_type: str,       # SOURCE_TYPE_LOCAL_VIDEO 或 SOURCE_TYPE_WEB_VIDEO
    raw_source: str,        # 文件路径（local）或 URL（web）
    video_text: str,        # 已提取的视频文本（字幕/ASR，来自 MCP 或 url_fetch）
    title: str = "",
    duration_sec: float = 0,
    text_source: str = "",  # "subtitle" / "asr" / ""
    subtitle_lang: str = "",
    asr_provider: str = "",
) -> tuple[SourcePayload, str, str]:
    """视频来源 prepare：接收视频文本化结果，转成统一 SourcePayload。

    设计原则：
    - 不负责视频文本化（文本化由 MCP/url_fetch 完成）；只做"已有文本 → SourcePayload"
    - local_video / web_video 都走此 parser，source_type 参数区分
    - 失败（text 为空）时返回带 error_code 的失败 payload

    返回 (payload, parser_name, error_code)。
    """
    parser_name = "video_text_parser"

    if source_type not in (SOURCE_TYPE_LOCAL_VIDEO, SOURCE_TYPE_WEB_VIDEO):
        return _failed_payload(
            source_type=source_type,
            raw_source=raw_source,
            title=title or raw_source,
            error_code="unsupported_video_type",
            parser_name=parser_name,
        ), parser_name, "unsupported_video_type"

    text = (video_text or "").strip()
    if not text:
        return _failed_payload(
            source_type=source_type,
            raw_source=raw_source,
            title=title or raw_source,
            error_code="empty_content",
            parser_name=parser_name,
            extra_meta={"raw_source": raw_source},
        ), parser_name, "empty_content"

    _title = (title or "").strip() or raw_source

    # metadata 统一字段
    meta: dict[str, Any] = {
        "title": _title,
        "source_type": source_type,
        "parser_name": parser_name,
        "created_at": _now_iso(),
        "chunk_index": 0,
        # 视频专有字段
        "duration_sec": duration_sec,
        "text_source": text_source,   # "subtitle" / "asr"
        "subtitle_lang": subtitle_lang,
        "asr_provider": asr_provider,
    }
    if source_type == SOURCE_TYPE_WEB_VIDEO:
        meta["url"] = raw_source
    else:
        meta["file_path"] = raw_source

    sid = _make_source_id(source_type, raw_source)
    payload = SourcePayload(
        source_type=source_type,
        source_id=sid,
        title=_title,
        text=text,
        metadata=meta,
        raw_source=raw_source,
    )
    return payload, parser_name, ""


def parse_local_video_source(
    file_path: str,
    *,
    session_id: str = "",
) -> tuple[SourcePayload, str, str]:
    import tools.video  # noqa: F401
    from tools.video.registry import call_tool

    result = call_tool("extract_local_video_subtitle", file_path=file_path, session_id=session_id)
    parser_name = result.tool_name
    if not result.is_committable:
        return _failed_payload(
            source_type=SOURCE_TYPE_LOCAL_VIDEO,
            raw_source=file_path,
            title=result.title or file_path,
            error_code=result.error_code or "subtitle_not_found",
            parser_name=parser_name,
            extra_meta={
                "file_path": file_path,
                "failure_reason": result.failure_reason,
                "task_id": result.task_id,
                "video_tool_name": result.tool_name,
                "video_status": result.status,
            },
        ), parser_name, result.error_code or "subtitle_not_found"

    meta = dict(result.metadata or {})
    meta.update(
        {
            "parser_name": parser_name,
            "created_at": _now_iso(),
            "chunk_index": 0,
            "video_tool_name": result.tool_name,
            "video_error_code": result.error_code,
            "video_status": result.status,
            "task_id": result.task_id,
        }
    )
    payload = SourcePayload(
        source_type=SOURCE_TYPE_LOCAL_VIDEO,
        source_id=_make_source_id("local_video", file_path),
        title=result.title or Path(file_path).name,
        text=result.text.strip(),
        metadata=meta,
        raw_source=file_path,
    )
    return payload, parser_name, ""


def parse_web_video_source(
    url: str,
    *,
    session_id: str = "",
) -> tuple[SourcePayload, str, str]:
    import tools.video  # noqa: F401
    from tools.video.registry import call_tool

    result = call_tool("extract_web_video_subtitle", url=url, session_id=session_id)
    parser_name = result.tool_name
    if not result.is_committable:
        return _failed_payload(
            source_type=SOURCE_TYPE_WEB_VIDEO,
            raw_source=url,
            title=result.title or url,
            error_code=result.error_code or "subtitle_not_found",
            parser_name=parser_name,
            extra_meta={
                "url": url,
                "failure_reason": result.failure_reason,
                "task_id": result.task_id,
                "video_tool_name": result.tool_name,
                "video_status": result.status,
            },
        ), parser_name, result.error_code or "subtitle_not_found"

    meta = dict(result.metadata or {})
    meta.update(
        {
            "parser_name": parser_name,
            "created_at": _now_iso(),
            "chunk_index": 0,
            "video_tool_name": result.tool_name,
            "video_error_code": result.error_code,
            "video_status": result.status,
            "task_id": result.task_id,
        }
    )
    payload = SourcePayload(
        source_type=SOURCE_TYPE_WEB_VIDEO,
        source_id=_make_source_id("web_video", url),
        title=result.title or url,
        text=result.text.strip(),
        metadata=meta,
        raw_source=url,
    )
    return payload, parser_name, ""
