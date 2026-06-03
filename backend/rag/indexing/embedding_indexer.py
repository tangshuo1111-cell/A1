"""Write rag_embeddings rows aligned with rag_chunks.id (PG-only)."""

from __future__ import annotations

import logging

from config.settings import settings
from rag import pg_chunks
from retrieval import embedding_store

logger = logging.getLogger(__name__)


def _encode_texts(texts: list[str]) -> list[list[float]]:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(settings.embedding_model_name)
    emb = model.encode(
        texts,
        batch_size=16,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return [row.tolist() for row in emb]


def index_embeddings_for_source(source_id: str, *, limit: int = 500) -> int:
    """Encode and upsert embeddings for all chunks of ``source_id``. Returns upsert count."""
    rows = pg_chunks.fetch_chunks_by_source_pg(source_id, limit=limit)
    if not rows:
        return 0
    rowids = [int(r[0]) for r in rows]
    texts = [str(r[2]) for r in rows]
    try:
        vectors = _encode_texts(texts)
    except Exception as exc:  # noqa: BLE001 - encode 失败不应阻断 ingest，降级跳过
        logger.warning("embedding_indexer encode failed source_id=%s: %s", source_id, exc)
        return 0
    n = 0
    for rid, vec in zip(rowids, vectors, strict=True):
        embedding_store.upsert(rid, vec)
        n += 1
    return n


def backfill_all_chunks(*, batch_size: int = 16) -> int:
    """Offline backfill: all rag_chunks rows. Used by scripts/build_embeddings.py."""
    from storage.pg_pool import get_pool

    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, content FROM rag_chunks ORDER BY id ASC;")
        rows = list(cur.fetchall())
    if not rows:
        return 0
    texts = [str(r[1]) for r in rows]
    rowids = [int(r[0]) for r in rows]
    total = 0
    for i in range(0, len(rowids), batch_size):
        batch_ids = rowids[i : i + batch_size]
        batch_texts = texts[i : i + batch_size]
        vectors = _encode_texts(batch_texts)
        for rid, vec in zip(batch_ids, vectors, strict=True):
            embedding_store.upsert(rid, vec)
            total += 1
    return total
