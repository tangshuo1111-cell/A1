"""Cookie-authorized web fetch; JSON cookie、域/重定向/脱敏增强。"""

from __future__ import annotations

import time
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
    looks_like_paywall_text,
    now_iso,
    same_domain,
    truncate_text,
    validate_http_url,
)
from tools.web.cookie_auth import (
    parse_cookie_input,
    redacted_cookie_trace_hint,
    resolve_expected_cookie_domain,
)
from tools.web.limits import MAX_COOKIE_BYTES, MAX_WEB_TIMEOUT_SEC
from tools.web.quality import assess_web_text
from tools.web.registry import WebToolSchema, register
from tools.web.tool_result import WebToolResult


def _fail(
    url: str,
    domain: str,
    code: str,
    reason: str,
    hint: str,
    trace: list[str],
    *,
    cookie_used: bool = False,
    duration_ms: float = 0.0,
) -> WebToolResult:
    return WebToolResult(
        tool_name="fetch_with_cookie",
        status="failed",
        url=url,
        final_url=url,
        domain=domain,
        fetch_method="cookie",
        requires_cookie=True,
        cookie_used=bool(cookie_used),
        error_code=code,
        failure_reason=reason,
        next_action_hint=hint,
        quality=assess_web_text(""),
        trace=trace,
        duration_ms=duration_ms,
    )


def _fetch_with_cookie(
    url: str,
    *,
    cookie: str = "",
    cookie_ref: str = "",
    cookie_domain: str = "",
    timeout_sec: int | None = None,
    task_id: str = "",
    _http_fetch=None,
) -> WebToolResult:
    t0 = time.perf_counter()

    def _ms() -> float:
        return (time.perf_counter() - t0) * 1000.0

    trace = ["v16_web:fetch_with_cookie:start"]
    clean_url, domain, err = validate_http_url(url)
    if err:
        return _fail(clean_url or url, domain, err, "URL 无效或 scheme 不受支持", "请提供 http/https URL。", trace)
    if not (cookie or cookie_ref):
        return _fail(
            clean_url,
            domain,
            errors.COOKIE_REQUIRED,
            "cookie 网页抓取必须由用户显式提供 cookie 或 cookie_ref",
            "请在授权后提供 cookie 或 cookie_ref。",
            trace + ["v16_web:cookie:missing"],
            duration_ms=_ms(),
        )

    jar_domains: list[str] = []
    cookie_count = 0
    if cookie:
        blob = cookie.strip()
        if len(blob.encode("utf-8", errors="replace")) > MAX_COOKIE_BYTES:
            return _fail(clean_url, domain, errors.WEB_TOO_LARGE, "cookie 超过 MAX_COOKIE_BYTES", "请缩小 cookie。", trace, duration_ms=_ms())
        parsed = parse_cookie_input(blob, cookie_domain_param=cookie_domain)
        if parsed.error_code:
            code = parsed.error_code
            if code == "cookie_required":
                code = errors.COOKIE_REQUIRED
            elif code == "invalid_cookie_format":
                code = errors.INVALID_COOKIE_FORMAT
            elif code == "cookie_expired":
                code = errors.COOKIE_EXPIRED
            return _fail(
                clean_url,
                domain,
                code,
                parsed.failure_reason,
                "检查 cookie JSON / Header 格式与有效期。",
                trace + ["v16_web:cookie:parse_failed"],
                duration_ms=_ms(),
            )
        cookie_header = parsed.header
        jar_domains = parsed.domains
        cookie_count = parsed.cookie_count
    else:
        ref = (cookie_ref or "").strip()
        if len(ref.encode("utf-8", errors="replace")) > MAX_COOKIE_BYTES:
            return _fail(clean_url, domain, errors.WEB_TOO_LARGE, "cookie_ref 过大", "请缩小引用。", trace, duration_ms=_ms())
        cookie_header = ref
        cookie_count = max(1, ref.count(";") + 1) if "=" in ref else 1
        if cookie_domain:
            jar_domains = [cookie_domain.strip().lower().lstrip(".")]

    expected_domain, dom_err = resolve_expected_cookie_domain(
        domain,
        cookie_domain_param=cookie_domain,
        jar_domains=jar_domains,
    )
    if dom_err:
        return _fail(
            clean_url,
            domain,
            errors.COOKIE_DOMAIN_MISMATCH,
            "请求 URL 与 cookie 授权 domain 不匹配",
            "仅能在与 cookie domain 一致的站点使用该授权。",
            trace + ["v16_web:cookie:domain_mismatch"],
            cookie_used=True,
            duration_ms=_ms(),
        )
    if expected_domain and not same_domain(clean_url, expected_domain):
        return _fail(
            clean_url,
            domain,
            errors.COOKIE_DOMAIN_MISMATCH,
            "cookie_domain 与目标 URL domain 不一致",
            "请修正 cookie_domain 或 URL。",
            trace + [redacted_cookie_trace_hint(cookie_count, jar_domains)],
            cookie_used=True,
            duration_ms=_ms(),
        )

    trace.append(redacted_cookie_trace_hint(cookie_count, jar_domains))
    fetch_fn = _http_fetch or fetch_http_text
    try:
        resp = fetch_fn(clean_url, timeout=int(timeout_sec or MAX_WEB_TIMEOUT_SEC), cookie_header=cookie_header)
    except urllib.error.HTTPError as e:
        code = errors.COOKIE_INVALID_OR_EXPIRED if e.code in (401, 403) else errors.HTTP_ERROR
        return _fail(
            clean_url,
            domain,
            code,
            f"HTTP {e.code}，cookie 授权可能无效或权限不足",
            "重新授权 cookie；本系统不绕过无权限内容。",
            trace + [f"v16_web:cookie:http_error status={e.code}"],
            cookie_used=True,
            duration_ms=_ms(),
        )
    except (OSError, ValueError, RuntimeError, TimeoutError) as e:  # noqa: BLE001
        return _fail(
            clean_url,
            domain,
            errors.FETCH_FAILED,
            f"cookie 网页抓取失败: {type(e).__name__}",
            "检查 URL、网络与 cookie。",
            trace + [f"v16_web:cookie:exception type={type(e).__name__}"],
            cookie_used=True,
            duration_ms=_ms(),
        )

    html = resp.html
    final_url = resp.final_url or clean_url
    _final_parsed = urllib.parse.urlparse(final_url)
    final_domain = (_final_parsed.hostname or _final_parsed.netloc).lower() or domain
    if not same_domain(final_url, expected_domain):
        return _fail(
            clean_url,
            final_domain,
            errors.COOKIE_REDIRECT_DOMAIN_MISMATCH,
            "重定向后的 URL 超出 cookie 授权 domain",
            "勿跨站跟踪重定向；检查站点是否有外链跳转。",
            trace + ["v16_web:cookie:redirect_domain_mismatch"],
            cookie_used=True,
            duration_ms=_ms(),
        )

    title = extract_title(html) or final_url
    extraction_method = "trafilatura_cookie"
    warnings: list[str] = []
    try:
        text = extract_with_trafilatura(html, final_url)
        if not text:
            raise RuntimeError("empty trafilatura text")
    except (OSError, ValueError, RuntimeError, TimeoutError):  # noqa: BLE001
        extraction_method = "beautifulsoup_cookie_fallback"
        warnings.append(errors.BEAUTIFULSOUP_FALLBACK_USED)
        text = extract_with_bs4(html)
    text = truncate_text(text)

    if looks_like_paywall_text(text, html):
        return _fail(
            clean_url,
            final_domain,
            errors.PAYWALL_NOT_SUPPORTED,
            "检测到付费墙或订阅墙",
            "本系统不绕过付费墙。",
            trace + ["v16_web:cookie:paywall"],
            cookie_used=True,
            duration_ms=_ms(),
        )

    wall_code = looks_like_access_wall(text, html)
    if wall_code in (errors.COOKIE_REQUIRED, errors.ACCESS_DENIED):
        return _fail(
            clean_url,
            final_domain,
            errors.COOKIE_INVALID_OR_EXPIRED,
            "cookie 会话无效或仍停留在登录/权限页",
            "请重新授权有效 cookie。",
            trace + ["v16_web:cookie:session_invalid"],
            cookie_used=True,
            duration_ms=_ms(),
        )
    if wall_code in (errors.CAPTCHA_OR_ANTIBOT, errors.LOGIN_REQUIRED):
        if wall_code == errors.LOGIN_REQUIRED:
            return _fail(
                clean_url,
                final_domain,
                errors.COOKIE_INVALID_OR_EXPIRED,
                "页面仍要求登录",
                "请确认 cookie 对应已登录会话。",
                trace + ["v16_web:cookie:login_wall"],
                cookie_used=True,
                duration_ms=_ms(),
            )
        return _fail(
            clean_url,
            final_domain,
            errors.CAPTCHA_NOT_SUPPORTED,
            "页面要求验证码或触发反爬",
            "本系统不绕过验证码。",
            trace + ["v16_web:cookie:captcha"],
            cookie_used=True,
            duration_ms=_ms(),
        )

    quality = assess_web_text(text)
    warnings.extend(str(w) for w in quality.get("warnings", []) if w)
    if quality.get("quality_level") in ("failed", "low"):
        return _fail(
            clean_url,
            final_domain,
            errors.EMPTY_EXTRACTED_TEXT if not text.strip() else errors.LOW_CONTENT_QUALITY,
            "cookie 网页正文为空或质量过低",
            "确认 cookie 对应页面为正文页。",
            trace + [f"v16_web:cookie:quality_failed level={quality.get('quality_level')}"],
            cookie_used=True,
            duration_ms=_ms(),
        )

    total_ms = _ms()
    metadata = {
        "url": clean_url,
        "final_url": final_url,
        "domain": final_domain,
        "title": title,
        "source_type": "web_url",
        "extraction_method": extraction_method,
        "fetch_method": "cookie",
        "provider": "cookie_http",
        "auth_mode": "cookie",
        "cookie_redacted": True,
        "cookie_count": cookie_count,
        "cookie_domains": list(dict.fromkeys(jar_domains))[:8],
        "parser_name": "fetch_with_cookie",
        "content_hash": content_hash(text),
        "text_length": len(text),
        "quality_level": quality.get("quality_level", ""),
        "retrieved_at": now_iso(),
        "status_code": resp.http_status,
        "http_status": resp.http_status,
        "requires_cookie": True,
        "cookie_used": True,
        "duration_ms": total_ms,
        "mcp_mode": "mcp_compatible_adapter",
    }
    return WebToolResult(
        tool_name="fetch_with_cookie",
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
        requires_cookie=True,
        cookie_used=True,
        extraction_method=extraction_method,
        fetch_method="cookie",
        trace=trace + [f"v16_web:cookie:ok chars={len(text)}"],
        duration_ms=total_ms,
        task_id=(task_id or "").strip(),
    )


register(WebToolSchema(
    tool_name="fetch_with_cookie",
    description="Fetch a cookie-authorized web page without exposing cookie values.",
    input_schema={
        "type": "object",
        "required": ["url"],
        "properties": {
            "url": {"type": "string"},
            "cookie": {"type": "string"},
            "cookie_ref": {"type": "string"},
            "cookie_domain": {"type": "string"},
            "timeout_sec": {"type": "integer", "default": MAX_WEB_TIMEOUT_SEC},
            "task_id": {"type": "string"},
        },
    },
    output_schema={"type": "object", "required": ["tool_name", "status", "text", "metadata", "quality", "error_code", "trace"]},
    call_fn=_fetch_with_cookie,
))
