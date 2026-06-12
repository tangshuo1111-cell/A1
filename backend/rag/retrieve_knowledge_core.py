"""
PG-only since 2026-05-09，注释中的 SQLite/FTS5 表述为历史遗留。

retrieve_knowledge 内部实现：strategy 分发、分数收口、source_all、embedding 探测。

对外入口与完整设计说明见同目录 `retrieve_knowledge.py`（薄门面）。
"""

from __future__ import annotations

import logging

from rag.retriever import retrieve as _retrieve_keyword
from rag.schema import RetrievedChunk

logger = logging.getLogger("light_maqa")

# 低置信阈值（score_normalized 低于此值视为 low_confidence）
LOW_CONFIDENCE_THRESHOLD: float = 0.15

# auto 策略：最少需要多少条有 embedding 的 chunk 才走 hybrid（否则降 keyword）
AUTO_MIN_EMBEDDING_COVERAGE: int = 1
DEFAULT_SOURCE_POLICY_POOL_MULTIPLIER: int = 4


def _should_exclude_default_source(
    chunk: RetrievedChunk,
    filters: dict[str, str],
) -> bool:
    """默认检索策略下排除明显的机器工件 source。

    规则：
    - 若调用方显式指定 source_id，则尊重调用方，不做默认排除。
    - 对自然语言问答主路，默认排除 benchmark scored-json 这类机器评测工件，
      避免其因为“与题目措辞高度重合”而持续污染 top hit。
    """
    if (filters or {}).get("source_id"):
        return False
    source_id = str(getattr(chunk, "source_id", "") or "")
    return source_id.startswith("benchmark:") and source_id.endswith(":scored-json")


def _apply_default_source_policy(
    chunks: list[RetrievedChunk],
    filters: dict[str, str],
) -> tuple[list[RetrievedChunk], int]:
    if not chunks:
        return chunks, 0
    kept: list[RetrievedChunk] = []
    excluded = 0
    for chunk in chunks:
        if _should_exclude_default_source(chunk, filters):
            excluded += 1
            continue
        kept.append(chunk)
    return kept, excluded


def _expanded_top_k_for_default_policy(
    top_k: int,
    filters: dict[str, str],
) -> int:
    """默认 source policy 生效时，扩大候选池，避免排除 scored-json 后直接空结果。"""
    if (filters or {}).get("source_id"):
        return top_k
    return max(top_k, top_k * DEFAULT_SOURCE_POLICY_POOL_MULTIPLIER)


def _dispatch(
    *,
    query: str,
    top_k: int,
    strategy: str,
    filters: dict[str, str],
    embedding_enabled: bool,
) -> tuple[list[RetrievedChunk], str, str]:
    """根据 strategy 分发到具体检索实现。

    返回 (chunks, strategy_used, auto_reason)。
    """
    if strategy == "keyword":
        chunks = _do_keyword(query, top_k, filters)
        chunks, excluded = _apply_default_source_policy(chunks, filters)
        reason = "default source policy excluded benchmark scored-json" if excluded else ""
        return chunks, "keyword", reason

    if strategy == "semantic":
        if not embedding_enabled:
            chunks = _do_keyword(query, top_k, filters)
            return chunks, "keyword:embedding_disabled", "semantic 降级：EMBEDDING_ENABLED=0"
        chunks = _do_semantic(query, _expanded_top_k_for_default_policy(top_k, filters))
        # filter 在 _dispatch 层统一应用（保证 mock _do_semantic 时 filter 仍生效）
        if filters:
            chunks = _apply_filters(chunks, filters)
        chunks, excluded = _apply_default_source_policy(chunks, filters)
        reason = "default source policy excluded benchmark scored-json" if excluded else ""
        return chunks[:top_k], "semantic", reason

    if strategy == "hybrid":
        if not embedding_enabled:
            chunks = _do_keyword(query, top_k, filters)
            return chunks, "keyword:embedding_disabled", "hybrid 降级：EMBEDDING_ENABLED=0"
        chunks = _do_hybrid(query, _expanded_top_k_for_default_policy(top_k, filters))
        # filter 在 _dispatch 层统一应用（保证 mock _do_hybrid 时 filter 仍生效）
        if filters:
            chunks = _apply_filters(chunks, filters)
        chunks, excluded = _apply_default_source_policy(chunks, filters)
        reason = "default source policy excluded benchmark scored-json" if excluded else ""
        return chunks[:top_k], "hybrid", reason

    if strategy == "auto":
        return _auto_dispatch(query, top_k, filters, embedding_enabled)

    if strategy == "source_all":
        # source_all 策略：按 source_id 全量拉取该 source 的所有 chunk。
        # 专用于 V8 锚点追问场景，替代旧的 fetch_knowledge_chunks_by_source_id 直接调用。
        # 语义：不是相关性排序，而是"给我这个 source 下的全部内容"。
        # 必须在 filters 中提供 source_id；缺失时**禁止**静默降级 keyword（V15 收口）。
        source_id_val = (filters or {}).get("source_id", "").strip()
        if not source_id_val:
            logger.warning("source_all 策略缺少 source_id filter，返回空结果（不降级 keyword）")
            return [], "source_all", "source_all 缺少 filters.source_id，禁止降级 keyword"
        chunks = _do_source_all(source_id_val)
        return chunks, "source_all", ""

    # 未知 strategy → 降 keyword
    logger.warning("retrieve_knowledge 未知 strategy=%r，降级 keyword", strategy)
    chunks = _do_keyword(query, top_k, filters)
    return chunks, f"keyword:unknown_strategy:{strategy}", f"未知 strategy: {strategy}"


def _auto_dispatch(
    query: str,
    top_k: int,
    filters: dict[str, str],
    embedding_enabled: bool,
) -> tuple[list[RetrievedChunk], str, str]:
    """auto 策略（完整三路选路，可解释）：

    选路规则：
    1. embedding 未启用 → keyword（最快，无 ST 依赖）
    2. embedding 启用且有 embedding 数据 → hybrid（最完整）
       - hybrid 失败 → semantic（去掉 FTS 权重）
       - semantic 也失败 → keyword（安全降级）
    3. embedding 启用但无 embedding 数据 → keyword

    每步选路原因均写入 auto_reason，trace 可见。
    """
    if not embedding_enabled:
        chunks = _do_keyword(query, top_k, filters)
        return chunks, "auto:keyword", "auto 选路：EMBEDDING_ENABLED=0，使用 keyword（原因：无 embedding 支持）"

    has_embeddings = _check_has_embeddings()
    if not has_embeddings:
        chunks = _do_keyword(query, top_k, filters)
        return chunks, "auto:keyword", "auto 选路：rag_embeddings 表无数据，使用 keyword（原因：无可用向量）"

    # 优先 hybrid（FTS + 语义联合）
    try:
        chunks = _do_hybrid(query, _expanded_top_k_for_default_policy(top_k, filters))
        if filters:
            chunks = _apply_filters(chunks, filters)
        chunks, excluded = _apply_default_source_policy(chunks, filters)
        chunks = chunks[:top_k]
        if chunks:
            return (
                chunks,
                "auto:hybrid",
                f"auto 选路：有 embedding 数据（≥{AUTO_MIN_EMBEDDING_COVERAGE}条），使用 hybrid"
                f"（FTS 权重 alpha={0.45}，语义权重 {0.55}）；跳过 keyword（仅 FTS）和 semantic（仅语义）",
            ) if not excluded else (
                chunks,
                "auto:hybrid",
                f"auto 选路：有 embedding 数据（≥{AUTO_MIN_EMBEDDING_COVERAGE}条），使用 hybrid"
                f"（FTS 权重 alpha={0.45}，语义权重 {0.55}）；跳过 keyword（仅 FTS）和 semantic（仅语义）；"
                f"默认排除了 {excluded} 个 benchmark scored-json 命中",
            )
    except (OSError, ValueError, RuntimeError, ImportError) as e:
        logger.warning("auto hybrid failed, fallback semantic: %s", e)

    # hybrid 失败或无结果 → 尝试 semantic
    try:
        chunks = _do_semantic(query, _expanded_top_k_for_default_policy(top_k, filters))
        if filters:
            chunks = _apply_filters(chunks, filters)
        chunks, excluded = _apply_default_source_policy(chunks, filters)
        chunks = chunks[:top_k]
        if chunks:
            return (
                chunks,
                "auto:semantic",
                "auto 选路：hybrid 失败/无结果，降级 semantic（原因：hybrid 异常或无候选）；跳过 keyword（已有语义支持）",
            ) if not excluded else (
                chunks,
                "auto:semantic",
                f"auto 选路：hybrid 失败/无结果，降级 semantic（原因：hybrid 异常或无候选）；跳过 keyword（已有语义支持）；"
                f"默认排除了 {excluded} 个 benchmark scored-json 命中",
            )
    except (OSError, ValueError, RuntimeError, ImportError) as e:
        logger.warning("auto semantic also failed, fallback keyword: %s", e)

    # 最终降级 keyword
    chunks = _do_keyword(query, top_k, filters)
    chunks, excluded = _apply_default_source_policy(chunks, filters)
    return (
        chunks,
        "auto:keyword:hybrid_and_semantic_failed",
        "auto 选路：hybrid 和 semantic 均失败，使用 keyword 安全降级"
        + (f"；默认排除了 {excluded} 个 benchmark scored-json 命中" if excluded else ""),
    )


def _do_keyword(
    query: str,
    top_k: int,
    filters: dict[str, str],
) -> list[RetrievedChunk]:
    """keyword 策略：FTS5 关键词检索，filters 在 _enrich_with_meta 中生效。

    返回的 RetrievedChunk 中：
    - score_keyword = score_normalized（FTS 归一化分）
    - score_semantic = 0.0
    - combined_score = score_keyword
    """
    from config.settings import settings

    if settings.use_tfidf_rerank:
        from rag.hybrid_retrieve import hybrid_retrieve
        chunks = hybrid_retrieve(query, top_k=top_k, use_tfidf_rerank=True)
        chunks = _apply_filters(chunks, filters)
        chunks = _finalize_keyword_scores(chunks)
    else:
        chunks = _retrieve_keyword(query, top_k=top_k, filters=filters or None)
        # keyword 路径：填充 score_keyword/combined_score
        chunks = _finalize_keyword_scores(chunks)

    return chunks


def _do_semantic(
    query: str,
    top_k: int,
) -> list[RetrievedChunk]:
    """semantic 策略：FTS 宽池 + sentence-transformer 语义重排。

    不含 filter 逻辑（filter 在 _dispatch 层统一应用）。
    返回的 RetrievedChunk 中：
    - score_keyword = FTS 归一化分（候选依据，不参与排序）
    - score_semantic = ST 余弦（排序主分）
    - combined_score = score_semantic
    """
    from retrieval.hybrid_pipeline import hybrid_search
    chunks = hybrid_search(query, top_k=top_k * 3, mode="semantic")
    # 对 semantic 结果填充 combined_score = score_semantic
    chunks = _finalize_semantic_scores(chunks)
    return chunks


def _do_hybrid(
    query: str,
    top_k: int,
) -> list[RetrievedChunk]:
    """hybrid 策略：FTS + 语义向量混合重排。

    不含 filter 逻辑（filter 在 _dispatch 层统一应用）。
    combined_score = alpha * score_keyword + (1-alpha) * score_semantic
    返回的 RetrievedChunk 中：
    - score_keyword = FTS 归一化分
    - score_semantic = ST 余弦
    - combined_score = alpha*score_kw + (1-alpha)*score_sem
    """
    from retrieval.hybrid_pipeline import hybrid_search
    chunks = hybrid_search(query, top_k=top_k * 3, mode="hybrid")
    return chunks


def _finalize_keyword_scores(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """keyword 路径：确保 score_keyword/combined_score 与 score_normalized 一致。"""
    from dataclasses import replace
    result = []
    for c in chunks:
        kw = c.score_normalized if c.score_normalized > 0 else (
            max(0.0, min(1.0, abs(c.score_raw))) if c.score_raw else 0.0
        )
        result.append(replace(
            c,
            score_keyword=kw,
            score_semantic=0.0,
            combined_score=kw,
            retrieval_strategy="keyword",
        ))
    return result


def _finalize_semantic_scores(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """semantic 路径：确保 combined_score = score_semantic。"""
    from dataclasses import replace
    result = []
    for c in chunks:
        sem = c.score_semantic if c.score_semantic > 0 else c.score_normalized
        result.append(replace(
            c,
            combined_score=sem,
            score_normalized=sem,
            retrieval_strategy="semantic",
        ))
    return result


def _apply_filters(
    chunks: list[RetrievedChunk],
    filters: dict[str, str],
) -> list[RetrievedChunk]:
    """对 RetrievedChunk 列表做 post-filter（用于 semantic / hybrid 路径）。

    filter 键：source_type / source_id / title / name
    与 keyword 路径的 _enrich_with_meta filter 逻辑保持一致。
    hybrid 路径必须经过此函数，不得绕开。
    """
    if not filters:
        return chunks
    result = []
    for c in chunks:
        if filters.get("source_type"):
            st = c.source_type or c.metadata.get("source_type", "")
            if st != filters["source_type"]:
                continue
        if filters.get("source_id") and c.source_id != filters["source_id"]:
            continue
        filter_title = filters.get("title") or filters.get("name")
        if filter_title:
            title_val = str(c.metadata.get("title", ""))
            if filter_title.lower() not in title_val.lower():
                continue
        result.append(c)
    return result


def _renormalize(chunks: list[RetrievedChunk], strategy: str) -> list[RetrievedChunk]:
    """重新计算 score_normalized（filter 后 max 可能变化）。"""
    if not chunks:
        return chunks
    max_score = max(c.score_raw for c in chunks) or 1.0
    from dataclasses import replace
    result = []
    for c in chunks:
        norm = max(0.0, min(1.0, c.score_raw / max_score))
        result.append(replace(c, score_normalized=norm, retrieval_strategy=strategy))
    return result


def _do_source_all(source_id: str) -> list[RetrievedChunk]:
    """source_all 策略：按 source_id 全量拉取该 source 下的所有已入库 chunk。

    专用于 V8 锚点追问场景，替代旧的 fetch_knowledge_chunks_by_source_id 直接调用。
    通过 FTS5 UNINDEXED source_id 字段精确匹配（全表扫描，量小时可接受），
    同时从 rag_chunk_meta 表补充元数据（chunk_id / source_type）。
    上限由 SOURCE_ALL_LIMIT 控制（默认 50），超出时 metadata 中标注 source_all_truncated=True。

    返回 list[RetrievedChunk]（空 = source 不存在或未入库）。
    每个 chunk 的 score 固定为 1.0（精确匹配，无需排序）。
    """
    from config.settings import settings
    if not settings.enable_rag:
        return []

    SOURCE_ALL_LIMIT = 50

    from rag.store import init_schema

    init_schema()
    chunks_out: list[RetrievedChunk] = []

    raw_rows: list[tuple[int, str, str]] = []
    meta_map: dict[int, dict] = {}
    type_map: dict[int, str] = {}
    id_map: dict[int, str] = {}

    try:
        from rag import pg_chunks
        from storage.pg_pool import get_pool

        get_pool()
        raw_rows = pg_chunks.fetch_chunks_by_source_pg(
            source_id, SOURCE_ALL_LIMIT + 1
        )
        ml = pg_chunks.fetch_meta_for_sources_pg([source_id]).get(source_id, [])
        ml_sorted = sorted(ml, key=lambda x: int(x["chunk_index"]))
        import json as _json2

        for idx, mr in enumerate(ml_sorted):
            mj = mr.get("metadata_json") or "{}"
            try:
                meta_map[idx] = _json2.loads(mj) if mj else {}
            except (ValueError, TypeError):
                meta_map[idx] = {}
            type_map[idx] = str(mr.get("source_type") or "")
            id_map[idx] = str(mr.get("chunk_id") or "")
    except (OSError, RuntimeError):
        return []

    truncated = len(raw_rows) > SOURCE_ALL_LIMIT
    raw_rows = raw_rows[:SOURCE_ALL_LIMIT]

    for idx, (rowid, sid, content) in enumerate(raw_rows):
        meta_data = meta_map.get(idx, {}).copy()
        if truncated:
            meta_data["source_all_truncated"] = True
            meta_data["source_all_limit"] = SOURCE_ALL_LIMIT
        chunk_id_v = id_map.get(idx) or f"{sid}::chunk::{rowid}"
        src_type_v = type_map.get(idx, "")
        chunks_out.append(
            RetrievedChunk(
                source_id=sid or source_id,
                chunk_id=chunk_id_v,
                text=content or "",
                metadata=meta_data,
                score=1.0,
                score_keyword=1.0,
                score_semantic=0.0,
                combined_score=1.0,
                source_type=src_type_v,
            )
        )
    return chunks_out


def _check_has_embeddings() -> bool:
    """快速检查 rag_embeddings 表是否有数据（auto 策略选路用）。"""
    try:
        from retrieval.embedding_store import ensure_table
        from storage.pg_pool import get_pool

        ensure_table()
        pool = get_pool()
        with pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM rag_embeddings;")
            row = cur.fetchone()
        return bool(row and int(row[0]) >= AUTO_MIN_EMBEDDING_COVERAGE)
    except (OSError, RuntimeError, ImportError):
        return False
