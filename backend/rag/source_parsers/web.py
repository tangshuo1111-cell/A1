"""Web URL source parser."""

from __future__ import annotations

from typing import Any

from ._common import (
    SOURCE_TYPE_WEB_URL,
    SourcePayload,
    _failed_payload,
    _make_source_id,
    _now_iso,
)


# ── 3. 网页 URL 来源 ──────────────────────────────────────────────────────
def parse_web_url_source(
    url: str,
    *,
    fetch_method: str = "static",
    cookie: str = "",
    cookie_ref: str = "",
    cookie_domain: str = "",
    task_id: str = "",
) -> tuple[SourcePayload, str, str]:
    """
    网页 URL prepare：web registry → WebToolResult → SourcePayload。

    默认主路径只走 fetch_web_page MCP-compatible Adapter，不再直接调用旧
    agno_web_service 抓取函数，避免 web_url 绕过 ToolResult / pending。
    返回 (payload, parser_name, error_code)。
    """
    import tools.web  # noqa: F401 - 触发 web tools 注册
    from tools.web.registry import call_tool

    tool_name = {
        "static": "fetch_web_page",
        "dynamic": "fetch_dynamic_page",
        "cookie": "fetch_with_cookie",
    }.get((fetch_method or "static").strip().lower(), "fetch_web_page")
    parser_name = tool_name
    u = (url or "").strip()

    kwargs: dict[str, Any] = {"url": u}
    if tool_name == "fetch_with_cookie":
        kwargs.update({"cookie": cookie, "cookie_ref": cookie_ref, "cookie_domain": cookie_domain})
        if task_id:
            kwargs["task_id"] = task_id
    result = call_tool(tool_name, **kwargs)
    parser_name = result.tool_name
    error_code = result.error_code or ""

    if not result.is_committable:
        return _failed_payload(
            source_type=SOURCE_TYPE_WEB_URL,
            raw_source=u,
            title=result.title or u or "(空 URL)",
            error_code=error_code or "fetch_failed",
            parser_name=parser_name,
            extra_meta={
                "url": u,
                "final_url": result.final_url or u,
                "domain": result.domain,
                "failure_reason": result.failure_reason,
                "next_action_hint": result.next_action_hint,
                "v16_web_tool_name": result.tool_name,
                "v16_web_mcp_mode": result.mcp_mode,
                "v16_web_error_code": error_code,
                "v16_web_trace": result.trace[:8],
            },
        ), parser_name, error_code or "fetch_failed"

    text = result.text.strip()
    title = result.title or result.metadata.get("title") or u
    meta: dict[str, Any] = {
        "title": title,
        "url": u,
        "final_url": result.final_url or result.metadata.get("final_url", u),
        "domain": result.domain or result.metadata.get("domain", ""),
        "parser_name": parser_name,
        "created_at": _now_iso(),
        "source_type": SOURCE_TYPE_WEB_URL,
        "chunk_index": 0,
        "extraction_method": result.extraction_method or result.metadata.get("extraction_method", ""),
        "fetch_method": result.fetch_method or result.metadata.get("fetch_method", "static"),
        "content_hash": result.metadata.get("content_hash", ""),
        "text_length": result.quality.get("text_length", len(text)),
        "quality_level": result.quality.get("quality_level", ""),
        "retrieved_at": result.metadata.get("retrieved_at", _now_iso()),
        "http_status": result.http_status,
        "requires_cookie": bool(result.requires_cookie),
        "cookie_used": bool(result.cookie_used),
        "v16_web_tool_name": result.tool_name,
        "v16_web_mcp_mode": result.mcp_mode,
        "v16_web_status": result.status,
        "v16_web_error_code": result.error_code,
        "v16_web_extract_method": result.extraction_method,
        "v16_web_quality_level": result.quality.get("quality_level", ""),
        "v16_web_text_length": result.quality.get("text_length", len(text)),
        "v16_web_valid_text_ratio": result.quality.get("valid_text_ratio", 0.0),
        "v16_web_trace": result.trace[:8],
    }
    tid = (result.task_id or task_id or "").strip()
    if tid:
        meta["v16_task_id"] = tid
    for k, v in (result.metadata or {}).items():
        if k not in meta:
            meta[k] = v
    sid = _make_source_id("web_url", result.final_url or u)
    payload = SourcePayload(
        source_type=SOURCE_TYPE_WEB_URL,
        source_id=sid,
        title=title,
        text=text,
        metadata=meta,
        raw_source=u,
    )
    return payload, parser_name, ""
