"""Static web page fetch tool."""

from __future__ import annotations

import urllib.error
import urllib.parse

from tools.web import errors
from tools.web.common import (
    content_hash,
    extract_title,
    extract_with_bs4,
    extract_with_trafilatura,
    fetch_http_text,
    looks_like_access_wall,
    now_iso,
    truncate_text,
    validate_http_url,
)
from tools.web.limits import MAX_WEB_TIMEOUT_SEC
from tools.web.quality import assess_web_text
from tools.web.registry import WebToolSchema, register
from tools.web.tool_result import WebToolResult


def _failure(
    *,
    url: str,
    domain: str = "",
    code: str,
    reason: str,
    hint: str = "",
    trace: list[str] | None = None,
    http_status: int = 0,
) -> WebToolResult:
    return WebToolResult(
        tool_name="fetch_web_page",
        status="failed",
        url=url,
        final_url=url,
        domain=domain,
        http_status=http_status,
        error_code=code,
        failure_reason=reason,
        next_action_hint=hint,
        trace=trace or [],
        quality=assess_web_text(""),
    )


def _fetch_web_page(url: str, *, timeout_sec: int | None = None) -> WebToolResult:
    trace = [f"v16_web:fetch_web_page:start url={url}"]
    clean_url, domain, err = validate_http_url(url)
    if err:
        return _failure(
            url=clean_url or url,
            domain=domain,
            code=err,
            reason="URL 为空、格式无效或 scheme 不受支持",
            hint="请提供 http:// 或 https:// 开头的网页 URL。",
            trace=trace + [f"v16_web:validate:failed error={err}"],
        )

    try:
        resp = fetch_http_text(clean_url, timeout=int(timeout_sec or MAX_WEB_TIMEOUT_SEC))
    except urllib.error.HTTPError as e:
        code = errors.ACCESS_DENIED if e.code in (401, 403) else errors.HTTP_ERROR
        return _failure(
            url=clean_url,
            domain=domain,
            code=code,
            reason=f"HTTP 请求失败，状态码 {e.code}",
            hint="确认 URL 可访问；若需要登录，请走 fetch_with_cookie。",
            trace=trace + [f"v16_web:http:error status={e.code}"],
            http_status=int(e.code),
        )
    except ValueError as e:
        code = errors.WEB_TOO_LARGE if str(e) == "web_too_large" else errors.FETCH_FAILED
        return _failure(
            url=clean_url,
            domain=domain,
            code=code,
            reason="网页内容超过处理上限" if code == errors.WEB_TOO_LARGE else str(e),
            hint="缩小网页内容或提高 MAX_WEB_BYTES。",
            trace=trace + [f"v16_web:http:failed error={code}"],
        )
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:  # noqa: B025, BLE001
        return _failure(
            url=clean_url,
            domain=domain,
            code=errors.FETCH_FAILED,
            reason=f"网页抓取失败: {type(e).__name__}: {e}",
            hint="稍后重试，或检查网络/URL。",
            trace=trace + [f"v16_web:http:exception type={type(e).__name__}"],
        )

    html = resp.html
    final_url = resp.final_url or clean_url
    _final_parsed = urllib.parse.urlparse(final_url)
    final_domain = (_final_parsed.hostname or _final_parsed.netloc).lower() or domain
    title = extract_title(html) or final_url
    extraction_method = "trafilatura"
    warnings: list[str] = []

    try:
        text = extract_with_trafilatura(html, final_url)
        if not text:
            raise RuntimeError("empty trafilatura text")
        trace.append(f"v16_web:trafilatura:ok chars={len(text)}")
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:  # noqa: BLE001
        trace.append(f"v16_web:trafilatura:failed type={type(e).__name__}")
        warnings.append(errors.BEAUTIFULSOUP_FALLBACK_USED)
        extraction_method = "beautifulsoup_fallback"
        text = extract_with_bs4(html)
        trace.append(f"v16_web:beautifulsoup:chars={len(text)}")

    text = truncate_text(text)
    wall_code = looks_like_access_wall(text, html)
    if wall_code in (errors.CAPTCHA_OR_ANTIBOT, errors.ACCESS_DENIED):
        return _failure(
            url=clean_url,
            domain=final_domain,
            code=wall_code,
            reason="网页出现验证码/反爬或访问拒绝提示",
            hint="本系统不会绕过验证码、强反爬或无权限内容。",
            trace=trace + [f"v16_web:access_wall error={wall_code}"],
            http_status=resp.http_status,
        )
    if wall_code == errors.COOKIE_REQUIRED:
        return _failure(
            url=clean_url,
            domain=final_domain,
            code=errors.COOKIE_REQUIRED,
            reason="网页需要登录态或 cookie 才能访问正文",
            hint="用户显式授权后可使用 fetch_with_cookie。",
            trace=trace + ["v16_web:cookie_required"],
            http_status=resp.http_status,
        )

    quality = assess_web_text(text)
    warnings.extend(str(w) for w in quality.get("warnings", []) if w)
    quality_level = str(quality.get("quality_level", "failed"))
    if quality_level == "failed" or not text.strip():
        return _failure(
            url=clean_url,
            domain=final_domain,
            code=errors.EMPTY_EXTRACTED_TEXT if not text.strip() else errors.LOW_CONTENT_QUALITY,
            reason="网页正文为空或质量过低",
            hint="请换用正文更完整的页面，或尝试动态网页抓取。",
            trace=trace + [f"v16_web:quality:failed level={quality_level}"],
            http_status=resp.http_status,
        )
    if quality_level == "low":
        return _failure(
            url=clean_url,
            domain=final_domain,
            code=errors.LOW_CONTENT_QUALITY,
            reason="网页正文过短、重复或疑似导航噪音",
            hint="请提供文章正文页，或尝试动态网页抓取。",
            trace=trace + [f"v16_web:quality:low text_length={quality.get('text_length')}"],
            http_status=resp.http_status,
        )

    metadata = {
        "url": clean_url,
        "final_url": final_url,
        "domain": final_domain,
        "title": title,
        "source_type": "web_url",
        "extraction_method": extraction_method,
        "fetch_method": "static",
        "parser_name": "fetch_web_page",
        "content_hash": content_hash(text),
        "text_length": len(text),
        "quality_level": quality_level,
        "retrieved_at": now_iso(),
        "http_status": resp.http_status,
        "requires_cookie": False,
        "cookie_used": False,
    }
    trace.append(f"v16_web:quality level={quality_level} chars={len(text)}")
    return WebToolResult(
        tool_name="fetch_web_page",
        status="success",
        url=clean_url,
        final_url=final_url,
        domain=final_domain,
        title=title,
        text=text,
        metadata=metadata,
        quality=quality,
        warnings=warnings[:8],
        http_status=resp.http_status,
        extraction_method=extraction_method,
        fetch_method="static",
        trace=trace + ["v16_web:fetch_web_page:done"],
    )


register(WebToolSchema(
    tool_name="fetch_web_page",
    description="Fetch and extract a normal static web page into a ToolResult.",
    input_schema={
        "type": "object",
        "required": ["url"],
        "properties": {
            "url": {"type": "string"},
            "timeout_sec": {"type": "integer", "default": MAX_WEB_TIMEOUT_SEC},
        },
    },
    output_schema={"type": "object", "required": ["tool_name", "status", "text", "metadata", "quality", "error_code", "trace"]},
    call_fn=_fetch_web_page,
))
