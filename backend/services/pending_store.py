"""Pending store facade aligned with session_store."""

from __future__ import annotations

from storage.memory_pending_store import MemoryPendingStore
from storage.ports.pending_store import PendingStorePort
from storage.store_factory import (
    create_pending_store,
    get_pending_store,
    reset_stores_for_tests,
)

MemoryPendingStoreFacade = MemoryPendingStore
PendingStore = PendingStorePort
create_default_pending_store = create_pending_store


def reset_pending_store_for_tests() -> None:
    reset_stores_for_tests()


__all__ = [
    "MemoryPendingStoreFacade",
    "PendingStore",
    "create_default_pending_store",
    "get_pending_store",
    "reset_pending_store_for_tests",
]
