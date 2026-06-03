"""
密钥检查工具。

用于启动时验证必要的 API key 是否存在，以及确保 key 不泄露到日志/错误返回。
"""

from __future__ import annotations

import os
import re

from config.safe_rule import SAFE


def check_env_keys(required: list[str] | None = None) -> dict[str, bool]:
    """
    检查环境变量中的 key 是否存在。

    Args:
        required: 需要检查的环境变量名列表。为 None 时检查常用 key。

    Returns:
        {key_name: exists} 字典。
    """
    if required is None:
        required = list(SAFE.secret_env_prefixes)

    return {key: bool(os.getenv(key)) for key in required}


def redact_value(value: str) -> str:
    """将 key 值脱敏为 前4位***后4位 格式。"""
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]


_KEY_PATTERN = re.compile(
    r"(sk-[a-zA-Z0-9]{20,}|AKIA[A-Z0-9]{16}|ghp_[a-zA-Z0-9]{36})",
)


def contains_secret(text: str) -> bool:
    """检测文本中是否包含疑似 API key 的模式。"""
    if _KEY_PATTERN.search(text):
        return True
    for prefix in SAFE.secret_env_prefixes:
        val = os.getenv(prefix, "")
        if val and val in text:
            return True
    return False
