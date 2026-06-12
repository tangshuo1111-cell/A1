"""KB retrieval orchestration — sole business-layer retrieve entry.

Business / agent / application code must import retrieval only from this module
(or ``kb_pipeline`` / ``rag_orchestration_service`` compat wrappers that delegate here).
Direct ``rag.*`` / ``knowledge.*`` / ``storage.knowledge_store`` imports are forbidden
outside ``services/capabilities/knowledge/``."""

from __future__ import annotations

from typing import Any

from rag.schema import RetrievedChunk

__all__ = [
    "retrieve_knowledge",
    "fetch_knowledge_chunks",
    "search_kb",
    "count_kb_chunks",
]


def retrieve_knowledge(
    query: str,
    *,
    top_k: int = 5,
    strategy: str = "auto",
    filters: dict[str, str] | None = None,
    embedding_enabled: bool | None = None,
) -> tuple[list[RetrievedChunk], dict[str, Any]]:
    from rag.retrieve_knowledge import retrieve_knowledge as _retrieve

    return _retrieve(
        query,
        top_k=top_k,
        strategy=strategy,
        filters=filters,
        embedding_enabled=embedding_enabled,
    )


def fetch_knowledge_chunks(
    query: str,
    *,
    top_k: int = 5,
    strategy: str = "auto",
    filters: dict[str, str] | None = None,
) -> list[RetrievedChunk]:
    """Structured chunks only — preferred over legacy text block helpers."""
    chunks, _trace = retrieve_knowledge(
        query,
        top_k=top_k,
        strategy=strategy,
        filters=filters,
    )
    return chunks


def search_kb(query: str, *, top_k: int = 8) -> list[Any]:
    from storage import knowledge_store

    return knowledge_store.search(query, top_k=top_k)


def count_kb_chunks() -> int:
    from storage import knowledge_store

    return knowledge_store.count_chunks()
