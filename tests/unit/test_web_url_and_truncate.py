"""网页工具：URL 校验、正文截断、静态/动态抓取失败与成功 mock 路径（第四轮 B-025 收口）。"""

from __future__ import annotations

import sys
import urllib.error
from dataclasses import replace
from email.message import Message

import pytest
from tests._support.bootstrap import find_repo_root

ROOT = find_repo_root(__file__)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config.cost_rule as cost_mod  # noqa: E402
import tools.web.fetch_dynamic_page  # noqa: F401, E402 — register
import tools.web.fetch_web_page  # noqa: F401, E402
from tools.web import errors  # noqa: E402
from tools.web.common import FetchResponse, truncate_text, validate_http_url  # noqa: E402
from tools.web.dynamic_providers import DynamicPageOutcome  # noqa: E402
from tools.web.registry import call_tool  # noqa: E402


def test_validate_http_url_empty() -> None:
    u, host, err = validate_http_url("")
    assert u == ""
    assert err == errors.INVALID_URL


def test_validate_http_url_rejects_non_http_scheme() -> None:
    u, _host, err = validate_http_url("ftp://a.example/x")
    assert err == errors.UNSUPPORTED_URL_SCHEME


def test_validate_http_url_ok() -> None:
    u, host, err = validate_http_url("https://Example.COM/path?q=1")
    assert err == ""
    assert "example.com" in host


def test_truncate_text_respects_cost_page_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cost_mod, "COST", replace(cost_mod.COST, web_page_max_chars=50))
    long = "字" * 200
    out = truncate_text(long)
    assert len(out) == 50


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://example.com/page",
        code,
        "err",
        Message(),
        None,
    )


def test_fetch_web_page_http_403_is_access_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.web.fetch_web_page.fetch_http_text",
        lambda *_a, **_k: (_ for _ in ()).throw(_http_error(403)),
    )
    r = call_tool("fetch_web_page", url="https://example.com/page")
    assert r.status == "failed"
    assert r.error_code == errors.ACCESS_DENIED
    assert r.http_status == 403


def test_fetch_web_page_http_500_is_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.web.fetch_web_page.fetch_http_text",
        lambda *_a, **_k: (_ for _ in ()).throw(_http_error(500)),
    )
    r = call_tool("fetch_web_page", url="https://example.com/page")
    assert r.status == "failed"
    assert r.error_code == errors.HTTP_ERROR


def test_fetch_web_page_timeout_maps_fetch_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.web.fetch_web_page.fetch_http_text",
        lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError("fetch timeout")),
    )
    r = call_tool("fetch_web_page", url="https://example.com/page")
    assert r.status == "failed"
    assert r.error_code == errors.FETCH_FAILED


def test_fetch_web_page_body_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.web.fetch_web_page.fetch_http_text",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("web_too_large")),
    )
    r = call_tool("fetch_web_page", url="https://example.com/page")
    assert r.status == "failed"
    assert r.error_code == errors.WEB_TOO_LARGE


def test_fetch_web_page_success_minimal_html(monkeypatch: pytest.MonkeyPatch) -> None:
    """足够正文字符 + 标题，使 trafilatura/BS4 至少一条路径达到 quality good。"""
    body = "这是可读正文。" * 20
    html = f"<html><head><title>单元测试页</title></head><body><p>{body}</p></body></html>"
    monkeypatch.setattr(
        "tools.web.fetch_web_page.fetch_http_text",
        lambda url, **k: FetchResponse(html=html, final_url=url, http_status=200),
    )
    r = call_tool("fetch_web_page", url="https://example.com/article")
    assert r.status == "success"
    assert (r.text or "").strip()
    assert r.http_status == 200


def test_fetch_dynamic_zero_timeout_is_rejected() -> None:
    r = call_tool("fetch_dynamic_page", url="https://example.com/d", timeout_sec=0)
    assert r.status == "failed"
    assert r.error_code == errors.DYNAMIC_PAGE_TIMEOUT


def test_fetch_dynamic_playwright_failure_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_url: str, **kw: object) -> DynamicPageOutcome:
        return DynamicPageOutcome(
            ok=False,
            error_code=errors.PLAYWRIGHT_DEPENDENCY_MISSING,
            failure_reason="no browser in unit",
        )

    monkeypatch.setattr(
        "tools.web.fetch_dynamic_page.dynamic_providers.run_playwright_dynamic_page",
        _boom,
    )
    r = call_tool("fetch_dynamic_page", url="https://example.com/dynamic")
    assert r.status == "failed"
    assert r.error_code == errors.PLAYWRIGHT_DEPENDENCY_MISSING


def test_fetch_dynamic_success_with_mocked_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    chunk = "动态渲染后的正文句子，用于质量检测。" * 8

    def _ok(url: str, **kw: object) -> DynamicPageOutcome:
        return DynamicPageOutcome(
            ok=True,
            html=f"<html><body><main><p>{chunk}</p></main></body></html>",
            final_url=url,
            duration_ms=2.0,
        )

    monkeypatch.setattr(
        "tools.web.fetch_dynamic_page.dynamic_providers.run_playwright_dynamic_page",
        _ok,
    )
    r = call_tool("fetch_dynamic_page", url="https://example.com/js-app", timeout_sec=30)
    assert r.status == "success"
    assert len((r.text or "").strip()) >= 80


def test_fetch_web_tool_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.web import registry as web_reg

    web_reg.disable_tool("fetch_web_page")
    try:
        r = call_tool("fetch_web_page", url="https://example.com/x")
        assert r.status == "failed"
        assert r.error_code == errors.TOOL_DISABLED
    finally:
        web_reg.enable_tool("fetch_web_page")
