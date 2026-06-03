"""Web search source parser."""

from __future__ import annotations

from ._common import (
    SOURCE_TYPE_WEB_SEARCH,
    SourcePayload,
    _failed_payload,
    _make_source_id,
    _now_iso,
)


def parse_web_search_source(
    query: str,
    *,
    provider_override: str = "",
    session_id: str = "",
) -> tuple[SourcePayload, str, str]:
    import tools.search  # noqa: F401
    from tools.search.registry import call_tool

    result = call_tool("web_search", query=query, provider_override=provider_override, session_id=session_id)
    parser_name = result.tool_name
    if not result.is_committable:
        return _failed_payload(
            source_type=SOURCE_TYPE_WEB_SEARCH,
            raw_source=query,
            title=query or "(empty query)",
            error_code=result.error_code or "search_provider_error",
            parser_name=parser_name,
            extra_meta={"query": query, "task_id": result.task_id, "failure_reason": result.failure_reason},
        ), parser_name, result.error_code or "search_provider_error"
    meta = dict(result.metadata or {})
    meta.update({"parser_name": parser_name, "created_at": _now_iso(), "chunk_index": 0, "task_id": result.task_id})
    payload = SourcePayload(
        source_type=SOURCE_TYPE_WEB_SEARCH,
        source_id=_make_source_id("web_search", query),
        title=f"Search: {query}",
        text=result.text.strip(),
        metadata=meta,
        raw_source=query,
    )
    return payload, parser_name, ""
