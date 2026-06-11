"""
历史归档：V14 SQLite 单文件知识库时代的检索验收与相关断言。

当前主链为 **PostgreSQL + PG 检索**；本模块仍依赖已移除的 ``rag.store._db_path``、
``rag.retrieve_knowledge._do_keyword`` 等旧接口，**不作为现行验收**，仅保留考古价值。

默认 ``pytest`` 不收集 ``tests/legacy/``（见 ``pyproject.toml`` 的 ``testpaths``）。
按需手动运行：``pytest tests/legacy/test_retrieval_acceptance.py``。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from tests._support.bootstrap import bootstrap_historical_test

pytestmark = pytest.mark.legacy

REPO_ROOT = bootstrap_historical_test(__file__)
ABILITY_LAYER = REPO_ROOT
MAIN_CORE = REPO_ROOT
for p in (str(REPO_ROOT), str(ABILITY_LAYER), str(MAIN_CORE)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("ENABLE_RAG", "1")
os.environ.setdefault("EMBEDDING_ENABLED", "0")
os.environ.setdefault("RETRIEVAL_MODE", "keyword")
os.environ.setdefault("USE_TFIDF_RERANK", "0")

from services.pending_store import reset_pending_store_for_tests


@pytest.fixture(autouse=True)
def _reset_pending():
    reset_pending_store_for_tests()
    yield
    reset_pending_store_for_tests()


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_file = tmp_path / "v14_acceptance.sqlite"
    monkeypatch.setattr("rag.store._db_path", lambda: db_file)
    monkeypatch.setattr("rag.ingest._db_path", lambda: db_file, raising=False)
    return db_file


def _ingest(text: str, source_id: str, title: str = "") -> None:
    from rag.ingest import ingest_text
    from rag.store import init_schema

    init_schema()
    ingest_text(text, source_id=source_id, source_type="text", title=title or source_id)


def test_v14_keyword_hits_have_trace_scores(tmp_db: Path) -> None:
    _ingest(
        "V14 验收关键词：ALPHA_BRAVO_DELTA 出现于本段正文。",
        "v14_accept/kw1",
        title="kw-doc",
    )
    from rag.retrieve_knowledge import retrieve_knowledge

    chunks, tr = retrieve_knowledge("ALPHA_BRAVO_DELTA", strategy="keyword", top_k=3)
    assert tr["strategy_requested"] == "keyword"
    assert tr["strategy_used"] == "keyword"
    assert len(chunks) >= 1
    assert tr["no_match"] is False
    c0 = chunks[0]
    assert getattr(c0, "source_id", "")
    assert getattr(c0, "chunk_id", "")
    assert isinstance(tr.get("filters_applied"), dict)


@pytest.mark.parametrize(
    ("strategy", "expect_used_prefix"),
    [
        ("keyword", "keyword"),
        ("auto", "auto:"),
        ("hybrid", "keyword:embedding_disabled"),
    ],
)
def test_v14_strategy_routing_matrix(
    tmp_db: Path, strategy: str, expect_used_prefix: str
) -> None:
    _ingest("semantic hybrid auto 矩阵测试 ZZ_UNIQUE_QQ99。", "v14/mx")
    from rag.retrieve_knowledge import retrieve_knowledge

    chunks, tr = retrieve_knowledge("ZZ_UNIQUE_QQ99", strategy=strategy, top_k=3)
    assert tr["strategy_requested"] == strategy
    su = str(tr["strategy_used"])
    assert su.startswith(expect_used_prefix) or expect_used_prefix in su, (
        f"strategy={strategy} 应路由到预期前缀，实际 strategy_used={su!r}"
    )
    assert "auto_reason" in tr


def test_v14_source_all_requires_source_id_no_silent_keyword(tmp_db: Path) -> None:
    _ingest("source_all 缺锚点测试 TEXT99", "v14/sa1")
    from rag.retrieve_knowledge import retrieve_knowledge

    chunks, tr = retrieve_knowledge(
        "任意 query",
        strategy="source_all",
        filters={},
        top_k=10,
    )
    assert chunks == []
    assert tr.get("failure_reason") == "source_all_missing_source_id"
    assert tr.get("no_match") is True


def test_v14_source_all_with_source_id_has_chunks(tmp_db: Path) -> None:
    sid = "v14/sa2_src"
    _ingest("锚点全量拉取 HELLO_SA2_UNIQUE", sid)
    from rag.retrieve_knowledge import retrieve_knowledge

    chunks, tr = retrieve_knowledge(
        "noop",
        strategy="source_all",
        filters={"source_id": sid},
        top_k=50,
    )
    assert tr["strategy_used"] == "source_all"
    assert len(chunks) >= 1
    assert all(getattr(c, "source_id", "") == sid or sid in str(c.source_id) for c in chunks)


def test_v14_filters_applied_in_trace(tmp_db: Path) -> None:
    _ingest("过滤字段测试 FILTER_TITLE_X", "v14/f1", title="唯一标题FILTER_TITLE_X")
    from rag.retrieve_knowledge import retrieve_knowledge

    _, tr = retrieve_knowledge(
        "FILTER_TITLE_X",
        strategy="keyword",
        filters={"title": "唯一标题FILTER_TITLE_X"},
        top_k=3,
    )
    assert tr.get("filters_applied") == {"title": "唯一标题FILTER_TITLE_X"}


def test_v14_no_match_trace(tmp_db: Path) -> None:
    from rag.retrieve_knowledge import retrieve_knowledge

    chunks, tr = retrieve_knowledge(
        "ZZZ_NO_SUCH_DOC_000111222",
        strategy="keyword",
        top_k=3,
    )
    assert chunks == []
    assert tr["no_match"] is True


def test_v14_semantic_strategy_embedding_off_degrades_keyword_path(tmp_db: Path) -> None:
    """semantic：EMBEDDING_DISABLED 时仍为可解释降级（不写死成功语义）。"""
    _ingest("semantic 占位词 SSC_SEM99", "v14/s1")
    from rag.retrieve_knowledge import retrieve_knowledge

    _, tr = retrieve_knowledge("SSC_SEM99", strategy="semantic", top_k=3)
    assert tr["strategy_requested"] == "semantic"
    assert "keyword" in str(tr["strategy_used"])


def test_v14_low_confidence_trace_from_retrieve_knowledge(monkeypatch: pytest.MonkeyPatch):
    """
    low_confidence：统一入口内 low_confidence 标记 + conservative 链路可复述（不写死 Answer）。
    """
    from rag.retrieve_knowledge import retrieve_knowledge
    from rag.schema import RetrievedChunk

    def fake_do_keyword(
        query: str,
        top_k: int,
        filters,
    ):  # noqa: ARG001
        return [
            RetrievedChunk(
                source_id="low/score/doc",
                chunk_id="low/score/doc::chunk::0",
                text="极弱相关性文本",
                metadata={},
                retrieval_strategy="keyword",
                score=0.04,
                score_raw=0.04,
                score_normalized=0.04,
                score_keyword=0.04,
                score_semantic=0.0,
                combined_score=0.04,
            )
        ]

    monkeypatch.setattr(
        "rag.retrieve_knowledge._do_keyword",
        fake_do_keyword,
    )
    _, tr = retrieve_knowledge("任意 q", strategy="keyword", top_k=3)
    assert tr.get("low_confidence") is True
    assert tr.get("hits", 0) >= 1
    assert "score_max_normalized" in tr or float(tr.get("score_max_normalized", 0)) < 1.0


def test_v14_answer_low_confidence_via_trace_raises_baoshou():
    """
    AnswerRuntime：trace 明示 low_confidence=True 时应抬升保守度（端到端收口层）。
    """
    from agents.answer_agent.runtime import AnswerAgentRuntime, HuidaPan
    from agents.main_agent import MainAgent
    from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
    from application.chat.budget_clock import BudgetClock
    from rag.store import init_schema

    init_schema()
    rt = AnswerAgentRuntime()
    plan = MainAgent().pan(
        "问题 XLC",
        session_id="sess_lowconf",
        http_use_knowledge=True,
        clock=BudgetClock.start(),
    ).plan
    bundle = AgnoMaterialBundle(
        knowledge_block=None,
        web_block=None,
        trace=[
            "v14:middle:strategy_requested=keyword "
            "strategy_used=keyword hits=1 "
            "no_match=False "
            "low_confidence=True "
            "auto_reason=test"
        ],
        knowledge_adequate=True,
        material_still_insufficient=False,
        web_judgment_reason="",
        kb_evidence_tier="weak",
        insufficiency_signal="weak",
        cailiao_pan=CailiaoPan(
            gou=False,
            bukong_xinhao="ruo",
            laiyuan_zhu="kb",
            kb_qiangdu=0.08,
            use_kb=True,
            use_web=False,
            que_shenme="kb",
            xia_yi_bu="wen_yonghu",
        ),
        material_sufficiency="low_confidence",
    )
    hp0 = HuidaPan(
        da_fengshi="zhijie",
        jiegou_mode="plain",
        baoshou_level=0.2,
        lane="test",
        primary_path="test",
    )
    hp1 = rt.pan_shibai_bianjie(hp=hp0, plan=plan, bundle=bundle)
    assert hp1.baoshou_level >= 0.6


def test_v14_used_context_agno_turn_default_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """
    run_agno_chat_turn：retrieve 成功后 extra 含 v12_used_context / v12_retrieval_debug（source/chunk）。
    """
    from unittest.mock import patch

    kb_path = tmp_path / "uw.sqlite"

    def _db():
        kb_path.parent.mkdir(parents=True, exist_ok=True)
        return kb_path

    monkeypatch.setattr("rag.store._db_path", _db)
    monkeypatch.setattr("rag.ingest._db_path", _db, raising=False)
    import rag.store as rs

    rs.init_schema()

    from services.pending_store import reset_pending_store_for_tests as _rst
    from services import agno_chat_service

    _rst()
    agno_chat_service.clear_agno_session_history_for_tests()

    unique = "U_CTX_ABC_UNIQUE_7766"
    from llm.router import V13IntentResult

    def _v13(msg: str):
        if "UW_PREP_FLAG_KEY" in msg:
            return V13IntentResult.ok("prepare_text", source_type="text", raw_source="")
        return V13IntentResult.ok("none")

    monkeypatch.setattr("llm.router.classify_v13_intent_with_llm", _v13)
    sid = "sess-used-ctx"

    with patch("rag.video_ingest.ingest_video_bundle"):
        prep_msg = (
            "加入草稿资料 UW_PREP_FLAG_KEY，"
            "补充说明以满足 prepare_text 的长度约束。"
        )
        r1 = agno_chat_service.run_agno_chat_turn(
            prep_msg,
            session_id=sid,
            use_knowledge=False,
            v13_text_content=f"一段用于追踪的上下文材料，包含关键字 {unique}。",
            v13_title="UCtxDoc",
        )
        assert r1.get("ok") is True
        assert (r1.get("extra") or {}).get("v13_material_status") == "pending"

        r2 = agno_chat_service.run_agno_chat_turn("保存到知识库", session_id=sid)
        cx = r2.get("extra") or {}
        assert cx.get("v13_commit", {}).get("success") is True

        r3 = agno_chat_service.run_agno_chat_turn(
            unique,
            session_id=sid,
            use_knowledge=True,
        )
    ex = r3.get("extra") or {}
    dbg = ex.get("v12_retrieval_debug") or []
    assert isinstance(dbg, list) and len(dbg) >= 1
    assert dbg[0].get("source_id")
    assert dbg[0].get("chunk_id")
    uc = ex.get("v12_used_context")
    assert isinstance(uc, list) and len(uc) >= 1
    joined_uc = "".join(uc)
    assert unique in joined_uc, f"v12_used_context 应带出唯一关键词（或 chunk 摘录），got={joined_uc[:400]}"
    ans = str(r3.get("answer") or "")
    assert len(ans.strip()) >= 8
