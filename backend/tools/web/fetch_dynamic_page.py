"""V16 R2 dynamic web page fetch tool; R4-D Playwright provider 抽层."""

from __future__ import annotations

import time
import urllib.parse

from tools.web import dynamic_providers, errors
from tools.web.common import (
    content_hash,
    extract_title,
    extract_with_bs4,
    now_iso,
    truncate_text,
    validate_http_url,
)
from tools.web.limits import MAX_DYNAMIC_TIMEOUT_SEC
from tools.web.quality import assess_web_text
from tools.web.registry import WebToolSchema, register
from tools.web.tool_result import WebToolResult


def _failed(url: str, domain: str, code: str, reason: str, hint: str, trace: list[str], duration_ms: float = 0.0) -> WebToolResult:
    return WebToolResult(
        tool_name="fetch_dynamic_page",
        status="failed",
        url=url,
        final_url=url,
        domain=domain,
        fetch_method="dynamic",
        error_code=code,
        failure_reason=reason,
        next_action_hint=hint,
        quality=assess_web_text(""),
        trace=trace,
        duration_ms=duration_ms,
    )


def _fetch_dynamic_page(
    url: str,
    *,
    timeout_sec: int | None = None,
    wait_until: str = "networkidle",
) -> WebToolResult:
    t0 = time.perf_counter()
    trace = [f"v16_web:fetch_dynamic_page:start url={url}"]
    clean_url, domain, err = validate_http_url(url)
    if err:
        return _failed(clean_url or url, domain, err, "URL 无效或 scheme 不受支持", "请提供 http/https URL。", trace)
    if timeout_sec is not None and int(timeout_sec) <= 0:
        return _failed(
            clean_url,
            domain,
            errors.DYNAMIC_PAGE_TIMEOUT,
            "动态网页渲染超时",
            "请设置大于 0 的 timeout。",
            trace + ["v16_web:dynamic:timeout timeout_ms=0"],
        )

    timeout_ms = int(timeout_sec or MAX_DYNAMIC_TIMEOUT_SEC) * 1000
    outcome = dynamic_providers.run_playwright_dynamic_page(
        clean_url,
        timeout_ms=timeout_ms,
        wait_until=wait_until,
        trace=trace,
    )
    if not outcome.ok:
        return _failed(
            clean_url,
            domain,
            outcome.error_code,
            outcome.failure_reason,
            outcome.next_action_hint or "确认浏览器依赖、URL 可访问且页面不需要验证码。",
            trace + [f"v16_web:dynamic:fail code={outcome.error_code}"],
            duration_ms=outcome.duration_ms,
        )

    html = outcome.html
    final_url = outcome.final_url or clean_url

    text = ""
    try:
        text = truncate_text(extract_with_bs4(html))
    except (OSError, ValueError, RuntimeError) as e:
        return _failed(
            clean_url,
            domain,
            errors.DYNAMIC_PAGE_RENDER_FAILED,
            f"正文抽取失败: {type(e).__name__}",
            "页面 HTML 可能异常或解析失败。",
            trace + [f"v16_web:dynamic:extract_fail {type(e).__name__}"],
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        )

    wall_code, wall_reason, wall_hint = dynamic_providers.classify_dynamic_wall(text, html)
    if wall_code:
        return _failed(
            clean_url,
            domain,
            wall_code,
            wall_reason,
            wall_hint,
            trace + [f"v16_web:dynamic:access_wall error={wall_code}"],
            duration_ms=outcome.duration_ms,
        )

    if not text.strip():
        return _failed(
            clean_url,
            domain,
            errors.DYNAMIC_PAGE_EMPTY,
            "动态渲染后正文为空",
            "确认页面内容由 JS 渲染，或调整 wait_until/timeout。",
            trace + ["v16_web:dynamic:empty_chars=0"],
            duration_ms=outcome.duration_ms,
        )

    quality = assess_web_text(text)
    if quality.get("quality_level") in ("failed", "low"):
        return _failed(
            clean_url,
            domain,
            errors.LOW_CONTENT_QUALITY,
            "动态网页正文质量过低",
            "调整渲染等待策略或确认页面可读内容。",
            trace + [f"v16_web:dynamic:quality_failed level={quality.get('quality_level')}"],
            duration_ms=outcome.duration_ms,
        )

    _final_parsed = urllib.parse.urlparse(final_url)
    final_domain = (_final_parsed.hostname or _final_parsed.netloc).lower() or domain
    title = extract_title(html) or final_url
    total_ms = outcome.duration_ms or (time.perf_counter() - t0) * 1000.0
    metadata = {
        "url": clean_url,
        "final_url": final_url,
        "domain": final_domain,
        "title": title,
        "source_type": "web_url",
        "extraction_method": "playwright_bs4",
        "fetch_method": "dynamic",
        "parser_name": "fetch_dynamic_page",
        "content_hash": content_hash(text),
        "text_length": len(text),
        "quality_level": quality.get("quality_level", ""),
        "retrieved_at": now_iso(),
        "requires_cookie": False,
        "cookie_used": False,
        "provider": outcome.provider,
        "provider_type": outcome.provider_type,
        "production_ready": outcome.production_ready,
        "production_capable": outcome.production_capable,
        "wait_until": wait_until,
        "http_status": outcome.http_status,
        "mcp_mode": "mcp_compatible_adapter",
    }
    metadata.update({k: v for k, v in (outcome.metadata_extra or {}).items() if k not in metadata})
    return WebToolResult(
        tool_name="fetch_dynamic_page",
        status="success",
        url=clean_url,
        final_url=final_url,
        domain=final_domain,
        title=title,
        text=text,
        metadata=metadata,
        quality=quality,
        warnings=list(quality.get("warnings", []) or []),
        extraction_method="playwright_bs4",
        fetch_method="dynamic",
        trace=trace + [f"v16_web:dynamic:ok chars={len(text)}"],
        duration_ms=total_ms,
    )


register(WebToolSchema(
    tool_name="fetch_dynamic_page",
    description="Render and extract a dynamic web page with Playwright.",
    input_schema={
        "type": "object",
        "required": ["url"],
        "properties": {
            "url": {"type": "string"},
            "timeout_sec": {"type": "integer", "default": MAX_DYNAMIC_TIMEOUT_SEC},
            "wait_until": {"type": "string", "default": "networkidle"},
        },
    },
    output_schema={"type": "object", "required": ["tool_name", "status", "text", "metadata", "quality", "error_code", "trace"]},
    call_fn=_fetch_dynamic_page,
))
