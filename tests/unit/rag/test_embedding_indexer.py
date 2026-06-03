"""embedding_indexer upsert path (mock ST, no network)."""

from __future__ import annotations

from unittest.mock import patch

from tests._support.pg_fixtures import pg_required_marks

pytestmark = pg_required_marks()


def test_index_embeddings_for_source_upserts(pg_settings: None) -> None:  # noqa: ARG001
    from rag.indexing import embedding_indexer
    from retrieval import embedding_store
    from storage import pg_pool

    source_id = "unit-test-embed-source"
    with pg_pool.get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rag_embeddings WHERE rowid IN (SELECT id FROM rag_chunks WHERE source_id = %s);", (source_id,))
            cur.execute("DELETE FROM rag_chunk_meta WHERE source_id = %s;", (source_id,))
            cur.execute("DELETE FROM rag_chunks WHERE source_id = %s;", (source_id,))
        conn.commit()

    from rag import ingest

    ingest.ingest_text("PostgreSQL 是默认数据库。", source_id=source_id, source_type="text", title="t")

    def _fake_encode(texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    with patch.object(embedding_indexer, "_encode_texts", side_effect=_fake_encode):
        n = embedding_indexer.index_embeddings_for_source(source_id, limit=10)

    assert n >= 1
    from rag import pg_chunks

    chunk_rows = pg_chunks.fetch_chunks_by_source_pg(source_id, limit=5)
    assert chunk_rows
    rid = int(chunk_rows[0][0])
    got = embedding_store.fetch_map([rid])
    assert rid in got
    assert len(got[rid]) == 3

    with pg_pool.get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rag_embeddings WHERE rowid IN (SELECT id FROM rag_chunks WHERE source_id = %s);", (source_id,))
            cur.execute("DELETE FROM rag_chunk_meta WHERE source_id = %s;", (source_id,))
            cur.execute("DELETE FROM rag_chunks WHERE source_id = %s;", (source_id,))
        conn.commit()
