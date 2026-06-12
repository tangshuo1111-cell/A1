"""
最小网页搜索 + 静态网页文本入库接线（挂在 Agno 主链上）。

- **主链摘要块**：`fetch_web_evidence_block` 在已配置 **V16** `V16_WEB_SEARCH_PROVIDER` /
  `V16_SEARCH_PROVIDER` 时走 `tools.search` 注册的 `web_search`（Tavily / generic_http 等）；
  否则回退 **DuckDuckGo HTML**（`run_web_search`）。
- 入库：复用 `storage.knowledge_store.save_document_text` → 既有 `rag.ingest`。

不新建对外路由、不造平行搜索/入库体系。
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Final
from urllib.parse import urlparse

import httpx

from services.capabilities.contracts import CapabilityAdvice, CapabilityFact
from services.capabilities.web.static_body_extract import minimal_html_to_plain_text
from storage import knowledge_store
from tools.search.web_search import format_evidence_line, run_web_search

logger = logging.getLogger("light_maqa")

# 入库 source_id 前缀，便于单测 DELETE 清理
V3_WEB_SOURCE_PREFIX: Final[str] = "v3_web_static/"

# 用户显式要外部检索时的最小触发词（大小写不敏感对 ASCII 段）
_EXPLICIT_HINTS: Final[tuple[str, ...]] = (
    "上网查",
    "搜一下",
    "查网页",
    "搜索网页",
    "查外部",
    "联网查",
    "网上查",
    "网上搜",
    "搜索一下",
    "查一下网上",
    "search the web",
    "web search",
)

_SPA_SHELL_MARKERS: Final[tuple[str, ...]] = (
    'id="root"',
    "id='root'",
    "__next_data__",
    "data-reactroot",
    "ng-app",
    "nuxt",
    "window.__initial_state__",
)

_URL_RE: Final[re.Pattern[str]] = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def _quality_level_from_text(text: str) -> str:
    plain = (text or "").strip()
    if not plain:
        return "empty"
    if len(plain) < 120:
        return "poor"
    if len(plain) < 400:
        return "usable"
    return "good"


def _looks_like_spa_shell(html: str, plain: str) -> bool:
    lower = (html or "").lower()
    return bool(any(marker.lower() in lower for marker in _SPA_SHELL_MARKERS) and len(plain.strip()) < 400)


def probe_web_capability(
    url: str,
    clock: Any | None = None,
) -> tuple[CapabilityFact, CapabilityAdvice]:
    """Probe static fetch viability; returns facts + advice only (§5.2 / W1)."""
    del clock  # reserved for budget-aware probe cutoff
    started = time.perf_counter()
    clean_url = (url or "").strip()
    dynamic_required = False
    cookie_required = False
    error_code = ""
    html = ""

    def _elapsed_ms() -> int:
        return int((time.perf_counter() - started) * 1000)

    if not clean_url:
        fact = CapabilityFact(
            lane="web",
            probe_elapsed_ms=_elapsed_ms(),
            dynamic_required=False,
            cookie_required=False,
            quality_level="empty",
            error_code="empty_url",
        )
        return fact, CapabilityAdvice(
            suggested_mode="sync_ok",
            reason="empty_url",
            next_action_hint="请提供有效网页 URL。",
        )

    try:
        html = _http_get_text(clean_url)
    except httpx.HTTPStatusError as exc:
        status = int(exc.response.status_code)
        if status in (401, 403):
            cookie_required = True
            error_code = "cookie_required"
        else:
            error_code = f"http_{status}"
            dynamic_required = True
    except (httpx.HTTPError, OSError, ValueError) as exc:
        error_code = type(exc).__name__.lower()
        dynamic_required = True

    plain = minimal_html_to_plain_text(html, url=clean_url) if html else ""
    quality_level = _quality_level_from_text(plain)

    if html and not cookie_required:
        try:
            from tools.web import errors as web_errors
            from tools.web.common import looks_like_access_wall

            wall = looks_like_access_wall(plain, html)
            if wall == web_errors.COOKIE_REQUIRED:
                cookie_required = True
                error_code = "cookie_required"
            elif wall in (web_errors.CAPTCHA_OR_ANTIBOT, web_errors.ACCESS_DENIED):
                dynamic_required = True
                error_code = str(wall)
        except Exception:  # noqa: BLE001
            pass

    if cookie_required:
        dynamic_required = False
    elif _looks_like_spa_shell(html, plain) or quality_level in {"empty", "poor"}:
        dynamic_required = True
        if not error_code:
            error_code = "dynamic_content_required"

    if cookie_required:
        advice = CapabilityAdvice(
            suggested_mode="demote_to_async",
            reason="cookie_required",
            next_action_hint="网页需要登录态，已建议转后台或 cookie 抓取。",
        )
    elif dynamic_required:
        advice = CapabilityAdvice(
            suggested_mode="demote_to_async",
            reason=error_code or "dynamic_required",
            next_action_hint="静态抓取不足，建议转动态网页后台任务。",
        )
    else:
        advice = CapabilityAdvice(
            suggested_mode="sync_ok",
            reason="static_fetch_ok",
            next_action_hint="可继续 fast 静态摘要。",
        )

    fact = CapabilityFact(
        lane="web",
        probe_elapsed_ms=_elapsed_ms(),
        dynamic_required=dynamic_required,
        cookie_required=cookie_required,
        quality_level=quality_level,  # type: ignore[arg-type]
        error_code=error_code,
        metadata={
            "url": clean_url,
            "text_length": len(plain),
            "static_fetch_ok": not dynamic_required and not cookie_required,
        },
    )
    return fact, advice


def user_requests_web_search(message: str) -> bool:
    """用户是否显式要求查网页 / 外部信息。"""
    raw = (message or "").strip()
    if not raw:
        return False
    lower = raw.lower()
    for hint in _EXPLICIT_HINTS:
        if hint.isascii():
            if hint.lower() in lower:
                return True
        elif hint in raw:
            return True
    return False


def extract_first_url(message: str) -> str:
    raw = (message or "").strip()
    if not raw:
        return ""
    m = _URL_RE.search(raw)
    return (m.group(0) if m else "").strip()


def knowledge_block_insufficient(block: str | None) -> bool:
    """本地知识检索是否不足（V3 最小口径：无正文即不足）。"""
    return not (block or "").strip()


def should_run_web_search(
    message: str,
    *,
    use_knowledge: bool,
    knowledge_block: str | None,
) -> bool:
    """
    仅在以下情况触发网页搜索：
    1) 用户显式要求查网页 / 外部信息
    2) 已开 use_knowledge 且本地检索结果为空（不足）
    """
    if user_requests_web_search(message):
        return True
    if use_knowledge and knowledge_block_insufficient(knowledge_block):  # noqa: SIM103
        return True
    return False


def fetch_web_evidence_block(query: str, *, max_results: int = 3) -> str:
    """
    拼出可塞进 Agno / Answer 提示的纯文本（网页检索摘要）。

    优先：若配置了 V16 web_search provider，则走 ``call_tool("web_search", ...)``（与 pending
    工具链同一套 Tavily 等实现）；否则回退 DuckDuckGo HTML ``run_web_search``。
    """
    q = (query or "").strip()
    if not q:
        return ""

    from config.settings import settings as _settings

    prov = (_settings.v16_web_search_provider or _settings.v16_search_provider or "").strip()
    if prov:
        try:
            import tools.search  # noqa: F401  # 注册 web_search
            from tools.search.registry import call_tool

            r = call_tool("web_search", query=q, session_id="agno_web_fetch")
            if r.status == "success":
                meta = r.metadata or {}
                raw_results = meta.get("results")
                if raw_results is None:
                    raw_results = (r.structured_data or {}).get("results")
                if isinstance(raw_results, list) and raw_results:
                    lines: list[str] = []
                    for item in raw_results[:max_results]:
                        if not isinstance(item, dict):
                            continue
                        t = (item.get("title") or "").strip()
                        u = (item.get("url") or "").strip()
                        s = (item.get("snippet") or "").strip()
                        if not u and not t:
                            continue
                        chunk = f"[Web检索] {t}\nURL: {u}\n摘要: {s}" if s else f"[Web检索] {t}\nURL: {u}"
                        lines.append(chunk[:6000])
                    if lines:
                        return "\n\n".join(lines)[:20_000]
                body = (r.text or "").strip()
                if body:
                    return body[:20_000]
        except Exception as e:  # noqa: BLE001
            logger.warning("agno_web_service V16 web_search failed: %s", e)

    try:
        recs, code = run_web_search(q, max_results=max_results)
    except Exception as e:  # noqa: BLE001
        logger.warning("agno_web_service run_web_search failed: %s", e)
        return ""
    if code != "ok" or not recs:
        return ""
    lines: list[str] = []
    for r in recs[:max_results]:
        line = format_evidence_line(r)
        if line.strip():
            lines.append(line.strip())
    return "\n\n".join(lines)


def fetch_web_fast_material(message: str, *, max_results: int = 2) -> str:
    """
    web_fast 的主材料获取：
    1) 若消息里有明确 URL，优先直抓该 URL 正文
    2) 正文不足时，再退回搜索摘要补充
    3) 无 URL 时，沿用现有搜索摘要链
    """
    raw = (message or "").strip()
    if not raw:
        return ""

    url = extract_first_url(raw)
    if not url:
        return fetch_web_evidence_block(raw, max_results=max_results)

    body_block = ""
    plain_text = ""
    try:
        html = _http_get_text(url)
        plain = minimal_html_to_plain_text(html, url=url)
        plain_text = plain.strip()
        if plain_text:
            host = (urlparse(url).netloc or url).strip()
            excerpt = plain_text[:12_000]
            body_block = f"[网页正文] {host}\nURL: {url}\n正文:\n{excerpt}"
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_web_fast_material direct fetch failed: %s", e)

    if body_block and len(plain_text) >= 1000:
        return body_block

    search_block = fetch_web_evidence_block(raw, max_results=max_results)
    if body_block and search_block:
        return f"{body_block}\n\n[搜索补充]\n{search_block}"
    if body_block:
        return body_block
    return search_block


def detect_web_fast_material_sources(material: str) -> dict[str, str]:
    text = (material or "").strip()
    has_page_body = "[网页正文]" in text
    has_search = "[搜索补充]" in text or "[Web检索]" in text
    primary = "unknown"
    if has_page_body:
        primary = "page_body"
    elif has_search:
        primary = "search"
    supplemental = "none"
    if has_page_body and has_search:
        supplemental = "search"
    return {
        "web_primary_source": primary,
        "web_supplement_source": supplemental,
    }


def _http_get_text(url: str) -> str:
    """拉取网页 HTML（单测可 monkeypatch 本函数）。"""
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        resp = client.get(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; LightMAQA-V3/1.0; +https://example.local)"
                ),
            },
        )
        resp.raise_for_status()
        return resp.text


def ingest_static_page_from_url(url: str, *, source_id: str | None = None) -> int:
    """
    抓取单 URL 静态页 → 最小清洗 → 走 knowledge_store 入库。
    source_id 默认 `v3_web_static/<规范化>`。
    """
    u = (url or "").strip()
    if not u:
        return 0
    html = _http_get_text(u)
    plain = minimal_html_to_plain_text(html, url=u)
    if not plain.strip():
        return 0
    sid = source_id or (V3_WEB_SOURCE_PREFIX + re.sub(r"[^\w.\-]+", "_", u)[:120])
    n = knowledge_store.save_document_text(plain, source_id=sid)
    logger.info("agno_web_service ingest url=%s chunks=%s", u[:80], n)
    return n
