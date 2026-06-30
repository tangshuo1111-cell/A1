"""动态网页 Playwright provider（延迟导入；可注入 fake page 做测试）。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from tools.web import errors

logger = logging.getLogger("light_maqa")

DynamicRunner = Callable[..., "DynamicPageOutcome"]


@dataclass
class DynamicPageOutcome:
    ok: bool
    html: str = ""
    final_url: str = ""
    error_code: str = ""
    failure_reason: str = ""
    next_action_hint: str = ""
    duration_ms: float = 0.0
    provider: str = "playwright"
    provider_type: str = "dynamic_page"
    production_ready: bool = True
    production_capable: bool = True
    http_status: int = 0
    metadata_extra: dict[str, Any] = field(default_factory=dict)


def classify_dynamic_wall(text: str, html: str) -> tuple[str, str, str]:  # noqa: ARG001
    """返回 (error_code, failure_reason, hint)；无阻断则 ("", "", "")。

    只扫可见正文 text：访问墙会用挑战/登录文案替换可见内容，标志词必然落在正文里。
    原始 html 头含框架样板（如 MediaWiki 站点注册的 hCaptcha 模块名 `ext.confirmEdit.hCaptcha`），
    裸子串扫描会把能正常阅读的 MediaWiki/维基页误判成验证码墙、丢弃已抓到的好正文，故不扫 html。
    """
    sample = (text or "").lower()
    captcha_tokens = ("captcha", "verify you are human", "验证码", "人机验证", "anti-bot", "hcaptcha", "recaptcha")
    login_tokens = (
        "login required",
        "please log in",
        "sign in to continue",
        "请登录",
        "登录后",
        "sign in",
    )
    forbidden_tokens = ("403 forbidden", "http 403", "access forbidden", "forbidden", "拒绝访问")
    if any(tok in sample for tok in captcha_tokens):
        return (
            errors.CAPTCHA_NOT_SUPPORTED,
            "页面包含验证码或人机验证",
            "本系统不自动绕过验证码；请改用手动材料或静态可访问页。",
        )
    if any(tok in sample for tok in login_tokens):
        return (
            errors.LOGIN_REQUIRED,
            "页面要求登录后才可阅读正文",
            "本系统不绕过登录墙；请提供 Cookie 抓取或改用授权内容。",
        )
    if any(tok in sample for tok in forbidden_tokens):
        return (
            errors.DYNAMIC_PAGE_FORBIDDEN,
            "页面或站点拒绝访问（403/禁止）",
            "检查权限、地区限制或换用可匿名访问的页面。",
        )
    if "access denied" in sample or "无权限" in sample:
        return (
            errors.ACCESS_DENIED,
            "访问被拒绝或无权限",
            "确认 URL 可匿名访问或调整权限后再试。",
        )
    return "", "", ""


def run_fake_playwright_dynamic(
    *,
    ok: bool = True,
    html: str = "<html><body><p>fixture</p></body></html>",
    error_code: str = "",
    failure_reason: str = "",
) -> DynamicPageOutcome:
    """仅测试：非生产 ready。"""
    if ok:
        return DynamicPageOutcome(
            ok=True,
            html=html,
            final_url="https://example.com/fake",
            production_ready=False,
            production_capable=False,
        )
    return DynamicPageOutcome(
        ok=False,
        error_code=error_code or errors.DYNAMIC_PAGE_PROVIDER_ERROR,
        failure_reason=failure_reason or "fixture",
        production_ready=False,
        production_capable=False,
    )


def _real_playwright_run(
    clean_url: str,
    *,
    timeout_ms: int,
    wait_until: str,
    trace: list[str],
) -> DynamicPageOutcome:
    t0 = time.perf_counter()

    def _ms() -> float:
        return (time.perf_counter() - t0) * 1000.0

    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return DynamicPageOutcome(
            ok=False,
            error_code=errors.PLAYWRIGHT_DEPENDENCY_MISSING,
            failure_reason=f"Playwright Python 依赖不可用: {type(e).__name__}",
            next_action_hint="安装 playwright 后再使用动态网页；静态 fetch_web_page 不受影响。",
            duration_ms=_ms(),
        )

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except (OSError, RuntimeError) as e:
                return DynamicPageOutcome(
                    ok=False,
                    error_code=errors.BROWSER_NOT_INSTALLED,
                    failure_reason=f"Playwright 浏览器不可用: {type(e).__name__}",
                    next_action_hint="运行 playwright install chromium。",
                    duration_ms=_ms(),
                )
            page = browser.new_page()
            try:
                resp = page.goto(
                    clean_url,
                    wait_until=cast(Literal["commit", "domcontentloaded", "load", "networkidle"], wait_until),
                    timeout=timeout_ms,
                )
            except PlaywrightTimeoutError:
                browser.close()
                return DynamicPageOutcome(
                    ok=False,
                    error_code=errors.DYNAMIC_PAGE_TIMEOUT,
                    failure_reason="动态网页渲染超时",
                    next_action_hint="提高 timeout 或改用 wait_until=domcontentloaded。",
                    duration_ms=_ms(),
                )
            status = int(getattr(resp, "status", 0) or 0) if resp is not None else 0
            if status == 403:
                browser.close()
                return DynamicPageOutcome(
                    ok=False,
                    error_code=errors.DYNAMIC_PAGE_FORBIDDEN,
                    failure_reason="HTTP 403 Forbidden",
                    next_action_hint="该 URL 拒绝自动化访问。",
                    duration_ms=_ms(),
                    http_status=403,
                )
            html = page.content()
            final_url = page.url or clean_url
            browser.close()
    except PlaywrightTimeoutError:
        return DynamicPageOutcome(
            ok=False,
            error_code=errors.DYNAMIC_PAGE_TIMEOUT,
            failure_reason="动态网页渲染超时",
            next_action_hint="提高 timeout 或改用 wait_until=domcontentloaded。",
            duration_ms=_ms(),
        )
    except Exception as e:  # noqa: BLE001
        name = type(e).__name__
        msg = str(e).lower()
        logger.warning("playwright dynamic failed: %s", e, exc_info=True)
        if "executable" in msg or ("browser" in msg and "launch" in msg):
            return DynamicPageOutcome(
                ok=False,
                error_code=errors.BROWSER_NOT_INSTALLED,
                failure_reason=str(e)[:200],
                next_action_hint="playwright install chromium",
                duration_ms=_ms(),
            )
        return DynamicPageOutcome(
            ok=False,
            error_code=errors.DYNAMIC_PAGE_PROVIDER_ERROR,
            failure_reason=f"{name}: {str(e)[:180]}",
            next_action_hint="检查浏览器依赖与网络。",
            duration_ms=_ms(),
        )

    return DynamicPageOutcome(
        ok=True,
        html=html or "",
        final_url=final_url,
        duration_ms=_ms(),
        http_status=status,
    )


def run_playwright_dynamic_page(
    clean_url: str,
    *,
    timeout_ms: int,
    wait_until: str,
    trace: list[str],
    runner: DynamicRunner | None = None,
) -> DynamicPageOutcome:
    impl: DynamicRunner = runner or _real_playwright_run
    return impl(clean_url, timeout_ms=timeout_ms, wait_until=wait_until, trace=trace)


__all__ = [
    "DynamicPageOutcome",
    "classify_dynamic_wall",
    "run_fake_playwright_dynamic",
    "run_playwright_dynamic_page",
]
