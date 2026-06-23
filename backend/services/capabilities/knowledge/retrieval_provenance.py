"""Knowledge capability facade for retrieval provenance (re-export rag owner)."""

from __future__ import annotations

from rag.retrieval_provenance import (
    SOURCE_KIND_USER_COMMITTED,
    chunk_source_kind,
    count_user_committed_hits,
    is_user_committed_chunk,
)

__all__ = [
    "SOURCE_KIND_USER_COMMITTED",
    "chunk_source_kind",
    "count_user_committed_hits",
    "is_user_committed_chunk",
]
