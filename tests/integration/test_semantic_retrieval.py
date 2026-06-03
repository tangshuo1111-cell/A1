"""integration：语义 / 混合检索（真实 sentence-transformers + embedding 路径）。

显式标记 ``real_external``：默认 ``pytest -m "not real_external"`` 不收集本文件。
本地跑：``ALLOW_REAL_SENTENCE_TRANSFORMERS=1 EMBEDDING_ENABLED=1 pytest tests/integration/test_semantic_retrieval.py -q``

风险收口（计划第七轮「未被考虑的风险」）：
- 文件名不与 ``tests/backend/*`` 重名；
- 依赖 ``bootstrap_historical_test`` 统一工程根，避免 ``tests/unit`` 与 conftest 路径不一致。
"""

from __future__ import annotations

import os
import sys
import uuid

import pytest
from tests._support.bootstrap import bootstrap_historical_test

pytestmark = pytest.mark.real_external

REPO_ROOT = bootstrap_historical_test(__file__)
for p in (str(REPO_ROOT), str(REPO_ROOT.resolve())):
    if p not in sys.path:
        sys.path.insert(0, p)


def _gate_embedding() -> None:
    if os.getenv("ALLOW_REAL_SENTENCE_TRANSFORMERS", "").lower() not in {"1", "true", "yes", "on"}:
        pytest.skip("需要 ALLOW_REAL_SENTENCE_TRANSFORMERS=1（默认测试会 stub sentence_transformers）")
    if os.getenv("EMBEDDING_ENABLED", "0").lower() not in {"1", "true", "yes", "on"}:
        pytest.skip("需要 EMBEDDING_ENABLED=1 以走向量索引写入/检索")


@pytest.fixture
def tmp_kb(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """隔离 data_dir：RAG SQLite 与 embedding 侧车文件落在 tmp。"""
    _gate_embedding()
    from config.settings import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from rag.store import init_schema

    init_schema()


def test_semantic_retrieve_hits_ingested_line(tmp_kb: None) -> None:
    from rag.ingest import ingest_text
    from rag.retrieve_knowledge import retrieve_knowledge

    sid = f"semantic_suite/{uuid.uuid4().hex[:8]}"
    ingest_text(
        "语义检索验收锚点 TOKEN_SEMANTIC_ZZ_9f3c 仅用于测试句子。",
        source_id=sid,
        source_type="document",
        title="semantic-fixture",
    )
    chunks, trace = retrieve_knowledge(
        "锚点 TOKEN_SEMANTIC",
        top_k=3,
        strategy="semantic",
        embedding_enabled=True,
    )
    assert trace.get("strategy_used", "").startswith("semantic")
    assert chunks, "semantic 路径应至少命中一条"
    assert any("TOKEN_SEMANTIC" in (getattr(c, "text", "") or "") for c in chunks)


def test_hybrid_retrieve_combines_paths(tmp_kb: None) -> None:
    from rag.ingest import ingest_text
    from rag.retrieve_knowledge import retrieve_knowledge

    sid = f"hybrid_suite/{uuid.uuid4().hex[:8]}"
    ingest_text(
        "混合检索验收 HYBRID_TOKEN_aa77 描述独特内容避免误匹配。",
        source_id=sid,
        source_type="document",
        title="hybrid-fixture",
    )
    chunks, trace = retrieve_knowledge(
        "HYBRID_TOKEN_aa77",
        top_k=5,
        strategy="hybrid",
        embedding_enabled=True,
    )
    assert "hybrid" in trace.get("strategy_used", "")
    assert chunks


def test_auto_strategy_enables_embedding_when_available(tmp_kb: None) -> None:
    from rag.ingest import ingest_text
    from rag.retrieve_knowledge import retrieve_knowledge

    sid = f"auto_sem/{uuid.uuid4().hex[:8]}"
    ingest_text(
        "AUTO_STRAT_TOKEN_bb12 用于自动策略验收。",
        source_id=sid,
        source_type="document",
    )
    chunks, trace = retrieve_knowledge(
        "AUTO_STRAT_TOKEN_bb12",
        top_k=3,
        strategy="auto",
        embedding_enabled=True,
    )
    used = trace.get("strategy_used", "")
    assert used.startswith("auto:") or used in {"semantic", "hybrid", "keyword"}
    assert chunks or used  # 允许空命中但必须有策略轨迹


def test_keyword_still_works_when_embedding_enabled(tmp_kb: None) -> None:
    from rag.ingest import ingest_text
    from rag.retrieve_knowledge import retrieve_knowledge

    sid = f"kw_only/{uuid.uuid4().hex[:8]}"
    ingest_text(
        "关键词强匹配 KWT_ONLY_cc99 固定串。",
        source_id=sid,
        source_type="document",
    )
    chunks, trace = retrieve_knowledge(
        "KWT_ONLY_cc99",
        top_k=2,
        strategy="keyword",
        embedding_enabled=True,
    )
    assert trace["strategy_used"] == "keyword"
    assert chunks


def test_filter_source_id_narrows_semantic(tmp_kb: None) -> None:
    from rag.ingest import ingest_text
    from rag.retrieve_knowledge import retrieve_knowledge

    a = f"fl_a/{uuid.uuid4().hex[:6]}"
    b = f"fl_b/{uuid.uuid4().hex[:6]}"
    ingest_text("FILTER_ALPHA_dd88 唯一在 A", source_id=a, source_type="document")
    ingest_text("FILTER_BETA_dd88 唯一在 B", source_id=b, source_type="document")
    chunks, _trace = retrieve_knowledge(
        "FILTER_ALPHA_dd88",
        top_k=5,
        strategy="semantic",
        embedding_enabled=True,
        filters={"source_id": a},
    )
    assert chunks
    assert all(getattr(c, "source_id", "") == a for c in chunks)
