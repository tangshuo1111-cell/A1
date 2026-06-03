"""PostgreSQL 主链 RAG 检索验收测试。

验收目标：
1. 构造知识材料 → 写入 PG rag_chunks + rag_chunk_meta
2. retrieve_knowledge 关键词检索 → 命中 → 字段完整
3. RetrievedChunk 字段校验（source_id / chunk_id / metadata / score / combined_score）
4. to_context_line 可被 Answer 消费
5. 不走旧 SQLite 路径（无 _db_path / sqlite / FTS5 依赖）
"""

from __future__ import annotations

import uuid

import pytest
from tests._support.pg_fixtures import pg_required_marks

pytestmark = [*pg_required_marks(), pytest.mark.acceptance]


SAMPLE_SOURCE_TYPE = "text"
SAMPLE_TITLE = "PG验收样本"

SAMPLE_TEXT = (
    "# LightMultiAgentQA 核心架构\n\n"
    "LightMultiAgentQA 采用三层 Agent 协作架构，由 MainAgent 负责路由，"
    "MiddleAgent 收集证据材料，AnswerAgent 生成最终回答。\n\n"
    "系统支持多种知识来源：文本、文档（docx/xlsx/pdf）、网页、视频字幕等，"
    "统一通过 RAG 检索接口 retrieve_knowledge 进行关键词、语义或混合检索。\n\n"
    "所有业务数据存储在 PostgreSQL 中，使用 tsvector + GIN 索引进行全文检索，"
    "彻底替代了历史版本的 SQLite FTS5 方案。"
)

# 用于 retrieve 的精准关键词（保证在 SAMPLE_TEXT 中唯一出现）
UNIQUE_KEYWORD = "LightMultiAgentQA"


@pytest.fixture()
def ingested_source(pg_settings) -> str:  # noqa: ARG001 — pg_settings 初始化连接池
    """写入一份测试知识材料并返回 source_id；测试结束后清理。"""
    from rag import ingest
    from storage.pg_pool import get_pool

    sid = f"pg_acceptance_{uuid.uuid4().hex[:8]}"
    n = ingest.ingest_text(
        SAMPLE_TEXT,
        source_id=sid,
        source_type=SAMPLE_SOURCE_TYPE,
        title=SAMPLE_TITLE,
    )
    assert n >= 2, f"ingest 应写入 ≥2 块（boost header + body chunks），实际 {n}"
    yield sid
    pool = get_pool()
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM rag_chunks WHERE source_id = %s;", (sid,))
        cur.execute("DELETE FROM rag_chunk_meta WHERE source_id = %s;", (sid,))
        conn.commit()


# ── 1. ingest + keyword retrieve 基本链路 ──────────────────────────────


def test_retrieve_keyword_hits_ingested_material(ingested_source: str) -> None:
    """retrieve_knowledge(keyword) 应命中刚写入的知识材料。"""
    from rag.retrieve_knowledge import retrieve_knowledge

    chunks, trace = retrieve_knowledge(
        UNIQUE_KEYWORD, top_k=5, strategy="keyword",
    )
    assert len(chunks) >= 1, f"keyword 检索应命中至少 1 条，实际 {len(chunks)}"
    assert trace["strategy_used"] == "keyword"
    assert trace["no_match"] is False

    hit = next((c for c in chunks if c.source_id == ingested_source), None)
    assert hit is not None, f"应命中 source_id={ingested_source}，实际命中的 source_id 列表：{[c.source_id for c in chunks]}"


# ── 2. RetrievedChunk 字段完整性 ───────────────────────────────────────


def test_chunk_fields_completeness(ingested_source: str) -> None:
    """RetrievedChunk 应包含 source_id / chunk_id / metadata / score / combined_score。"""
    from rag.retrieve_knowledge import retrieve_knowledge

    chunks, _ = retrieve_knowledge(UNIQUE_KEYWORD, top_k=5, strategy="keyword")
    hit = next((c for c in chunks if c.source_id == ingested_source), None)
    assert hit is not None

    assert hit.source_id == ingested_source
    assert hit.chunk_id, "chunk_id 不应为空"
    assert "::" in hit.chunk_id, f"chunk_id 应包含 '::' 分隔符，实际 {hit.chunk_id}"
    assert isinstance(hit.metadata, dict)
    assert hit.metadata.get("source_type") == SAMPLE_SOURCE_TYPE
    assert hit.metadata.get("title") in (SAMPLE_TITLE, ingested_source)

    assert hit.score >= 0, "score 应非负"
    assert hit.score_raw >= 0, "score_raw 应非负"
    assert 0 <= hit.score_normalized <= 1, f"score_normalized 应 ∈ [0,1]，实际 {hit.score_normalized}"
    assert hit.combined_score >= 0, "combined_score 应非负"
    assert hit.score_keyword >= 0, "score_keyword 应非负"
    assert hit.retrieval_strategy == "keyword"


# ── 3. to_context_line 输出可被 Answer 消费 ────────────────────────────


def test_to_context_line_consumable(ingested_source: str) -> None:
    """to_context_line() 应输出包含 source_id 和正文的可读文本，供 Answer prompt 拼接。"""
    from rag.retrieve_knowledge import retrieve_knowledge

    chunks, _ = retrieve_knowledge(UNIQUE_KEYWORD, top_k=5, strategy="keyword")
    hit = next((c for c in chunks if c.source_id == ingested_source), None)
    assert hit is not None

    ctx = hit.to_context_line()
    assert ingested_source in ctx, "context_line 应包含 source_id"
    assert hit.chunk_id in ctx, "context_line 应包含 chunk_id"
    assert len(ctx) > 20, "context_line 不应过短"


# ── 4. source_all 策略按 source_id 全量拉取 ────────────────────────────


def test_source_all_retrieves_all_chunks(ingested_source: str) -> None:
    """source_all 策略应返回该 source_id 下的所有 chunk（含 boost header）。"""
    from rag.retrieve_knowledge import retrieve_knowledge

    chunks, trace = retrieve_knowledge(
        "", top_k=50, strategy="source_all",
        filters={"source_id": ingested_source},
    )
    assert len(chunks) >= 2, f"source_all 应返回 ≥2 块（boost+body），实际 {len(chunks)}"
    assert all(c.source_id == ingested_source for c in chunks)
    assert trace["strategy_used"] == "source_all"


# ── 5. filter 按 source_id 精确过滤 ────────────────────────────────────


def test_filter_by_source_id(ingested_source: str) -> None:
    """keyword 检索 + filters={source_id} 应仅返回该 source。"""
    from rag.retrieve_knowledge import retrieve_knowledge

    chunks, _ = retrieve_knowledge(
        UNIQUE_KEYWORD, top_k=10, strategy="keyword",
        filters={"source_id": ingested_source},
    )
    assert len(chunks) >= 1
    assert all(c.source_id == ingested_source for c in chunks)


# ── 6. rag_chunk_meta 元数据一致性 ──────────────────────────────────────


def test_pg_chunk_meta_consistency(ingested_source: str) -> None:
    """rag_chunk_meta 中 source_type / title 应与 ingest 参数一致。"""
    from rag.pg_chunks import fetch_meta_for_sources_pg

    meta_map = fetch_meta_for_sources_pg([ingested_source])
    meta_list = meta_map.get(ingested_source, [])
    assert len(meta_list) >= 1, "rag_chunk_meta 应有至少 1 条记录"
    for entry in meta_list:
        assert entry["source_type"] == SAMPLE_SOURCE_TYPE
        assert entry["title"] in (SAMPLE_TITLE, ingested_source)
        assert entry["chunk_id"].startswith(ingested_source)


# ── 7. material bundle 模拟：retrieved_chunks 可组装知识块 ──────────────


def test_material_bundle_knowledge_block(ingested_source: str) -> None:
    """模拟 Middle retrieval_flow：retrieved_chunks → knowledge_block 拼接可用。"""
    from rag.retrieve_knowledge import retrieve_knowledge

    chunks, trace = retrieve_knowledge(UNIQUE_KEYWORD, top_k=5, strategy="keyword")
    hits = [c for c in chunks if c.source_id == ingested_source]
    assert hits

    knowledge_block = "\n\n---\n\n".join(c.to_context_line() for c in hits)
    assert UNIQUE_KEYWORD in knowledge_block or "三层" in knowledge_block
    assert len(knowledge_block) > 30


# ── 8. 确认不走 SQLite 路径 ─────────────────────────────────────────────


def test_no_sqlite_path_used(pg_settings, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ARG001
    """确认 retrieve 和 ingest 不调用任何 SQLite 相关函数或路径。"""
    import rag.retriever as _retriever_mod

    sqlite_called = []

    def _trap(*args, **kwargs):
        sqlite_called.append(("sqlite_call", args, kwargs))
        raise AssertionError("不应调用 SQLite 路径")

    for attr in ("_try_fts5", "_fallback_like", "_sqlite_retrieve"):
        if hasattr(_retriever_mod, attr):
            monkeypatch.setattr(_retriever_mod, attr, _trap)

    from rag.retrieve_knowledge import retrieve_knowledge

    chunks, _ = retrieve_knowledge(UNIQUE_KEYWORD, top_k=3, strategy="keyword")
    assert not sqlite_called, "不应有 SQLite 函数被调用"
    assert isinstance(chunks, list)


# ── 9. auto 策略（embedding 未启用时降级 keyword） ──────────────────────


def test_auto_strategy_degrades_to_keyword(ingested_source: str) -> None:
    """EMBEDDING_ENABLED=0 时 auto 应降级为 keyword 且仍能命中。"""
    from rag.retrieve_knowledge import retrieve_knowledge

    chunks, trace = retrieve_knowledge(
        UNIQUE_KEYWORD, top_k=5, strategy="auto", embedding_enabled=False,
    )
    assert "keyword" in trace["strategy_used"], f"auto 应降级 keyword，实际 {trace['strategy_used']}"
    hit = next((c for c in chunks if c.source_id == ingested_source), None)
    assert hit is not None
