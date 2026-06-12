"""Cookie 解析、脱敏与校验（不记录明文）。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field


@dataclass
class CookieParseOutcome:
    header: str = ""
    domains: list[str] = field(default_factory=list)
    cookie_count: int = 0
    error_code: str = ""
    failure_reason: str = ""


def _norm_domain(d: str) -> str:
    return (d or "").strip().lower().lstrip(".")


def parse_cookie_input(raw: str, *, cookie_domain_param: str = "") -> CookieParseOutcome:
    """
    支持：
    - JSON 数组：[{"name","value","domain","expires",...}, ...]
    - 原生 Cookie 请求头字符串：a=b; c=d
    """
    s = (raw or "").strip()
    if not s:
        return CookieParseOutcome(error_code="cookie_required", failure_reason="cookie 为空")

    if s.startswith("["):
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            return CookieParseOutcome(
                error_code="invalid_cookie_format",
                failure_reason="cookie JSON 无法解析",
            )
        if not isinstance(data, list):
            return CookieParseOutcome(
                error_code="invalid_cookie_format",
                failure_reason="cookie JSON 必须是数组",
            )
        parts: list[str] = []
        domains: list[str] = []
        now = time.time()
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                return CookieParseOutcome(
                    error_code="invalid_cookie_format",
                    failure_reason=f"cookie[{i}] 必须是对象",
                )
            name = item.get("name")
            if not name or not isinstance(name, str):
                return CookieParseOutcome(
                    error_code="invalid_cookie_format",
                    failure_reason=f"cookie[{i}] 缺少合法 name",
                )
            val = item.get("value")
            if val is None or not isinstance(val, (str, int, float)):
                return CookieParseOutcome(
                    error_code="invalid_cookie_format",
                    failure_reason=f"cookie[{i}] 缺少合法 value",
                )
            if "\n" in str(name) or "\r" in str(name) or "\n" in str(val) or "\r" in str(val):
                return CookieParseOutcome(
                    error_code="invalid_cookie_format",
                    failure_reason=f"cookie[{i}] 含非法换行",
                )
            exp = item.get("expires")
            if exp is not None:
                try:
                    if float(exp) < now:
                        return CookieParseOutcome(
                            error_code="cookie_expired",
                            failure_reason="cookie expires 已过期",
                        )
                except (TypeError, ValueError):
                    return CookieParseOutcome(
                        error_code="invalid_cookie_format",
                        failure_reason=f"cookie[{i}] expires 非法",
                    )
            dom = _norm_domain(str(item.get("domain") or ""))
            if dom:
                domains.append(dom)
            parts.append(f"{str(name).strip()}={str(val)}")
        if not parts:
            return CookieParseOutcome(
                error_code="invalid_cookie_format",
                failure_reason="cookie 数组为空",
            )
        if cookie_domain_param:
            d0 = _norm_domain(cookie_domain_param)
            if d0 and d0 not in domains:
                domains.append(d0)
        return CookieParseOutcome(
            header="; ".join(parts),
            domains=sorted(set(domains)),
            cookie_count=len(parts),
        )

    if ";" not in s and "=" not in s:
        return CookieParseOutcome(
            error_code="invalid_cookie_format",
            failure_reason="cookie 格式既不是 JSON 也不是 name=value",
        )
    pairs = [p.strip() for p in s.split(";") if p.strip()]
    for p in pairs:
        if "=" not in p:
            return CookieParseOutcome(
                error_code="invalid_cookie_format",
                failure_reason="cookie 分段缺少 =",
            )
    doms: list[str] = []
    if cookie_domain_param:
        doms.append(_norm_domain(cookie_domain_param))
    return CookieParseOutcome(header=s, domains=sorted(set(doms)), cookie_count=len(pairs))


def host_matches_cookie_domain(host: str, cookie_domain: str) -> bool:
    h = _norm_domain(host)
    exp = _norm_domain(cookie_domain)
    if not h or not exp:
        return False
    return h == exp or h.endswith("." + exp)


def resolve_expected_cookie_domain(
    url_host: str,
    *,
    cookie_domain_param: str,
    jar_domains: list[str],
) -> tuple[str, str]:
    param = _norm_domain(cookie_domain_param)
    if param:
        if not host_matches_cookie_domain(url_host, param):
            return "", "cookie_domain_mismatch"
        return param, ""
    if jar_domains:
        for d in jar_domains:
            if host_matches_cookie_domain(url_host, d):
                return d, ""
        return "", "cookie_domain_mismatch"
    return _norm_domain(url_host), ""


def redacted_cookie_trace_hint(cookie_count: int, domains: list[str]) -> str:
    dom_part = ",".join(domains[:4]) if domains else ""
    return f"v16_web:cookie:redacted count={cookie_count} domains={dom_part}"
