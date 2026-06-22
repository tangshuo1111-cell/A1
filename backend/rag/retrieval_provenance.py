"""Retrieval provenance helpers — single source for chunk source_kind semantics."""

from __future__ import annotations

from rag.schema import RetrievedChunk

SOURCE_KIND_USER_COMMITTED = "user_committed"


def chunk_source_kind(chunk: RetrievedChunk) -> str:
    meta = dict(getattr(chunk, "metadata", None) or {})
    return str(meta.get("source_kind") or "").strip()


def is_user_committed_chunk(chunk: RetrievedChunk) -> bool:
    return chunk_source_kind(chunk) == SOURCE_KIND_USER_COMMITTED


def count_user_committed_hits(chunks: list[RetrievedChunk]) -> int:
    return sum(1 for chunk in chunks if is_user_committed_chunk(chunk))
