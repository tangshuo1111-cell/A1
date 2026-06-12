"""In-process pending knowledge store."""

from __future__ import annotations

import threading

from rag.pending_schema import (
    PENDING_KIND_COMMITTED,
    STATUS_COMMITTED,
    STATUS_DISCARDED,
    PendingKnowledgeItem,
)


class MemoryPendingStore:
    """Session-scoped pending items; thread-safe in-process cache."""

    def __init__(self) -> None:
        # PG-backed subclass may call parent mutations while already holding the
        # store lock; use a re-entrant lock to avoid self-deadlock.
        self._lock = threading.RLock()
        self._data: dict[str, list[PendingKnowledgeItem]] = {}

    def add(self, item: PendingKnowledgeItem) -> None:
        sid = item.session_id or "__default__"
        with self._lock:
            self._data.setdefault(sid, []).append(item)

    def get(self, pending_id: str) -> PendingKnowledgeItem | None:
        with self._lock:
            for items in self._data.values():
                for item in items:
                    if item.pending_id == pending_id:
                        return item
        return None

    def list_for_session(
        self,
        session_id: str,
        *,
        only_committable: bool = False,
    ) -> list[PendingKnowledgeItem]:
        sid = session_id or "__default__"
        with self._lock:
            items = list(self._data.get(sid, []))
        if only_committable:
            items = [i for i in items if i.is_committable]
        return items

    def get_recent(
        self,
        session_id: str,
        *,
        only_committable: bool = True,
    ) -> PendingKnowledgeItem | None:
        items = self.list_for_session(session_id, only_committable=only_committable)
        if not items:
            return None
        return items[-1]

    def mark_committed(
        self,
        pending_id: str,
        *,
        committed_source_id: str,
        chunk_count: int,
    ) -> bool:
        with self._lock:
            for items in self._data.values():
                for item in items:
                    if item.pending_id == pending_id:
                        item.commit_status = STATUS_COMMITTED
                        item.committed_source_id = committed_source_id
                        item.committed_chunk_count = chunk_count
                        item.pending_kind = PENDING_KIND_COMMITTED
                        return True
        return False

    def discard(self, pending_id: str) -> bool:
        with self._lock:
            for items in self._data.values():
                for item in items:
                    if item.pending_id == pending_id:
                        item.commit_status = STATUS_DISCARDED
                        return True
        return False

    def discard_session(self, session_id: str) -> None:
        sid = session_id or "__default__"
        with self._lock:
            self._data.pop(sid, None)

    def count_committable(self, session_id: str) -> int:
        return len(self.list_for_session(session_id, only_committable=True))

    def clear_all(self) -> None:
        with self._lock:
            self._data.clear()
