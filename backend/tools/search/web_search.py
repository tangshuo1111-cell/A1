"""
DuckDuckGo HTML 轻量搜索（tools / search 子层）。

无官方 API Key：抓取 html.duckduckgo.com，结构变化时可能失效，返回可恢复错误记录。
输入：query；输出：ExternalEvidenceRecord 列表 + 简短 trace 码。

与 middle_agent._run_search、tools.standard_result 协作。
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from config.settings import settings
from storage import task_job_store
from tasks.orchestration.task_store import create_task_record
from tools.document.tool_result import DocumentToolResult
from tools.search.providers import dispatch_provider
from tools.search.registry import SearchToolSchema, register
from tools.standard_result import ExternalEvidenceRecord

logger = logging.getLogger("light_maqa")


def _unwrap_ddg_url(href: str) -> str:
    if "duckduckgo.com/l/?" not in href:
        return href
    try:
        q = parse_qs(urlparse(href).query).get("uddg", [""])[0]
        return unquote(q) if q else href
    except (ValueError, KeyError):
        return href


def run_web_search(
    query: str,
    *,
    max_results: int = 5,
) -> tuple[list[ExternalEvidenceRecord], str]:
    q = (query or "").strip()
    if not q:
        return [], "empty_query"
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": q, "b": ""},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; LightMAQA/1.0; +https://example.local)"
                    ),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
        resp.raise_for_status()
    except (httpx.HTTPError, OSError) as e:
        logger.warning("web_search http failed: %s", e)
        return [
            ExternalEvidenceRecord(
                source="web_search",
                title="HTTP",
                status="error",
                error=str(e),
            )
        ], "http_error"

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(resp.text, "html.parser")
    except (ImportError, ValueError, TypeError) as e:
        return [
            ExternalEvidenceRecord(
                source="web_search",
                title="parse",
                status="error",
                error=str(e),
            )
        ], "parse_error"

    results: list[ExternalEvidenceRecord] = []
    for a in soup.select("a.result__a")[:max_results]:
        href = a.get("href") or ""
        title = a.get_text(strip=True) or "(无标题)"
        url = _unwrap_ddg_url(href)
        sn = a.find_parent("div", class_="result__body")
        snippet = ""
        if sn:
            snb = sn.select_one(".result__snippet")
            if snb:
                snippet = snb.get_text(strip=True)[:500]
        results.append(
            ExternalEvidenceRecord(
                source="web_search",
                title=title,
                url=url,
                snippet=snippet,
                content=snippet,
                status="ok",
                metadata={"engine": "ddg_html"},
            )
        )

    if not results:
        return [
            ExternalEvidenceRecord(
                source="web_search",
                title="no_results",
                status="error",
                error="no_parseable_results",
            )
        ], "no_results"

    return results, "ok"


def format_evidence_line(rec: ExternalEvidenceRecord) -> str:
    if rec.status != "ok":
        return f"[Web检索·失败] {rec.title}: {rec.error or 'unknown'}"
    u = rec.url or ""
    t = rec.title or ""
    s = rec.snippet or rec.content or ""
    return f"[Web检索] {t}\nURL: {u}\n摘要: {s}"[:6000]


def web_search_tool(**kwargs: Any) -> dict[str, Any]:
    """注册用：返回结构化 dict，便于 tools.call。"""
    q = str(kwargs.get("query") or "")
    recs, code = run_web_search(q)
    return {
        "ok": code == "ok",
        "trace": code,
        "results": [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
                "status": r.status,
                "error": r.error,
            }
            for r in recs
        ],
    }


def _web_search(query: str, *, provider_override: str = "", session_id: str = "") -> DocumentToolResult:
    task_id = create_task_record(task_type="web_search", source_type="web_search", session_id=session_id, user_query=query)
    task_job_store.mark_task_running(task_id, stage="search_provider")
    q = (query or "").strip()
    if not q:
        task_job_store.mark_task_failed(task_id, error_code="search_empty_result", failure_reason="查询为空")
        return DocumentToolResult(
            tool_name="web_search",
            source_type="web_search",
            task_id=task_id,
            status="failed",
            error_code="search_empty_result",
            failure_reason="查询为空",
            metadata={"source_type": "web_search", "query": q, "provider": "", "provider_type": "", "results": []},
        )
    if len(q) > settings.v16_max_search_query_chars:
        q = q[: settings.v16_max_search_query_chars]
    po = (provider_override or "").strip()
    wp = (settings.v16_web_search_provider or "").strip()
    sp = (settings.v16_search_provider or "").strip()
    provider = (po or wp or sp).lower()
    if not provider:
        task_job_store.mark_task_failed(task_id, error_code="web_search_not_configured", failure_reason="未配置搜索 provider")
        return DocumentToolResult(
            tool_name="web_search",
            source_type="web_search",
            task_id=task_id,
            status="failed",
            error_code="web_search_not_configured",
            failure_reason="未配置搜索 provider",
            next_action_hint="设置 V16_WEB_SEARCH_PROVIDER 或 V16_SEARCH_PROVIDER（generic_http 时尚需 V16_WEB_SEARCH_ENDPOINT）",
            metadata={
                "source_type": "web_search",
                "query": q,
                "provider": "",
                "provider_type": "",
                "production_ready": False,
                "results": [],
            },
        )
    t0 = time.perf_counter()
    out = dispatch_provider(
        provider_key=provider,
        query=q,
        max_results=settings.v16_max_search_results,
        settings=settings,
        run_web_search=run_web_search,
    )
    duration_ms = (time.perf_counter() - t0) * 1000.0
    if not out.ok:
        task_job_store.mark_task_failed(task_id, error_code=out.error_code, failure_reason=out.failure_reason)
        return DocumentToolResult(
            tool_name="web_search",
            source_type="web_search",
            task_id=task_id,
            status="failed",
            error_code=out.error_code,
            failure_reason=out.failure_reason,
            next_action_hint=out.next_action_hint,
            duration_ms=max(duration_ms, out.duration_ms),
            metadata={
                "source_type": "web_search",
                "query": q,
                "provider": out.provider,
                "provider_type": out.provider_type,
                "production_ready": out.production_ready,
                "results": [],
                "title": "",
                "url": "",
                "snippet": "",
                "result_count": 0,
            },
            quality={"quality_level": "failed", "text_length": 0},
            trace=[f"v16:search failed provider={provider} code={out.error_code}"],
        )
    results = out.results
    text = "\n".join(f"{item['title']}\n{item['url']}\n{item['snippet']}" for item in results).strip()
    metadata = {
        "source_type": "web_search",
        "query": q,
        "provider": out.provider,
        "provider_type": out.provider_type,
        "production_ready": out.production_ready,
        "result_count": len(results),
        "title": results[0]["title"] if results else "",
        "url": results[0]["url"] if results else "",
        "snippet": results[0]["snippet"] if results else "",
        "results": results,
        "search_time": "now",
        "quality_level": "usable" if results else "failed",
    }
    task_job_store.mark_task_succeeded(task_id, result_summary={"status": "success", "result_count": len(results)})
    return DocumentToolResult(
        tool_name="web_search",
        source_type="web_search",
        task_id=task_id,
        status="success",
        text=text,
        structured_data={"results": results},
        metadata=metadata,
        quality={"quality_level": metadata["quality_level"], "text_length": len(text)},
        duration_ms=max(duration_ms, out.duration_ms),
        trace=[f"v16:search success provider={provider} provider_type={out.provider_type} count={len(results)}"],
    )


register(
    SearchToolSchema(
        tool_name="web_search",
        description="Web search boundary tool with configurable provider.",
        input_schema={"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"status": {"type": "string"}, "results": {"type": "array"}}},
        call_fn=_web_search,
        enabled=True,
    )
)
