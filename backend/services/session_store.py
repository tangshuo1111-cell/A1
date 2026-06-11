"""会话状态存储 facade（G-024 / Round 8）。

实现由 ``storage.store_factory`` 按 ``STORE_BACKEND`` 选择 memory 或 pg；
本模块暴露显式 ``get_session_store()``，不再使用 lazy ``__getattr__`` proxy。
"""

from __future__ import annotations

from storage.memory_chat_session_store import MemoryChatSessionStore
from storage.ports.session_store import SessionStorePort
from storage.store_factory import get_session_store, reset_stores_for_tests

MemorySessionStore = MemoryChatSessionStore
SessionStore = SessionStorePort


def reset_session_store_for_tests() -> None:
    reset_stores_for_tests()


__all__ = [
    "MemorySessionStore",
    "SessionStore",
    "get_session_store",
    "reset_session_store_for_tests",
]
