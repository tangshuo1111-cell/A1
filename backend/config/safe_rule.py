"""
统一安全规则。

集中定义 key 保护、日志脱敏、错误返回等安全策略。
业务代码通过 `from config.safe_rule import SAFE` 使用。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SafeRule:
    """安全默认规则。"""

    # Key 保护：日志和错误返回中不得出现的环境变量前缀
    secret_env_prefixes: tuple[str, ...] = (
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "V16_TENCENT_SECRET",
        "V16_ASR_API_KEY",
        "V16_WEB_SEARCH_API_KEY",
        "DATABASE_URL",
    )

    # 日志脱敏：这些字段在日志输出时用 *** 替换
    log_redact_fields: tuple[str, ...] = (
        "api_key",
        "secret_id",
        "secret_key",
        "cookie",
        "authorization",
        "token",
    )

    # 错误返回：不暴露以下内容给客户端
    error_hide_traceback: bool = True
    error_hide_local_paths: bool = True
    error_hide_env_values: bool = True

    # 外部工具默认关闭：未显式开启时不出网
    tool_default_disabled: bool = True


SAFE = SafeRule()
