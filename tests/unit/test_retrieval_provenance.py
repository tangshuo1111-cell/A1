"""Unit tests for retrieval provenance (North Star 1 source_kind)."""

from __future__ import annotations

from rag.retrieval_provenance import (
    SOURCE_KIND_USER_COMMITTED,
    count_user_committed_hits,
    is_user_committed_chunk,
)
from rag.schema import RetrievedChunk


def _chunk(source_kind: str = "") -> RetrievedChunk:
    return RetrievedChunk(
        source_id="user/doc.md",
        chunk_id="user/doc.md::chunk::0",
        text="hello",
        metadata={"source_kind": source_kind},
    )


def test_user_committed_chunk_detection() -> None:
    assert is_user_committed_chunk(_chunk(SOURCE_KIND_USER_COMMITTED))
    assert not is_user_committed_chunk(_chunk(""))
    assert count_user_committed_hits([_chunk(SOURCE_KIND_USER_COMMITTED), _chunk("")]) == 1
