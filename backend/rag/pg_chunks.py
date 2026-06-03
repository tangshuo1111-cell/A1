"""PostgreSQL 上的 RAG chunk 读写（与 SQLite 行为对齐，检索用语义级 tsvector）。"""

from __future__ import annotations

import json
from typing import Any

from psycopg.rows import dict_row

from storage.pg_pool import get_pool


def ingest_text_pg(
    *,
    source_id: str = "inline",
    source_type: str = "text",
    title: str = "",
    created_at: str = "",
    extra_metadata: dict[str, Any] | None = None,
    parts: list[str],
    base_meta: dict[str, Any],
) -> int:
    """由 ``ingest.ingest_text`` 准备好 ``parts`` / ``base_meta`` 后写入 PG。"""
    pool = get_pool()
    n = 0
    chunk_index = 0
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rag_chunks WHERE source_id = %s;", (source_id,))
            cur.execute("DELETE FROM rag_chunk_meta WHERE source_id = %s;", (source_id,))
            for i, p in enumerate(parts):
                cur.execute(
                    "INSERT INTO rag_chunks (source_id, content) VALUES (%s, %s);",
                    (source_id, p),
                )
                is_boost = i == 0 and len(parts) > 1
                if not is_boost:
                    chunk_id = f"{source_id}::chunk::{chunk_index}"
                    meta: dict[str, Any] = dict(base_meta)
                    meta["chunk_index"] = chunk_index
                    cur.execute(
                        """
                        INSERT INTO rag_chunk_meta
                            (chunk_id, source_id, chunk_index, source_type,
                             title, created_at, metadata_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                        """,
                        (
                            chunk_id,
                            source_id,
                            chunk_index,
                            source_type,
                            title or source_id,
                            created_at,
                            json.dumps(meta, ensure_ascii=False),
                        ),
                    )
                    chunk_index += 1
                n += 1
        conn.commit()
    if n > 0:
        from config.feature_flags import embed_on_commit_active

        if embed_on_commit_active():
            from rag.indexing.embedding_indexer import index_embeddings_for_source

            index_embeddings_for_source(source_id)
    return n


def count_chunks_pg() -> int:
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM rag_chunks;")
        row = cur.fetchone()
        return int(row[0]) if row else 0


def list_stored_source_ids_pg(limit: int) -> list[str]:
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT source_id FROM rag_chunks LIMIT %s;",
            (int(limit),),
        )
        return [str(r[0]) for r in cur.fetchall() if r and r[0]]


def fetch_chunks_by_source_pg(source_id: str, limit: int) -> list[tuple[int, str, str]]:
    pool = get_pool()
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
                SELECT id AS rowid, source_id, content
                FROM rag_chunks
                WHERE source_id = %s
                ORDER BY id ASC
                LIMIT %s;
                """,
            (source_id, limit),
        )
        out: list[tuple[int, str, str]] = []
        for r in cur.fetchall():
            d = dict(r)
            out.append((int(d["rowid"]), str(d["source_id"]), str(d["content"])))
        return out


def fetch_meta_for_sources_pg(source_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not source_ids:
        return {}
    pool = get_pool()
    meta_map: dict[str, list[dict[str, Any]]] = {}
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
                SELECT chunk_id, source_id, chunk_index, source_type,
                       title, created_at, metadata_json
                FROM rag_chunk_meta
                WHERE source_id = ANY(%s)
                ORDER BY source_id, chunk_index ASC;
                """,
            (source_ids,),
        )
        for row in cur.fetchall():
            d = dict(row)
            sid = str(d["source_id"])
            meta_map.setdefault(sid, []).append(d)
    return meta_map
