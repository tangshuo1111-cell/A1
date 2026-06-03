"""API 限流：slowapi + IP 维度。支持 Redis 后端（多副本共享限流状态）。"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address


def build_limiter() -> Limiter:
    from config.settings import settings

    storage_uri = settings.rate_limit_storage_uri or "memory://"
    return Limiter(
        key_func=get_remote_address,
        default_limits=[],
        storage_uri=storage_uri,
    )


limiter = build_limiter()


def chat_rate_limit_string() -> str:
    from config.settings import settings

    return settings.rate_limit_chat or "120/minute"
