"""Pending knowledge store port."""

from __future__ import annotations

from typing import Protocol

from rag.pending_schema import PendingKnowledgeItem


class PendingStorePort(Protocol):
    def add(self, item: PendingKnowledgeItem) -> None: ...
    def get(self, pending_id: str) -> PendingKnowledgeItem | None: ...
    def list_for_session(
        self,
        session_id: str,
        *,
        only_committable: bool = False,
    ) -> list[PendingKnowledgeItem]: ...
    def get_recent(
        self,
        session_id: str,
        *,
        only_committable: bool = True,
    ) -> PendingKnowledgeItem | None: ...
    def mark_committed(
        self,
        pending_id: str,
        *,
        committed_source_id: str,
        chunk_count: int,
    ) -> bool: ...
    def discard(self, pending_id: str) -> bool: ...
    def discard_session(self, session_id: str) -> None: ...
    def count_committable(self, session_id: str) -> int: ...
