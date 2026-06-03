"""
PG-only since 2026-05-09，注释中的 SQLite/FTS5 表述为历史遗留。

V14 R1/R2：统一检索主入口 retrieve_knowledge(...)。

设计原则：
- 这是所有检索策略的唯一对外入口（对 Middle / service 层）
- 内部按 strategy 分发到 keyword / semantic / hybrid / auto 实现
- filter 在此层统一生效（keyword / semantic / hybrid 路径均支持）
- 返回统一 list[RetrievedChunk]（含 V14 R2 完整分数字段）
- 默认主路径（Middle→KB）唯一通过此入口检索

支持的 strategy：
- "keyword" : FTS5 关键词检索（+ 可选 TF-IDF 重排）
- "semantic" : sentence-transformer 语义向量检索
              （仅对有 embedding 的 chunk 生效；旧数据按方案 C 处理）
- "hybrid"   : FTS5 关键词 + 语义向量混合检索
              combined_score = alpha * score_keyword + (1-alpha) * score_semantic
              alpha=0.45（FTS 权重），1-alpha=0.55（语义权重）
              旧数据无向量时（方案 C）：score_semantic=0，退化为 alpha*score_keyword
- "auto"     : V14 R2 完整三路选路（可解释，trace 可见）：
              有 embedding 数据 → hybrid；embedding 不可用 → keyword；
              hybrid 失败 → semantic；semantic 也失败 → keyword

Embedding 旧数据处理策略（方案 C）：
- semantic / hybrid / auto 检索时，对无向量 chunk 做 on-the-fly encode（sentence-transformers）
- 这意味着旧数据可以参与语义检索，但延迟较高
- 有向量（rag_embeddings 表）的 chunk 直接用预存向量（更快）
- 旧知识库数据可通过 scripts/build_embeddings.py 离线回填以提升性能
- R1/R2 不做 ingest 时强制 encode，保持 ingest 路径简洁

Filter 生效范围：
- source_type / source_id / title 均在 _apply_filters 中统一生效
- keyword 路径：通过 retriever.retrieve(filters=...) 在 SQL 后 post-filter
- semantic 路径：hybrid_pipeline 返回后 _apply_filters post-filter
- hybrid 路径：hybrid_pipeline 返回后 _apply_filters post-filter（不被合并流程绕开）
- 三种策略 filter 逻辑一致，不存在"某策略无 filter"问题

Score 口径（V14 R2 完整定义）：
- score_keyword     : FTS/BM25 分数 max 归一化（0-1）；keyword 路径下等于 score_normalized
- score_semantic    : sentence-transformer 余弦相似度（0-1）；无向量时为 on-the-fly 编码结果
- combined_score    : hybrid 合并分数；formula: alpha*score_keyword + (1-alpha)*score_semantic
                      keyword 路径：combined_score = score_keyword（score_semantic=0）
                      semantic 路径：combined_score = score_semantic（score_keyword=0）
                      hybrid 路径：combined_score = alpha*score_kw + (1-alpha)*score_sem
- score_raw         : 原始分数（BM25 原始值/余弦）
- score_normalized  : combined_score 再做一次最大值归一化（0-1）
- score             : 同 combined_score（V12 兼容）
- retrieval_strategy: keyword / semantic / hybrid / auto:keyword / auto:semantic / auto:hybrid

分数跨策略可比性边界（重要）：
- 同策略内两条 chunk 的 combined_score 可比
- 不同策略间（如 keyword combined_score vs semantic combined_score）**不可直接比较**
  因为 FTS BM25 和 ST 余弦量纲不同，合并公式也不同

no_match 处理：
- retrieve_knowledge 返回空列表时，调用方（Middle/Answer）应视为 no_match
- low_confidence: 所有 chunk 的 score_normalized < LOW_CONFIDENCE_THRESHOLD 时视为低置信

多来源统一检索边界说明：
- text / text_file / web_url / local_video / web_video 均可进入统一策略层
- 本轮统一的是"检索策略层"，**不是**承诺各来源文本质量/metadata质量/semantic效果同厚度优化
- 不同来源的文本化质量（视频ASR vs 网页正文 vs 手工录入文本）存在自然差异
- 这些差异体现在检索结果质量，但不影响策略层的统一性

实现细节见 `retrieve_knowledge_core.py`。
"""

from __future__ import annotations

import logging
from typing import Any

from rag.schema import RetrievedChunk

from . import retrieve_knowledge_core as _rk_core

AUTO_MIN_EMBEDDING_COVERAGE = _rk_core.AUTO_MIN_EMBEDDING_COVERAGE
LOW_CONFIDENCE_THRESHOLD = _rk_core.LOW_CONFIDENCE_THRESHOLD

logger = logging.getLogger("light_maqa")


def retrieve_knowledge(
    query: str,
    *,
    top_k: int = 5,
    strategy: str = "auto",
    filters: dict[str, str] | None = None,
    embedding_enabled: bool | None = None,
) -> tuple[list[RetrievedChunk], dict[str, Any]]:
    """统一检索主入口。

    参数：
    - query           : 检索问题
    - top_k           : 返回 chunk 数量上限（自动 clamp 到 COST.rag_max_top_k）
    - strategy        : "keyword" / "semantic" / "hybrid" / "auto"
    - filters         : dict，支持 source_type / source_id / title / name
    - embedding_enabled: 强制覆盖设置（测试用）；None 时从 config.settings 读

    返回：
    - chunks : list[RetrievedChunk]（空列表 = no_match）
    - trace  : dict，包含检索过程关键信息（strategy_requested/strategy_used/auto_reason/
               filter/score_max/no_match/low_confidence/score_info）
    """
    from config.cost_rule import COST
    from config.settings import settings

    top_k = min(top_k, COST.rag_max_top_k)
    _emb_enabled = embedding_enabled if embedding_enabled is not None else settings.embedding_enabled

    strategy_requested = strategy.strip().lower()
    trace_info: dict[str, Any] = {
        "strategy_requested": strategy_requested,
        "strategy_used": "",
        "auto_reason": "",
        "filter": filters or {},
        "top_k": top_k,
        "hits": 0,
        "no_match": False,
        "low_confidence": False,
        "score_max_normalized": 0.0,
        "score_max_keyword": 0.0,
        "score_max_semantic": 0.0,
        "score_max_combined": 0.0,
        "alpha": 0.0,
        "default_source_policy": "exclude_benchmark_scored_json",
        "default_source_excluded": 0,
    }

    try:
        chunks, strategy_used, auto_reason = _rk_core._dispatch(
            query=query,
            top_k=top_k,
            strategy=strategy_requested,
            filters=filters or {},
            embedding_enabled=_emb_enabled,
        )
    except (OSError, ValueError, RuntimeError, ImportError) as e:
        logger.warning("retrieve_knowledge failed strategy=%s err=%s", strategy, e)
        chunks = []
        strategy_used = f"{strategy_requested}:exception"
        auto_reason = str(e)[:80]

    trace_info["strategy_used"] = strategy_used
    trace_info["auto_reason"] = auto_reason
    if "默认排除了 " in auto_reason and " 个 benchmark scored-json 命中" in auto_reason:
        try:
            trace_info["default_source_excluded"] = int(
                auto_reason.split("默认排除了 ", 1)[1].split(" 个 benchmark scored-json 命中", 1)[0]
            )
        except (ValueError, IndexError):
            trace_info["default_source_excluded"] = 0
    trace_info["hits"] = len(chunks)
    trace_info["no_match"] = len(chunks) == 0
    trace_info["filters_applied"] = filters or {}
    if strategy_requested == "source_all" and not ((filters or {}).get("source_id") or "").strip():
        trace_info["failure_reason"] = "source_all_missing_source_id"
        trace_info["no_match"] = True

    if chunks:
        max_norm = max(c.score_normalized for c in chunks)
        max_kw = max(c.score_keyword for c in chunks)
        max_sem = max(c.score_semantic for c in chunks)
        max_comb = max(c.combined_score for c in chunks)
        trace_info["score_max_normalized"] = round(max_norm, 4)
        trace_info["score_max_keyword"] = round(max_kw, 4)
        trace_info["score_max_semantic"] = round(max_sem, 4)
        trace_info["score_max_combined"] = round(max_comb, 4)
        trace_info["low_confidence"] = (
            False if strategy_used == "source_all" else max_norm < LOW_CONFIDENCE_THRESHOLD
        )
        if strategy_used == "source_all":
            trace_info["chunk_id_preview"] = [c.chunk_id for c in chunks[:3]]
            trace_info["source_all_truncated"] = any(
                c.metadata.get("source_all_truncated") for c in chunks
            )
    else:
        trace_info["low_confidence"] = False

    if "hybrid" in strategy_used:
        from retrieval.semantic_retriever import HYBRID_ALPHA

        trace_info["alpha"] = HYBRID_ALPHA

    return chunks, trace_info
