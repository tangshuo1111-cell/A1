"""RAG 检索：PostgreSQL tsvector + GIN 索引；空结果时回退 LIKE。"""

from __future__ import annotations

import json
import re
from typing import Any

from rag.result_cleaner import sort_hits_body_before_boost
from rag.schema import RetrievedChunk

RetrievalFilters = dict[str, str]


def _query_tokens(q: str) -> list[str]:
    """中英文片段：连续中文(>=2) 或 英文词(>=2)，去重保序。"""
    parts = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9]{1,}", q)
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        low = p.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(p)
        if len(out) >= 14:
            break
    return out


def _try_ts_pg(conn: Any, q: str, top_k: int) -> list[Any]:
    from psycopg.rows import dict_row

    candidates: list[str] = []
    qn = q.strip()
    if qn:
        candidates.append(qn[:500])
    for tok in _query_tokens(q)[:8]:
        if tok and tok not in candidates:
            candidates.append(tok[:200])
    merged: list[dict[str, Any]] = []
    seen_rowids: set[int] = set()
    for expr in candidates:
        if not expr:
            continue
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id AS rowid, source_id, content,
                           ts_rank(
                               to_tsvector('simple', content),
                               plainto_tsquery('simple', %s)
                           ) AS bm
                    FROM rag_chunks
                    WHERE to_tsvector('simple', content)
                          @@ plainto_tsquery('simple', %s)
                    ORDER BY bm DESC NULLS LAST
                    LIMIT %s;
                    """,
                    (expr, expr, top_k),
                )
                got = [dict(row) for row in cur.fetchall()]
            for row in got:
                rowid = int(row["rowid"])
                if rowid in seen_rowids:
                    continue
                seen_rowids.add(rowid)
                merged.append(row)
        except Exception:  # noqa: BLE001
            continue
    if not merged:
        return []
    merged.sort(key=lambda row: float(row.get("bm") or 0.0), reverse=True)
    return merged[:top_k]


def _fallback_like_pg(conn: Any, q: str, top_k: int) -> list[Any]:
    from psycopg.rows import dict_row

    tokens = _query_tokens(q)
    if not tokens:
        tokens = [q] if q else []
    seen: set[tuple[str, str]] = set()
    out: list[Any] = []
    for tok in tokens:
        pat = f"%{tok}%"
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id AS rowid, source_id, content
                FROM rag_chunks
                WHERE content LIKE %s
                LIMIT %s;
                """,
                (pat, top_k),
            )
            for r in cur.fetchall():
                d = dict(r)
                key = (d["source_id"], d["content"])
                if key in seen:
                    continue
                seen.add(key)
                out.append(r)
                if len(out) >= top_k:
                    return out
    return out


def _enrich_with_meta_pg(
    conn: Any,
    rows: list[Any],
    strategy: str = "keyword",
    filters: RetrievalFilters | None = None,
) -> list[RetrievedChunk]:
    from psycopg.rows import dict_row

    if not rows:
        return []

    legacy_dicts: list[dict[str, Any]] = []
    for r in rows:
        row = dict(r) if not isinstance(r, dict) else r
        legacy_dicts.append(
            {
                "text": row["content"],
                "source_id": row["source_id"] or "kb",
                "rowid": int(row["rowid"]),
                "score": float(row.get("bm") or 0.0),
            }
        )

    sorted_dicts = sort_hits_body_before_boost(legacy_dicts)

    source_ids = list({d["source_id"] for d in sorted_dicts})
    meta_map: dict[str, list[dict[str, Any]]] = {}
    if source_ids:
        ph = ",".join(["%s"] * len(source_ids))
        try:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    f"""
                    SELECT chunk_id, source_id, chunk_index, source_type,
                           title, created_at, metadata_json
                    FROM rag_chunk_meta
                    WHERE source_id IN ({ph})
                    ORDER BY source_id, chunk_index ASC;
                    """,
                    source_ids,
                )
                for meta_row in cur.fetchall():
                    dd = dict(meta_row)
                    sid = str(dd["source_id"])
                    meta_map.setdefault(sid, []).append(dd)
        except Exception:  # noqa: BLE001
            pass

    all_scores = [float(d["score"]) for d in sorted_dicts]
    max_score = max(all_scores, default=1.0) or 1.0

    per_source_body_idx: dict[str, int] = {}
    chunks: list[RetrievedChunk] = []
    for d in sorted_dicts:
        sid = d["source_id"]
        rowid = d["rowid"]
        score_raw = float(d["score"])
        text = (d.get("text") or "").strip()

        meta_list = meta_map.get(sid, [])
        meta_entry: dict[str, Any] | None = None
        if meta_list and not text.startswith("[doc_path]"):
            body_idx = per_source_body_idx.get(sid, 0)
            if 0 <= body_idx < len(meta_list):
                meta_entry = meta_list[body_idx]
            per_source_body_idx[sid] = body_idx + 1

        if meta_entry:
            chunk_id = str(meta_entry["chunk_id"])
            chunk_index = int(meta_entry["chunk_index"])
            try:
                meta_dict = json.loads(meta_entry["metadata_json"] or "{}")
            except Exception:  # noqa: BLE001
                meta_dict = {}
            meta_dict.setdefault("source_type", meta_entry.get("source_type", "text"))
            meta_dict.setdefault("title", meta_entry.get("title", sid))
            meta_dict.setdefault("created_at", meta_entry.get("created_at", ""))
            meta_dict.setdefault("chunk_index", chunk_index)
            meta_dict["rowid"] = rowid
            st = str(meta_entry.get("source_type") or meta_dict.get("source_type") or "text")
        else:
            chunk_id = f"{sid}::chunk::{rowid}"
            meta_dict = {"source_type": "text", "title": sid, "chunk_index": rowid, "rowid": rowid}
            st = "text"

        if filters:
            if filters.get("source_type") and st != filters["source_type"]:
                continue
            if filters.get("source_id") and sid != filters["source_id"]:
                continue
            filter_title = filters.get("title") or filters.get("name")
            if filter_title:
                title_val = str(meta_dict.get("title", ""))
                if filter_title.lower() not in title_val.lower():
                    continue

        score_normalized = max(0.0, min(1.0, score_raw / max_score))

        chunks.append(
            RetrievedChunk(
                source_id=sid,
                chunk_id=chunk_id,
                text=text,
                metadata=meta_dict,
                score=score_raw,
                retrieval_strategy=strategy,
                score_raw=score_raw,
                score_normalized=score_normalized,
                source_type=st,
            )
        )
    return chunks


def retrieve(
    query: str,
    top_k: int = 5,
    *,
    filters: RetrievalFilters | None = None,
) -> list[RetrievedChunk]:
    """RAG 关键词检索：tsvector 优先，LIKE 兜底。"""
    q = query.strip()
    if not q:
        return []

    pool_k = top_k * 3 if filters else top_k
    from storage.pg_pool import get_pool

    with get_pool().connection() as conn:
        rows = _try_ts_pg(conn, q, pool_k)
        if not rows:
            rows = _fallback_like_pg(conn, q, pool_k)
        result = _enrich_with_meta_pg(conn, rows, strategy="keyword", filters=filters)
        return result[:top_k]
