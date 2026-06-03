"""
URL 安全规则。

防止 SSRF：只允许 http/https，拒绝 localhost、内网、file:// 等。
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

# 拒绝的 host 模式
_BLOCKED_HOSTS = re.compile(
    r"^(localhost|127\.\d+\.\d+\.\d+|0\.0\.0\.0|::1|\[::1\])$",
    re.IGNORECASE,
)

# 内网 CIDR
_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
]


def check_url_safe(url: str) -> tuple[bool, str]:
    """
    检查 URL 是否安全可访问。

    Returns:
        (True, "") 如果安全；(False, reason) 如果不安全。
    """
    if not url or not url.strip():
        return False, "URL 为空"

    parsed = urlparse(url)

    # 只允许 http/https
    if parsed.scheme not in ("http", "https"):
        return False, f"不允许的协议：{parsed.scheme}"

    host = parsed.hostname or ""

    if not host:
        return False, "无法解析 host"

    # 拒绝 localhost 等
    if _BLOCKED_HOSTS.match(host):
        return False, f"禁止访问本地地址：{host}"

    # 拒绝纯 IP 内网地址
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return False, f"禁止访问内网地址：{host}"
        for net in _PRIVATE_NETS:
            if ip in net:
                return False, f"禁止访问内网地址：{host}"
    except ValueError:
        pass  # 不是 IP，是域名，继续

    return True, ""
