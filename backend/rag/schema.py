"""
V12 统一 retrieval result 出口 schema。

V14 R1 升级：
- 新增 score_raw（原始分数，来自 BM25/TF-IDF/余弦）
- 新增 score_normalized（0-1 归一化，由 retrieve_knowledge 统一计算）
- 新增 source_type（便于 filter / trace 不必再拆 metadata）

V14 R2 升级：
- 新增 score_keyword（FTS/BM25 关键词分数，已归一化到 0-1）
- 新增 score_semantic（sentence-transformer 余弦相似度，已在 0-1）
- 新增 combined_score（hybrid 合并分数；keyword/semantic 时与 score_normalized 相同）

上层消费方（Main / Middle / Answer / service / trace）统一使用本模块的
RetrievedChunk，不再直接依赖底层 rowid / source / text 旧口径。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RetrievedChunk:
    """V12/V14 标准 retrieval result 单元。

    字段说明：
    - source_id         : 入库时指定的资料标识符，如 ``knowledge_samples/sample.md``
    - chunk_id          : 本 chunk 在该 source 内的唯一标识，格式 ``{source_id}::chunk::{index}``
    - text              : chunk 正文（不含 boost header 等内部标记）
    - metadata          : 随 chunk 携带的结构化元信息，至少含 source_type / title /
                          chunk_index / created_at（来自 rag_chunks 表或 ingest 注入）
    - score             : 综合检索分数（V14 兼容字段，同 combined_score）
    - retrieval_strategy: 实际使用的检索策略标签，如
                          ``keyword`` / ``semantic`` / ``hybrid`` /
                          ``auto:keyword`` / ``auto:semantic`` / ``auto:hybrid``
    - score_raw         : V14 R1 新增；原始评分，来自 FTS BM25 / TF-IDF 余弦 / ST 余弦
    - score_normalized  : V14 R1 新增；0-1 归一化分数，由 retrieve_knowledge 统一计算
    - source_type       : V14 R1 新增；来源类型（text/text_file/web_url/local_video/web_video）；
                          为空时从 metadata["source_type"] 取

    V14 R2 新增分数字段（有默认值，保持向后兼容）：
    - score_keyword     : FTS/BM25 关键词分数（已 max 归一化到 0-1）；keyword 路径下等于 score_normalized
    - score_semantic    : sentence-transformer 余弦相似度（0-1）；无向量时为 0.0（方案 C）
    - combined_score    : hybrid 合并分数；公式：alpha * score_keyword + (1-alpha) * score_semantic
                          其中 alpha=0.45（FTS 权重）
                          keyword 路径：combined_score = score_keyword（score_semantic=0）
                          semantic 路径：combined_score = score_semantic（score_keyword=0）
                          hybrid 路径：combined_score = alpha*score_keyword + (1-alpha)*score_semantic
                          注意：跨策略的 combined_score 不可直接比较（不同策略分数来源不同）

    兼容说明：
    - score 字段保留（V12 消费方仍可直接用）；V14 新消费方优先用 combined_score
    - retrieval_strategy 从 V12 的 ``fts`` 迁移到 V14 的 ``keyword`` 语义，兼容旧值
    - score_keyword / score_semantic / combined_score 默认值均为 0.0，不破坏现有代码
    """

    source_id: str
    chunk_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    retrieval_strategy: str = "keyword"

    # V14 R1 新增字段（有默认值，保持向后兼容）
    score_raw: float = 0.0
    score_normalized: float = 0.0
    source_type: str = ""

    # V14 R2 新增字段（有默认值，保持向后兼容）
    score_keyword: float = 0.0    # FTS/BM25 关键词分数（max 归一化 0-1）
    score_semantic: float = 0.0   # ST 余弦相似度（0-1，无向量时为 0.0）
    combined_score: float = 0.0   # hybrid 合并分数（alpha*kw + (1-alpha)*sem）

    # ------------------------------------------------------------------ #
    #  工厂方法                                                             #
    # ------------------------------------------------------------------ #
    @classmethod
    def from_legacy_row(
        cls,
        row: dict[str, Any],
        *,
        strategy: str = "keyword",
    ) -> RetrievedChunk:
        """从旧口径 dict（rowid / source / text 或 source_id / content）转换。

        V12 统一转换层：确保下游不再直接吃旧字段。
        V14 R1：填充 score_raw / score_normalized / source_type。
        V14 R2：填充 score_keyword / score_semantic / combined_score。
        """
        source_id = (
            row.get("source_id") or row.get("source") or "unknown"
        )
        text = (row.get("text") or row.get("content") or "").strip()
        rowid = row.get("rowid")
        chunk_index = row.get("chunk_index", 0)
        chunk_id = (
            row.get("chunk_id")
            or f"{source_id}::chunk::{chunk_index if chunk_index else rowid or 0}"
        )
        # score_raw：从各来源取原始分数
        score_raw = float(
            row.get("score_semantic")
            or row.get("score_hybrid")
            or row.get("score")
            or row.get("score_tfidf")
            or row.get("score_fts")
            or 0.0
        )
        score_normalized = float(row.get("score_normalized", score_raw))
        score = score_raw

        metadata: dict[str, Any] = dict(row.get("metadata") or {})
        if "retrieval_mode" in row:
            metadata.setdefault("retrieval_mode", row["retrieval_mode"])
        if "chunk_index" in row:
            metadata.setdefault("chunk_index", row["chunk_index"])

        source_type = (
            row.get("source_type")
            or metadata.get("source_type")
            or ""
        )

        # V14 R2 分数字段
        score_keyword = float(row.get("score_keyword", 0.0))
        score_semantic = float(row.get("score_semantic", 0.0))
        combined_score = float(row.get("combined_score", score_raw))

        return cls(
            source_id=source_id,
            chunk_id=chunk_id,
            text=text,
            metadata=metadata,
            score=score,
            retrieval_strategy=strategy,
            score_raw=score_raw,
            score_normalized=score_normalized,
            source_type=source_type,
            score_keyword=score_keyword,
            score_semantic=score_semantic,
            combined_score=combined_score,
        )

    def to_context_line(self) -> str:
        """转成可塞进 prompt 的单行材料文本。"""
        return f"来源「{self.source_id}」（chunk: {self.chunk_id}）：\n{self.text}"
