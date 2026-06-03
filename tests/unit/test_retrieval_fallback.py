"""语义检索失败时 hybrid_pipeline 回落 FTS。

V14 R1 更新：hybrid_pipeline 现在返回 list[RetrievedChunk]（不再是 dict）。
fake_retrieve 也需要返回 RetrievedChunk 列表。
"""

from __future__ import annotations

from unittest.mock import patch

from config.settings import settings


def test_hybrid_search_semantic_import_error_returns_fts(monkeypatch) -> None:
    """semantic 失败时 hybrid_pipeline 回落 FTS，返回 list[RetrievedChunk]。"""
    from rag.schema import RetrievedChunk

    monkeypatch.setattr(settings, "embedding_enabled", True)
    monkeypatch.setattr(settings, "retrieval_mode", "hybrid")

    # V14 R1：fake_retrieve 返回 RetrievedChunk（hybrid_pipeline 已修复 dict bug）
    def fake_retrieve(q: str, top_k: int = 5, *, filters=None):
        return [
            RetrievedChunk(
                source_id="s1",
                chunk_id="s1::chunk::1",
                text="hello chunk",
                metadata={"rowid": 1},
                score=0.9,
                retrieval_strategy="keyword",
                score_raw=0.9,
                score_normalized=1.0,
                source_type="text",
            )
        ]

    with patch("rag.retriever.retrieve", fake_retrieve), patch(
        "retrieval.semantic_retriever.rank_by_semantic",
        side_effect=RuntimeError("no st"),
    ):
        from retrieval.hybrid_pipeline import hybrid_search

        chunks = hybrid_search("hello", top_k=2)
    assert len(chunks) >= 1
    # V14 R1：返回 RetrievedChunk，不再是 dict
    assert isinstance(chunks[0], RetrievedChunk)
    assert chunks[0].text == "hello chunk"
    # 回落时 retrieval_strategy 含 fts_fallback
    assert "fts_fallback" in chunks[0].retrieval_strategy
