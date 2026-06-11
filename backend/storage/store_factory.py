"""Chat session + pending store factory (Round 7)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storage.memory_chat_session_store import MemoryChatSessionStore
    from storage.memory_pending_store import MemoryPendingStore

_session_singleton: MemoryChatSessionStore | None = None
_pending_singleton: MemoryPendingStore | None = None


def create_session_store(backend: str | None = None):
    from config.settings import settings
    from storage.memory_chat_session_store import MemoryChatSessionStore

    kind = (backend or settings.store_backend or "memory").lower()
    if kind == "memory":
        return MemoryChatSessionStore()
    if kind == "pg":
        from storage.pg_chat_session_store import PgChatSessionStore

        return PgChatSessionStore()
    raise ValueError(f"unknown STORE_BACKEND: {kind!r}")


def create_pending_store(backend: str | None = None):
    from config.settings import settings
    from storage.memory_pending_store import MemoryPendingStore

    kind = (backend or settings.store_backend or "memory").lower()
    if kind == "memory":
        return MemoryPendingStore()
    if kind == "pg":
        from storage.pg_pending_store import PgPendingStore

        return PgPendingStore()
    raise ValueError(f"unknown STORE_BACKEND: {kind!r}")


def get_session_store():
    global _session_singleton
    if _session_singleton is None:
        _session_singleton = create_session_store()
    return _session_singleton


def get_pending_store():
    global _pending_singleton
    if _pending_singleton is None:
        _pending_singleton = create_pending_store()
    return _pending_singleton


def reset_stores_for_tests(*, clear_persistent: bool = True) -> None:
    """Clear singleton handles and optionally wipe underlying store state."""
    global _session_singleton, _pending_singleton
    if _session_singleton is not None and clear_persistent:
        _session_singleton.clear_all()
    if _pending_singleton is not None and clear_persistent:
        _pending_singleton.clear_all()
    _session_singleton = None
    _pending_singleton = None
