"""Chunk 向量落库（PostgreSQL 唯一后端）。

与 ``rag_chunks.id``（BIGINT rowid）对齐。
表 ``rag_embeddings(rowid, dim, vec BYTEA)``，写入见 ``upsert()``，批量读见 ``fetch_map()``。
"""

from __future__ import annotations

import struct


def ensure_table() -> None:
    from storage.pg_pool import get_pool

    get_pool()


def pack_vec(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def unpack_vec(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _blob_to_bytes(blob: object) -> bytes:
    if isinstance(blob, memoryview):
        return blob.tobytes()
    if isinstance(blob, bytes):
        return blob
    return bytes(blob)


def upsert(rowid: int, vector: list[float]) -> None:
    ensure_table()
    from storage.pg_pool import get_pool

    pool = get_pool()
    blob = pack_vec(vector)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rag_embeddings (rowid, dim, vec) VALUES (%s, %s, %s)
                ON CONFLICT (rowid) DO UPDATE SET
                    dim = EXCLUDED.dim,
                    vec = EXCLUDED.vec;
                """,
                (rowid, len(vector), blob),
            )
        conn.commit()


def fetch_map(rowids: list[int]) -> dict[int, list[float]]:
    if not rowids:
        return {}
    ensure_table()
    from storage.pg_pool import get_pool

    pool = get_pool()
    ph = ",".join(["%s"] * len(rowids))
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT rowid, vec FROM rag_embeddings WHERE rowid IN ({ph});",
            rowids,
        )
        rows = cur.fetchall()
    return {int(r[0]): unpack_vec(_blob_to_bytes(r[1])) for r in rows}


def list_missing_rowids(all_rowids: list[int]) -> list[int]:
    if not all_rowids:
        return []
    m = fetch_map(all_rowids)
    return [r for r in all_rowids if r not in m]
