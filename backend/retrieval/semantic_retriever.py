"""
PG-only since 2026-05-09，注释中的 SQLite/FTS5 表述为历史遗留。

语义打分与重排（retrieval / 语义子层）。

依赖 sentence-transformers（可选）；不可用时由 hybrid_pipeline 捕获并回落。
输入 FTS 候选行（含 rowid、text、score_fts）与 embedding_store 向量表；
输出按 hybrid/semantic 模式重排。

V14 R2 更新：
- alpha 参数化（默认 0.45，可由调用方传入）
- 明确 combined_score 公式：
    mode=semantic : combined_score = score_semantic（不含 FTS 权重）
    mode=hybrid   : combined_score = alpha * score_fts_normalized + (1-alpha) * score_semantic
                    其中 alpha=0.45（FTS 关键词权重），(1-alpha)=0.55（语义权重）
                    注意：score_fts_normalized = max(0, min(1, score_fts)) 是归一化到 0-1 的 FTS 分
    mode=keyword  : combined_score = score_fts_normalized（score_semantic=0）
- 输出新增 score_keyword / score_semantic 字段（对应 RetrievedChunk V14 R2 字段）

分数可比性边界说明：
- 同一策略内（如两条都是 hybrid 结果）combined_score 可比较
- 不同策略间（keyword combined_score vs semantic combined_score）**不可直接比较**
- FTS BM25 分数为负值（SQLite bm25() 特性），score_fts_normalized 做 max(0, min(1, abs(score_fts)/max_abs)) 归一
- 旧数据无向量（方案 C）：score_semantic = 0，combined_score 在 hybrid 模式退化为 alpha * score_fts_normalized

与 knowledge_store.search、LangGraph collect（经 middle→RAG）间接协作；
answer_agent 仍只读 Evidence 文本。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

logger = logging.getLogger("light_maqa")

# V14 R2：hybrid combined_score 公式权重（FTS vs semantic）
HYBRID_ALPHA: float = 0.45  # FTS 权重；semantic 权重 = 1 - HYBRID_ALPHA = 0.55


@lru_cache(maxsize=1)
def _get_sentence_transformer(model_name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def warmup_semantic_runtime() -> None:
    """Warm the semantic model into process memory.

    Used by API startup / local benchmarks so the first KB query does not pay
    the entire model-load cost inside the request budget.
    """
    from config.settings import settings

    _get_sentence_transformer(settings.embedding_model_name)


def rank_by_semantic(
    query: str,
    rows: list[dict[str, Any]],
    vec_map: dict[int, list[float]],
    *,
    mode: str,
    alpha: float = HYBRID_ALPHA,
) -> list[dict[str, Any]]:
    """对 FTS 候选行做语义/混合重排。

    combined_score 公式（V14 R2 明确）：
    - mode=semantic : combined_score = score_semantic
    - mode=hybrid   : combined_score = alpha * score_fts_n + (1-alpha) * score_semantic
                      alpha=0.45（FTS 关键词权重），1-alpha=0.55（语义向量权重）
                      score_fts_n = max(0, min(1, fts_abs_normalized))
    - mode=keyword  : combined_score = score_fts_n（score_semantic=0）

    旧数据方案 C（无向量）：score_semantic=0，hybrid 退化为 alpha*score_fts_n。

    输出行新增字段：
    - score_keyword   : FTS 归一化分（0-1）
    - score_semantic  : ST 余弦相似度（0-1，无向量时为 0.0）
    - combined_score  : 最终排序用分数
    - score_hybrid    : 同 combined_score（保持旧字段兼容）
    - retrieval_mode  : {mode}_st
    """
    try:
        import numpy as np

        from config.settings import settings

        model = _get_sentence_transformer(settings.embedding_model_name)
    except Exception as e:  # noqa: BLE001
        logger.warning("semantic rank unavailable: %s", e)
        raise

    qv = model.encode(query, normalize_embeddings=True)
    qvn = np.asarray(qv, dtype=np.float32).reshape(-1)

    # 计算 FTS 分数的绝对最大值用于归一化（BM25 为负，取绝对值做 max 归一化）
    fts_scores_raw = [float(r.get("score_fts", 0.0)) for r in rows]
    max_fts_abs = max((abs(s) for s in fts_scores_raw), default=1.0) or 1.0

    sems: list[float | None] = []
    for i, r in enumerate(rows):  # noqa: B007
        rid = r.get("rowid")
        if rid is not None and int(rid) in vec_map:
            dv = np.array(vec_map[int(rid)], dtype=np.float32).reshape(-1)
            sems.append(
                float(
                    np.dot(qvn, dv)
                    / (np.linalg.norm(qvn) * np.linalg.norm(dv) + 1e-9)
                )
            )
        else:
            sems.append(None)

    # 旧数据（无向量，方案 C）：on-the-fly encode 兜底
    need_idx = [i for i, s in enumerate(sems) if s is None]
    if need_idx:
        batch = [rows[i].get("text", "")[:2000] for i in need_idx]
        enc = model.encode(batch, normalize_embeddings=True)
        for j, i in enumerate(need_idx):
            dv = np.asarray(enc[j], dtype=np.float32).reshape(-1)
            sems[i] = float(
                np.dot(qvn, dv)
                / (np.linalg.norm(qvn) * np.linalg.norm(dv) + 1e-9)
            )

    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows):
        sem_v = float(sems[i] if sems[i] is not None else 0.0)
        fts_raw = float(r.get("score_fts", 0.0))
        # FTS 归一化：BM25 为负值，取绝对值再 max 归一化
        fts_n = max(0.0, min(1.0, abs(fts_raw) / max_fts_abs))

        # combined_score 公式（V14 R2 明确）
        if mode == "semantic":
            combined = sem_v
        elif mode == "hybrid":
            combined = alpha * fts_n + (1.0 - alpha) * max(0.0, sem_v)
        else:
            combined = fts_n

        row = dict(r)
        row["score_keyword"] = fts_n          # FTS 归一化分（V14 R2）
        row["score_semantic"] = sem_v          # ST 余弦（V14 R2）
        row["combined_score"] = combined       # 最终排序分（V14 R2）
        row["score_hybrid"] = combined         # 旧字段兼容
        row["retrieval_mode"] = f"{mode}_st"
        out.append(row)

    out.sort(key=lambda x: -float(x.get("combined_score", 0.0)))
    return out
