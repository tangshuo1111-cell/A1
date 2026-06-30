"""
web_search provider 调度（fixture + generic_http + 内置商业 API + 遗留 DDG HTML）。

fixture：仅测试 / 本地假数据，production_ready=false。
generic_http：可配置 endpoint + api key 的通用 HTTP 搜索 API 客户端（成功形态由 JSON 解析约定）。
tavily / brave / serper：内置常见「免费额度」商业搜索 API，仅需 V16_WEB_SEARCH_API_KEY（无需自建 endpoint）。
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("light_maqa")

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
SERPER_SEARCH_URL = "https://google.serper.dev/search"

SearchLegacyFn = Callable[..., tuple[list[Any], str]]


def _strip_html_basic(html: str) -> str:
    if not html:
        return ""
    s = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    s = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class WebSearchProviderOutcome:
    ok: bool
    error_code: str = ""
    failure_reason: str = ""
    next_action_hint: str = ""
    results: list[dict[str, Any]] = field(default_factory=list)
    provider: str = ""
    provider_type: str = ""
    production_ready: bool = False
    duration_ms: float = 0.0


def _commercial_api_key_missing_outcome(*, provider_key: str) -> WebSearchProviderOutcome:
    return WebSearchProviderOutcome(
        ok=False,
        error_code="web_search_not_configured",
        failure_reason=f"{provider_key} 需要配置 V16_WEB_SEARCH_API_KEY",
        next_action_hint=f"设置 V16_WEB_SEARCH_PROVIDER={provider_key} 与官网申请的 API Key（见 .env.example）",
        provider=provider_key,
        provider_type=provider_key,
        production_ready=True,
    )


def _normalize_hit(raw: dict[str, Any], *, default_source: str) -> dict[str, Any] | None:
    url = str(raw.get("url") or "").strip()
    if not url:
        return None
    title = str(raw.get("title") or "").strip() or "(no title)"
    snippet = str(raw.get("snippet") or raw.get("description") or "").strip()
    source = str(raw.get("source") or default_source).strip() or default_source
    return {"title": title, "url": url, "snippet": snippet, "source": source}


def run_fixture_provider(query: str, *, max_results: int) -> WebSearchProviderOutcome:
    q = (query or "").strip()
    results = [
        {
            "title": "Fixture Search Result",
            "url": "https://fixture.local/search/1",
            "snippet": f"Fixture result for {q}",
            "source": "fixture",
        }
    ][:max_results]
    return WebSearchProviderOutcome(
        ok=True,
        results=results,
        provider="fixture",
        provider_type="fixture",
        production_ready=False,
    )


def _parse_generic_json_payload(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        raw_items = data.get("results") or data.get("items") or data.get("hits")
        if raw_items is None:
            return []
        if not isinstance(raw_items, list):
            return []
        items = raw_items
    else:
        return []
    out: list[dict[str, Any]] = []
    for it in items:
        if isinstance(it, dict):
            out.append(it)
    return out


def run_generic_http_provider(
    query: str,
    *,
    max_results: int,
    endpoint: str,
    api_key: str,
    timeout_sec: float,
) -> WebSearchProviderOutcome:
    ep = (endpoint or "").strip()
    if not ep:
        return WebSearchProviderOutcome(
            ok=False,
            error_code="web_search_not_configured",
            failure_reason="generic_http 未配置 V16_WEB_SEARCH_ENDPOINT",
            next_action_hint="设置 V16_WEB_SEARCH_ENDPOINT 与 V16_WEB_SEARCH_PROVIDER=generic_http",
            provider="generic_http",
            provider_type="generic_http",
            production_ready=True,
        )
    q = (query or "").strip()
    t0 = time.perf_counter()
    headers: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
    ak = (api_key or "").strip()
    if ak:
        headers["X-API-Key"] = ak
    body = {"query": q, "max_results": max_results}
    try:
        with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
            resp = client.post(ep, json=body, headers=headers)
        resp.raise_for_status()
        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            logger.warning("web_search generic_http json decode: %s", e)
            return WebSearchProviderOutcome(
                ok=False,
                error_code="search_provider_error",
                failure_reason="搜索 API 返回非 JSON",
                next_action_hint="检查 endpoint 返回是否为 JSON（含 results 数组）",
                provider="generic_http",
                provider_type="generic_http",
                production_ready=True,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
    except httpx.HTTPStatusError as e:
        logger.warning("web_search generic_http http status: %s", e)
        return WebSearchProviderOutcome(
            ok=False,
            error_code="search_provider_error",
            failure_reason=f"搜索 API HTTP 错误: {e.response.status_code}",
            next_action_hint="检查 endpoint、鉴权与 API 可用性",
            provider="generic_http",
            provider_type="generic_http",
            production_ready=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:  # noqa: BLE001
        logger.warning("web_search generic_http request failed: %s", e)
        return WebSearchProviderOutcome(
            ok=False,
            error_code="search_provider_error",
            failure_reason=f"搜索请求失败: {e}",
            next_action_hint="检查网络、超时（V16_WEB_SEARCH_TIMEOUT_SEC）与 endpoint",
            provider="generic_http",
            provider_type="generic_http",
            production_ready=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    raw_list = _parse_generic_json_payload(data)
    normalized: list[dict[str, Any]] = []
    for raw in raw_list[:max_results]:
        hit = _normalize_hit(raw, default_source="generic_http")
        if hit:
            normalized.append(hit)
    elapsed = (time.perf_counter() - t0) * 1000.0
    if not normalized:
        return WebSearchProviderOutcome(
            ok=False,
            error_code="search_empty_result",
            failure_reason="搜索 API 返回空结果",
            next_action_hint="尝试更换 query 或检查远端索引",
            provider="generic_http",
            provider_type="generic_http",
            production_ready=True,
            duration_ms=elapsed,
        )
    return WebSearchProviderOutcome(
        ok=True,
        results=normalized,
        provider="generic_http",
        provider_type="generic_http",
        production_ready=True,
        duration_ms=elapsed,
    )


def _cap_search_count(n: int, *, upper: int = 20) -> int:
    try:
        v = int(n)
    except (TypeError, ValueError):
        v = 5
    return max(1, min(v, upper))


def run_tavily_provider(
    query: str,
    *,
    max_results: int,
    api_key: str,
    timeout_sec: float,
) -> WebSearchProviderOutcome:
    """Tavily Search API：Bearer 鉴权，结果字段含 content。"""
    ak = (api_key or "").strip()
    if not ak:
        return _commercial_api_key_missing_outcome(provider_key="tavily")
    q = (query or "").strip()
    count = _cap_search_count(max_results)
    t0 = time.perf_counter()
    auth = ak if ak.lower().startswith("bearer ") else f"Bearer {ak}"
    headers = {"Authorization": auth, "Content-Type": "application/json", "Accept": "application/json"}
    body = {"query": q, "max_results": count}
    try:
        with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
            resp = client.post(TAVILY_SEARCH_URL, json=body, headers=headers)
        resp.raise_for_status()
        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            logger.warning("web_search tavily json decode: %s", e)
            return WebSearchProviderOutcome(
                ok=False,
                error_code="search_provider_error",
                failure_reason="Tavily 返回非 JSON",
                next_action_hint="检查 API Key 与网络",
                provider="tavily",
                provider_type="tavily",
                production_ready=True,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
    except httpx.HTTPStatusError as e:
        logger.warning("web_search tavily http status: %s", e)
        return WebSearchProviderOutcome(
            ok=False,
            error_code="search_provider_error",
            failure_reason=f"Tavily HTTP 错误: {e.response.status_code}",
            next_action_hint="检查 V16_WEB_SEARCH_API_KEY 是否有效、额度是否耗尽",
            provider="tavily",
            provider_type="tavily",
            production_ready=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:  # noqa: BLE001
        logger.warning("web_search tavily request failed: %s", e)
        return WebSearchProviderOutcome(
            ok=False,
            error_code="search_provider_error",
            failure_reason=f"Tavily 请求失败: {e}",
            next_action_hint="检查网络与 V16_WEB_SEARCH_TIMEOUT_SEC",
            provider="tavily",
            provider_type="tavily",
            production_ready=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    items = data.get("results") if isinstance(data, dict) else None
    if not isinstance(items, list):
        items = []
    normalized: list[dict[str, Any]] = []
    for raw in items[:count]:
        if not isinstance(raw, dict):
            continue
        merged = dict(raw)
        if merged.get("content") and not merged.get("snippet"):
            merged["snippet"] = str(merged.get("content") or "")
        hit = _normalize_hit(merged, default_source="tavily")
        if hit:
            normalized.append(hit)
    elapsed = (time.perf_counter() - t0) * 1000.0
    if not normalized:
        return WebSearchProviderOutcome(
            ok=False,
            error_code="search_empty_result",
            failure_reason="Tavily 返回空结果",
            next_action_hint="尝试更换关键词",
            provider="tavily",
            provider_type="tavily",
            production_ready=True,
            duration_ms=elapsed,
        )
    return WebSearchProviderOutcome(
        ok=True,
        results=normalized,
        provider="tavily",
        provider_type="tavily",
        production_ready=True,
        duration_ms=elapsed,
    )


def run_brave_provider(
    query: str,
    *,
    max_results: int,
    api_key: str,
    timeout_sec: float,
) -> WebSearchProviderOutcome:
    """Brave Search API：GET + X-Subscription-Token，结果在 web.results[].description（HTML）。"""
    ak = (api_key or "").strip()
    if not ak:
        return _commercial_api_key_missing_outcome(provider_key="brave")
    q = (query or "").strip()
    count = _cap_search_count(max_results)
    t0 = time.perf_counter()
    headers = {"Accept": "application/json", "X-Subscription-Token": ak}
    try:
        with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
            resp = client.get(
                BRAVE_WEB_SEARCH_URL,
                headers=headers,
                params={"q": q, "count": count},
            )
        resp.raise_for_status()
        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            logger.warning("web_search brave json decode: %s", e)
            return WebSearchProviderOutcome(
                ok=False,
                error_code="search_provider_error",
                failure_reason="Brave 返回非 JSON",
                next_action_hint="检查 API Key 与网络",
                provider="brave",
                provider_type="brave",
                production_ready=True,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
    except httpx.HTTPStatusError as e:
        logger.warning("web_search brave http status: %s", e)
        return WebSearchProviderOutcome(
            ok=False,
            error_code="search_provider_error",
            failure_reason=f"Brave HTTP 错误: {e.response.status_code}",
            next_action_hint="检查 V16_WEB_SEARCH_API_KEY（Brave Subscription Token）是否有效",
            provider="brave",
            provider_type="brave",
            production_ready=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:  # noqa: BLE001
        logger.warning("web_search brave request failed: %s", e)
        return WebSearchProviderOutcome(
            ok=False,
            error_code="search_provider_error",
            failure_reason=f"Brave 请求失败: {e}",
            next_action_hint="检查网络与超时设置",
            provider="brave",
            provider_type="brave",
            production_ready=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    web = data.get("web") if isinstance(data, dict) else None
    raw_list = (web or {}).get("results") if isinstance(web, dict) else None
    if not isinstance(raw_list, list):
        raw_list = []
    normalized = []
    for raw in raw_list[:count]:
        if not isinstance(raw, dict):
            continue
        desc = _strip_html_basic(str(raw.get("description") or ""))
        hit = _normalize_hit(
            {"title": raw.get("title"), "url": raw.get("url"), "snippet": desc or str(raw.get("title") or "")},
            default_source="brave",
        )
        if hit:
            normalized.append(hit)
    elapsed = (time.perf_counter() - t0) * 1000.0
    if not normalized:
        return WebSearchProviderOutcome(
            ok=False,
            error_code="search_empty_result",
            failure_reason="Brave 返回空结果",
            next_action_hint="尝试更换关键词",
            provider="brave",
            provider_type="brave",
            production_ready=True,
            duration_ms=elapsed,
        )
    return WebSearchProviderOutcome(
        ok=True,
        results=normalized,
        provider="brave",
        provider_type="brave",
        production_ready=True,
        duration_ms=elapsed,
    )


def run_serper_provider(
    query: str,
    *,
    max_results: int,
    api_key: str,
    timeout_sec: float,
) -> WebSearchProviderOutcome:
    """Serper.dev：POST JSON q/num，organic[] 中 link 为 URL。"""
    ak = (api_key or "").strip()
    if not ak:
        return _commercial_api_key_missing_outcome(provider_key="serper")
    q = (query or "").strip()
    count = _cap_search_count(max_results, upper=50)
    t0 = time.perf_counter()
    headers = {"X-API-KEY": ak, "Content-Type": "application/json", "Accept": "application/json"}
    body = {"q": q, "num": count}
    try:
        with httpx.Client(timeout=timeout_sec, follow_redirects=True) as client:
            resp = client.post(SERPER_SEARCH_URL, json=body, headers=headers)
        resp.raise_for_status()
        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            logger.warning("web_search serper json decode: %s", e)
            return WebSearchProviderOutcome(
                ok=False,
                error_code="search_provider_error",
                failure_reason="Serper 返回非 JSON",
                next_action_hint="检查 API Key 与网络",
                provider="serper",
                provider_type="serper",
                production_ready=True,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )
    except httpx.HTTPStatusError as e:
        logger.warning("web_search serper http status: %s", e)
        return WebSearchProviderOutcome(
            ok=False,
            error_code="search_provider_error",
            failure_reason=f"Serper HTTP 错误: {e.response.status_code}",
            next_action_hint="检查 V16_WEB_SEARCH_API_KEY（Serper X-API-KEY）",
            provider="serper",
            provider_type="serper",
            production_ready=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:  # noqa: BLE001
        logger.warning("web_search serper request failed: %s", e)
        return WebSearchProviderOutcome(
            ok=False,
            error_code="search_provider_error",
            failure_reason=f"Serper 请求失败: {e}",
            next_action_hint="检查网络与超时设置",
            provider="serper",
            provider_type="serper",
            production_ready=True,
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    organic = data.get("organic") if isinstance(data, dict) else None
    if not isinstance(organic, list):
        organic = []
    normalized = []
    for raw in organic[:count]:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("link") or raw.get("url") or "").strip()
        hit = _normalize_hit(
            {
                "title": raw.get("title"),
                "url": url,
                "snippet": raw.get("snippet"),
            },
            default_source="serper",
        )
        if hit:
            normalized.append(hit)
    elapsed = (time.perf_counter() - t0) * 1000.0
    if not normalized:
        return WebSearchProviderOutcome(
            ok=False,
            error_code="search_empty_result",
            failure_reason="Serper 返回空结果",
            next_action_hint="尝试更换关键词",
            provider="serper",
            provider_type="serper",
            production_ready=True,
            duration_ms=elapsed,
        )
    return WebSearchProviderOutcome(
        ok=True,
        results=normalized,
        provider="serper",
        provider_type="serper",
        production_ready=True,
        duration_ms=elapsed,
    )


def run_legacy_ddg_provider(
    query: str,
    *,
    max_results: int,
    run_web_search: SearchLegacyFn,
    provider_label: str,
) -> WebSearchProviderOutcome:
    """遗留：内部 DDG HTML 抓取，非商业搜索 API，production_ready=false。"""
    t0 = time.perf_counter()
    recs, code = run_web_search(query, max_results=max_results)
    elapsed = (time.perf_counter() - t0) * 1000.0
    if code != "ok":
        err = "search_provider_error" if code != "no_results" else "search_empty_result"
        reason = "搜索 provider 失败" if err == "search_provider_error" else "没有搜索结果"
        return WebSearchProviderOutcome(
            ok=False,
            error_code=err,
            failure_reason=reason,
            next_action_hint="检查网络或更换关键词（DDG HTML 抓取不稳定）",
            provider=provider_label,
            provider_type="ddg_html",
            production_ready=False,
            duration_ms=elapsed,
        )
    results = []
    for r in recs:
        if getattr(r, "status", "") != "ok":
            continue
        url = (getattr(r, "url", None) or "").strip()
        if not url:
            continue
        results.append(
            {
                "title": getattr(r, "title", "") or "(no title)",
                "url": url,
                "snippet": (getattr(r, "snippet", None) or getattr(r, "content", None) or "") or "",
                "source": getattr(r, "source", None) or "web_search",
            }
        )
    if not results:
        return WebSearchProviderOutcome(
            ok=False,
            error_code="search_empty_result",
            failure_reason="没有可解析的搜索结果",
            next_action_hint="更换关键词或稍后重试",
            provider=provider_label,
            provider_type="ddg_html",
            production_ready=False,
            duration_ms=elapsed,
        )
    return WebSearchProviderOutcome(
        ok=True,
        results=results,
        provider=provider_label,
        provider_type="ddg_html",
        production_ready=False,
        duration_ms=elapsed,
    )


def dispatch_provider(
    *,
    provider_key: str,
    query: str,
    max_results: int,
    settings: Any,
    run_web_search: SearchLegacyFn,
) -> WebSearchProviderOutcome:
    """
    调度搜索 provider。provider_key 已非空、且 query 已校验非空。
    """
    key = (provider_key or "").strip().lower()
    if key == "fixture":
        return run_fixture_provider(query, max_results=max_results)

    if key in ("tavily", "brave", "serper"):
        ak = (getattr(settings, "v16_web_search_api_key", "") or "").strip()
        if not ak:
            return _commercial_api_key_missing_outcome(provider_key=key)
        timeout = float(getattr(settings, "v16_web_search_timeout_sec", 15.0) or 15.0)
        if key == "tavily":
            return run_tavily_provider(query, max_results=max_results, api_key=ak, timeout_sec=timeout)
        if key == "brave":
            return run_brave_provider(query, max_results=max_results, api_key=ak, timeout_sec=timeout)
        return run_serper_provider(query, max_results=max_results, api_key=ak, timeout_sec=timeout)

    if key == "generic_http":
        ep = getattr(settings, "v16_web_search_endpoint", "") or ""
        if not str(ep).strip():
            return WebSearchProviderOutcome(
                ok=False,
                error_code="web_search_not_configured",
                failure_reason="generic_http 需要配置 V16_WEB_SEARCH_ENDPOINT",
                next_action_hint="设置环境变量 V16_WEB_SEARCH_ENDPOINT（及可选 V16_WEB_SEARCH_API_KEY）",
                provider="generic_http",
                provider_type="generic_http",
                production_ready=True,
            )
        ak = getattr(settings, "v16_web_search_api_key", "") or ""
        timeout = float(getattr(settings, "v16_web_search_timeout_sec", 15.0) or 15.0)
        return run_generic_http_provider(
            query,
            max_results=max_results,
            endpoint=str(ep),
            api_key=str(ak),
            timeout_sec=timeout,
        )

    return run_legacy_ddg_provider(
        query,
        max_results=max_results,
        run_web_search=run_web_search,
        provider_label=key,
    )
