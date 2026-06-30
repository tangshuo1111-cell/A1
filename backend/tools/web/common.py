"""Shared helpers for web tools."""

from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from tools.web import errors
from tools.web.limits import MAX_REDIRECTS, MAX_WEB_BYTES, MAX_WEB_TEXT_CHARS


@dataclass
class FetchResponse:
    html: str
    final_url: str
    http_status: int


def now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def validate_http_url(url: str) -> tuple[str, str, str]:
    u = (url or "").strip()
    if not u:
        return "", "", errors.INVALID_URL
    parsed = urllib.parse.urlparse(u)
    if parsed.scheme not in ("http", "https"):
        return u, "", errors.UNSUPPORTED_URL_SCHEME if parsed.scheme else errors.INVALID_URL
    if not parsed.netloc:
        return u, "", errors.INVALID_URL
    return u, (parsed.hostname or parsed.netloc).lower(), ""


def same_domain(url: str, expected_domain: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    domain = (parsed.hostname or parsed.netloc).lower()
    expected = (expected_domain or "").lower().lstrip(".")
    return bool(expected and (domain == expected or domain.endswith("." + expected)))


class _LimitedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self) -> None:
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirect_count += 1
        if self.redirect_count > MAX_REDIRECTS:
            raise urllib.error.HTTPError(newurl, 310, "too many redirects", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_http_text(url: str, *, timeout: int, cookie_header: str = "") -> FetchResponse:
    redirect_handler = _LimitedRedirect()
    opener = urllib.request.build_opener(redirect_handler)
    headers = {"User-Agent": "LightMAQA-V16R2/1.0"}
    if cookie_header:
        headers["Cookie"] = cookie_header
    req = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 0) or 0)
            raw = resp.read(MAX_WEB_BYTES + 1)
            if len(raw) > MAX_WEB_BYTES:
                raise ValueError("web_too_large")
            charset = resp.headers.get_content_charset() or "utf-8"
            return FetchResponse(
                html=raw.decode(charset, errors="replace"),
                final_url=str(resp.geturl() or url),
                http_status=status,
            )
    except urllib.error.HTTPError:
        raise
    except TimeoutError:
        raise TimeoutError("fetch timeout")  # noqa: B904


def extract_title(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    if soup.title and soup.title.string:
        return re.sub(r"\s+", " ", soup.title.string).strip()[:200]
    h1 = soup.find("h1")
    if h1:
        return re.sub(r"\s+", " ", h1.get_text(" ", strip=True)).strip()[:200]
    return ""


def extract_with_trafilatura(html: str, url: str) -> str:
    try:
        import trafilatura
    except (ImportError, ModuleNotFoundError) as e:
        raise RuntimeError(f"trafilatura unavailable: {type(e).__name__}") from e
    extracted = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    return (extracted or "").strip()


def extract_with_bs4(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = main.get_text("\n", strip=True)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    cleaned = "\n".join(ln for ln in lines if ln)
    return cleaned.strip()


def truncate_text(text: str) -> str:
    from config.cost_rule import COST

    limit = min(MAX_WEB_TEXT_CHARS, COST.web_page_max_chars)
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[:limit]


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="replace")).hexdigest()[:16]


def looks_like_paywall_text(text: str, html: str) -> bool:
    sample = f"{text}\n{html[:2500]}".lower()
    tokens = (
        "payment required",
        "subscribe to",
        "subscription required",
        "paywall",
        "upgrade to premium",
        "付费",
        "付费墙",
        "订阅后",
        "会员专享",
        "仅限会员",
    )
    return any(tok in sample for tok in tokens)


def looks_like_access_wall(text: str, html: str) -> str:  # noqa: ARG001
    # 只扫可见正文 text：访问墙的标志词会出现在正文；原始 html 头含框架样板
    # （如 MediaWiki 注册的 hCaptcha 模块名），裸子串扫 html 会误判正常 MediaWiki/维基页。
    sample = (text or "").lower()
    captcha_tokens = ("captcha", "verify you are human", "验证码", "人机验证", "anti-bot")
    login_tokens = ("login required", "please log in", "sign in", "请登录", "登录后", "cookie required")
    denied_tokens = ("access denied", "forbidden", "无权限", "拒绝访问")
    if any(tok in sample for tok in captcha_tokens):
        return errors.CAPTCHA_OR_ANTIBOT
    if any(tok in sample for tok in login_tokens):
        return errors.COOKIE_REQUIRED
    if any(tok in sample for tok in denied_tokens):
        return errors.ACCESS_DENIED
    return ""
