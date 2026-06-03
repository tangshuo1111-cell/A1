"""
PG-only since 2026-05-09，注释中的 SQLite/FTS5 表述为历史遗留。

可插拔检索管线：FTS5 宽召回 + 可选 TF-IDF 重排（轻量「深度」升级，无向量库）。

V12 R2 变更：
- 直接调 retrieve()（返回 list[RetrievedChunk]），移除旧 retrieve_as_legacy_dicts 调用
- _tfidf_rerank 改为接受 list[RetrievedChunk] 输入，操作 chunk.text
- 消除了 RetrievedChunk → dict → RetrievedChunk 的双重转换
- retrieve_as_legacy_dicts 已完全退场

层级：rag / retrieval — 供 knowledge_store、middle_agent 间接使用。

策略：
1) baseline：原 retriever.retrieve 同等 FTS 宽池（top_k * pool_mult）
2) upgrade：若 sklearn 可用且配置开启，对候选做 query–doc TF-IDF 余弦重排
3) fallback：重排失败或未安装 sklearn 时退回 FTS 顺序截断

chunk：沿用 rag_chunks 行级块；metadata：source_id + score_fts / score_tfidf（若有）。
"""

from __future__ import annotations

import logging
from dataclasses import replace

from rag.result_cleaner import demote_boost_preserve_order_chunks
from rag.schema import RetrievedChunk

logger = logging.getLogger("light_maqa")


def _tfidf_rerank(
    query: str,
    chunks: list[RetrievedChunk],
    top_k: int,
) -> list[RetrievedChunk]:
    """TF-IDF 余弦重排，直接操作 RetrievedChunk，不再转换为 dict。"""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        logger.warning("sklearn 未安装，跳过 TF-IDF 重排")
        return chunks[:top_k]

    if not chunks or not query.strip():
        return chunks[:top_k]

    texts = [c.text for c in chunks]
    try:
        vec = TfidfVectorizer(max_features=4096, ngram_range=(1, 2))
        mat = vec.fit_transform([query] + texts)
        sims = cosine_similarity(mat[0:1], mat[1:]).flatten()
    except Exception as e:  # noqa: BLE001
        logger.warning("TF-IDF 重排失败，使用 FTS 顺序: %s", e)
        return chunks[:top_k]

    scored = sorted(
        zip(chunks, sims, strict=False),
        key=lambda x: float(x[1]),
        reverse=True,
    )
    out: list[RetrievedChunk] = []
    for c, s in scored[:top_k]:
        # 更新 score 为 tfidf 分值，metadata 中也记录
        new_meta = dict(c.metadata)
        new_meta["score_tfidf"] = float(s)
        out.append(
            replace(c, score=float(s), metadata=new_meta)
        )
    return out


def hybrid_retrieve(
    query: str,
    top_k: int = 5,
    *,
    pool_mult: int = 4,
    use_tfidf_rerank: bool = True,
) -> list[RetrievedChunk]:
    """
    混合检索入口。返回 list[RetrievedChunk]（V12 统一出口）。

    V12 R2：直接调 retrieve()，不再经过旧 retrieve_as_legacy_dicts 中转。
    """
    from config.settings import settings
    from rag.retriever import retrieve

    pool = max(top_k, top_k * max(1, pool_mult))
    raw: list[RetrievedChunk] = retrieve(query, top_k=pool)

    if not settings.use_tfidf_rerank or not use_tfidf_rerank:
        slim = demote_boost_preserve_order_chunks(raw, top_k)
        strategy = "fts_only"
        return [replace(c, retrieval_strategy=strategy) for c in slim]

    reranked = _tfidf_rerank(query, raw, top_k)
    slim = demote_boost_preserve_order_chunks(reranked, top_k)
    strategy = "fts_tfidf_rerank"
    return [replace(c, retrieval_strategy=strategy) for c in slim]
