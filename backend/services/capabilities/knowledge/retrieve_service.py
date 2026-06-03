"""KB retrieval orchestration — sole MiddleAgent-facing retrieve entry."""

from __future__ import annotations

from typing import Any

from rag.schema import RetrievedChunk


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


def search_kb(query: str, *, top_k: int = 8) -> list[Any]:
    from storage import knowledge_store

    return knowledge_store.search(query, top_k=top_k)


def count_kb_chunks() -> int:
    from storage import knowledge_store

    return knowledge_store.count_chunks()
