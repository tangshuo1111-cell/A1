"""Embedding PG 路径：BYTEA 写入后 ``fetch_map`` 能读回（第一轮步骤 3.5 闭环）。"""

from __future__ import annotations

from tests._support.pg_fixtures import pg_required_marks

pytestmark = pg_required_marks()


def test_embedding_upsert_and_fetch_map_roundtrip(pg_settings: None) -> None:  # noqa: ARG001
    from retrieval import embedding_store
    from storage import pg_pool

    rowid = 9_876_543_210_001
    vec = [0.25, -0.5, 0.0, 0.125]
    try:
        embedding_store.upsert(rowid, vec)
        got = embedding_store.fetch_map([rowid])
        assert rowid in got
        assert len(got[rowid]) == len(vec)
        for a, b in zip(vec, got[rowid], strict=True):
            assert abs(a - b) < 1e-6
    finally:
        with pg_pool.get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM rag_embeddings WHERE rowid = %s;", (rowid,))
            conn.commit()
