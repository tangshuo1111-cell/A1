"""Retriever metadata enrichment for user_committed provenance."""

from __future__ import annotations

from rag.retrieval_provenance import SOURCE_KIND_USER_COMMITTED, count_user_committed_hits
from rag.retriever import _enrich_with_meta_pg


class _FakeConn:
    pass


def test_enrich_maps_metadata_json_by_body_order_not_global_rowid() -> None:
    rows = [
        {"rowid": 99, "source_id": "metrics_sandbox/demo.md", "content": "[doc_path] boost", "bm": 0.2},
        {"rowid": 100, "source_id": "metrics_sandbox/demo.md", "content": "body with token", "bm": 0.9},
    ]

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params):  # noqa: ARG002
            self._sql = sql

        def fetchall(self):
            if "rag_chunk_meta" in self._sql:
                return [
                    {
                        "chunk_id": "metrics_sandbox/demo.md::chunk::0",
                        "source_id": "metrics_sandbox/demo.md",
                        "chunk_index": 0,
                        "source_type": "text_file",
                        "title": "demo",
                        "created_at": "2026-06-22T00:00:00",
                        "metadata_json": '{"source_kind":"user_committed","chunk_index":0}',
                    }
                ]
            return []

    class Conn:
        def cursor(self, *, row_factory=None):  # noqa: ARG002
            return Cursor()

    chunks = _enrich_with_meta_pg(Conn(), rows, strategy="keyword")
    assert len(chunks) == 2
    assert count_user_committed_hits(chunks) == 1
    body = next(c for c in chunks if "body with token" in c.text)
    assert body.metadata.get("source_kind") == SOURCE_KIND_USER_COMMITTED
