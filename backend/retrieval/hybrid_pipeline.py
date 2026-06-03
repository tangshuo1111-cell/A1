"""
内部检索混合管线（retrieval 编排层）。

keyword：走原 FTS（经 retriever）；
semantic/hybrid：在 FTS 宽池上做向量重排（可选）。

V14 R1 修复：
- 修复 retriever.retrieve() 返回 RetrievedChunk 而非 dict，hybrid_pipeline 之前
  错误地对 RetrievedChunk 调用 .setdefault()（dict 方法）导致 AttributeError。
- 现在 hybrid_pipeline 统一返回 list[RetrievedChunk]（V14 统一出口）。

V14 R2 升级：
- 把 score_keyword / score_semantic / combined_score 写入 RetrievedChunk
- 使用 semantic_retriever.HYBRID_ALPHA 作为混合权重（公式明确写在 semantic_retriever.py）
- combined_score 公式：
    hybrid : alpha * score_keyword + (1-alpha) * score_semantic（alpha=0.45）
    semantic : combined_score = score_semantic
    keyword : combined_score = score_keyword（score_semantic=0）
- filter 在 retrieve_knowledge 层由 _apply_filters 统一处理，hybrid_search 不负责 filter

依赖缺失或异常时自动退回 FTS 截断，不抛到上层。
由 retrieve_knowledge 按 strategy 调用；
与 rag.hybrid_retrieve（TF-IDF）可并存。
embedding 开启且 mode 为 semantic/hybrid 时本模块优先于 TF-IDF。
"""

from __future__ import annotations

import logging
from typing import Any

from rag.schema import RetrievedChunk
from retrieval.semantic_retriever import HYBRID_ALPHA

logger = logging.getLogger("light_maqa")


def hybrid_search(
    query: str,
    top_k: int = 5,
    *,
    mode: str = "semantic",
    alpha: float = HYBRID_ALPHA,
) -> list[RetrievedChunk]:
    """在 FTS 宽池基础上做语义/混合重排，返回统一 RetrievedChunk 列表。

    V14 R1：
    - 参数新增 mode（semantic/hybrid），由 retrieve_knowledge 传入
    - 返回 list[RetrievedChunk]（不再返回 dict）

    V14 R2：
    - 新增 alpha 参数（hybrid 权重，默认 HYBRID_ALPHA=0.45）
    - RetrievedChunk 填充 score_keyword / score_semantic / combined_score
    - combined_score 与 semantic_retriever 公式一致

    filter 不在此处处理（由 retrieve_knowledge._apply_filters 统一处理）。
    """
    from config.settings import settings
    from rag import retriever

    pool = max(top_k, top_k * max(1, settings.rag_fts_pool_mult))
    chunks: list[RetrievedChunk] = retriever.retrieve(query, top_k=pool)
    if not chunks:
        return []

    # FTS 分数 max 归一化（BM25 为负，取绝对值）
    fts_scores = [abs(c.score) for c in chunks]
    max_fts = max(fts_scores, default=1.0) or 1.0

    if not settings.embedding_enabled:
        # embedding 未启用：纯 keyword 模式
        result = []
        for c in chunks[:top_k]:
            kw_norm = max(0.0, min(1.0, abs(c.score) / max_fts))
            result.append(
                RetrievedChunk(
                    source_id=c.source_id,
                    chunk_id=c.chunk_id,
                    text=c.text,
                    metadata=c.metadata,
                    score=kw_norm,
                    retrieval_strategy="keyword",
                    score_raw=c.score,
                    score_normalized=kw_norm,
                    source_type=c.source_type,
                    score_keyword=kw_norm,
                    score_semantic=0.0,
                    combined_score=kw_norm,
                )
            )
        return result

    try:
        from retrieval.embedding_store import ensure_table, fetch_map
        from retrieval.semantic_retriever import rank_by_semantic

        ensure_table()
        # 构造 dict 列表供 semantic_retriever（需要 rowid/text/score_fts）
        rows: list[dict[str, Any]] = []
        for i, c in enumerate(chunks):
            row: dict[str, Any] = {
                "source_id": c.source_id,
                "chunk_id": c.chunk_id,
                "text": c.text,
                "metadata": c.metadata,
                "source_type": c.source_type,
                "score_fts": c.score,
            }
            # rowid 从 metadata 取（ingest 时写入）
            rowid = c.metadata.get("rowid") or c.metadata.get("chunk_index") or i
            row["rowid"] = rowid
            rows.append(row)

        rowids = [int(r["rowid"]) for r in rows if r.get("rowid") is not None]
        vm = fetch_map(rowids)
        ranked_rows = rank_by_semantic(query, rows, vm, mode=mode, alpha=alpha)

        # 计算 combined_score 归一化（已在 rank_by_semantic 中计算，这里做最终截断）
        combined_scores = [float(r.get("combined_score", 0.0)) for r in ranked_rows]
        max_combined = max(combined_scores, default=1.0) or 1.0

        result = []
        for r in ranked_rows[:top_k]:
            score_kw = float(r.get("score_keyword", 0.0))
            score_sem = float(r.get("score_semantic", 0.0))
            combined = float(r.get("combined_score", 0.0))
            score_norm = combined / max_combined if max_combined > 0 else 0.0

            result.append(
                RetrievedChunk(
                    source_id=r.get("source_id", ""),
                    chunk_id=r.get("chunk_id", ""),
                    text=r.get("text", ""),
                    metadata=r.get("metadata", {}),
                    score=combined,
                    retrieval_strategy=mode,
                    score_raw=float(r.get("score_fts", 0.0)),
                    score_normalized=score_norm,
                    source_type=r.get("source_type", ""),
                    score_keyword=score_kw,
                    score_semantic=score_sem,
                    combined_score=combined,
                )
            )
        return result

    except Exception as e:  # noqa: BLE001
        logger.warning("hybrid_pipeline semantic failed, fts fallback: %s", e)
        # 回退 keyword
        result = []
        for c in chunks[:top_k]:
            kw_norm = max(0.0, min(1.0, abs(c.score) / max_fts))
            result.append(
                RetrievedChunk(
                    source_id=c.source_id,
                    chunk_id=c.chunk_id,
                    text=c.text,
                    metadata=c.metadata,
                    score=kw_norm,
                    retrieval_strategy="keyword:fts_fallback",
                    score_raw=c.score,
                    score_normalized=kw_norm,
                    source_type=c.source_type,
                    score_keyword=kw_norm,
                    score_semantic=0.0,
                    combined_score=kw_norm,
                )
            )
        return result


def _normalize_fts_scores(scores: list[float], score: float) -> float:
    """把 FTS/BM25 分数归一化到 0-1（max 归一化，取绝对值）。"""
    max_s = max((abs(s) for s in scores), default=1.0) or 1.0
    return max(0.0, min(1.0, abs(score) / max_s))
