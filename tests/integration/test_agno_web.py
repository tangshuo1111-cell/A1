"""V3：网页搜索问答 + 静态网页入库 + 入库后回查（不经旧 workflow）。

仓库根执行：
  python -m pytest tests/integration/test_agno_web.py -q
"""

from __future__ import annotations

import os
import sys

from tests._support.bootstrap import bootstrap_historical_test

REPO_ROOT = bootstrap_historical_test(__file__)
MAIN_CORE_DIR = REPO_ROOT.resolve()

for p in (str(REPO_ROOT), str(MAIN_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("ENABLE_RAG", "1")
os.environ.setdefault("EMBEDDING_ENABLED", "0")
os.environ.setdefault("RETRIEVAL_MODE", "keyword")

import pytest
from tests._support.pg_fixtures import pg_required_marks

from agents.agno_chat_agent import reset_agent_cache_for_tests
from services import agno_chat_service
from services.capabilities.knowledge import rag_orchestration_service as agno_rag_service
from services.capabilities.web import web_orchestration_service as agno_web_service
from storage.pg_pool import get_pool

pytestmark = pg_required_marks()


def disable_fast_lane_shortcuts(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import feature_flags

    for flag in feature_flags.LANE_FAST_FLAG.values():
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, flag, False)

WEB_SNIP_FAKE = "V3-WEB-SNIPPET-UNIQUE-7pQz"
INGEST_SUB = "xJ4k-Np91"


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch, pg_settings: None) -> None:  # noqa: ARG001
    disable_fast_lane_shortcuts(monkeypatch)
    agno_chat_service.clear_agno_session_history_for_tests()
    reset_agent_cache_for_tests()
    _delete_v3_web_chunks()
    yield
    agno_chat_service.clear_agno_session_history_for_tests()
    reset_agent_cache_for_tests()
    _delete_v3_web_chunks()


def _delete_v3_web_chunks() -> None:
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM rag_chunks WHERE source_id LIKE %s;",
                (agno_web_service.V3_WEB_SOURCE_PREFIX + "%",),
            )
        conn.commit()


# --- 第一段：网页搜索问答链 ---


def test_web_not_triggered_without_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """无显式、且未开知识或知识非空场景：不调用网页检索拼装。"""
    called: list[int] = []

    def boom(*_a, **_k) -> str:
        called.append(1)
        raise AssertionError("不应触发网页检索")

    monkeypatch.setattr("services.capabilities.web.web_orchestration_service.fetch_web_evidence_block", boom)
    agno_chat_service.run_agno_chat_turn("今天天气不错", session_id="w0")
    assert not called


def test_web_triggered_explicit_goes_to_answer_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式「上网查」→ 检索块进入 run_basic_qa（防伪：不是只调函数）。"""
    seen: list[str | None] = []

    def fake_basic(
        user_message: str,
        *,
        context_block: str | None = None,
        knowledge_block: str | None = None,
        web_search_block: str | None = None,
        **_extra: object,
    ) -> str:
        seen.append(web_search_block)
        return "ok"

    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
        lambda q, max_results=3: f"[Web检索] 假结果\n摘要: {WEB_SNIP_FAKE}",
    )
    monkeypatch.setattr("services.agno_chat_service.run_basic_qa", fake_basic)
    out = agno_chat_service.run_agno_chat_turn(
        "请上网查一下 V3 防伪测试在说什么",
        session_id="w1",
        use_knowledge=False,
    )
    assert out["ok"] is True
    assert out.get("primary_path") == "agno_basic_v3_web"
    assert seen and seen[0] is not None
    assert WEB_SNIP_FAKE in seen[0]


def test_web_triggered_when_kb_insufficient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """use_knowledge + 本地无命中 → 触发网页检索并进入回答链。"""
    seen: list[str | None] = []

    def fake_basic(
        user_message: str,
        *,
        context_block: str | None = None,
        knowledge_block: str | None = None,
        web_search_block: str | None = None,
        **_extra: object,
    ) -> str:
        seen.append(web_search_block)
        return "ok"

    monkeypatch.setattr("services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_block", lambda q, top_k=5: "")
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
        lambda q, max_results=3: f"摘要含 {WEB_SNIP_FAKE}",
    )
    monkeypatch.setattr("services.agno_chat_service.run_basic_qa", fake_basic)
    agno_chat_service.run_agno_chat_turn(
        "随便问一个本地库里肯定没有的东西",
        session_id="w2",
        use_knowledge=True,
    )
    assert seen[0] and WEB_SNIP_FAKE in seen[0]


def test_web_suppressed_when_kb_has_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """本地知识已有正文：不触发网页检索。"""
    from rag.schema import RetrievedChunk

    called: list[int] = []

    def spy(*_a, **_k) -> str:
        called.append(1)
        return "bad"

    _fake = RetrievedChunk(
        source_id="local", chunk_id="local::chunk::0",
        text="word " * 40, metadata={}, score=0.9,
    )
    # V12 R2：patch 主路径 fetch_knowledge_chunks
    monkeypatch.setattr(
        "services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_chunks",
        lambda q, top_k=5, strategy="auto", filters=None: [_fake],
    )
    monkeypatch.setattr(
        "services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_block",
        lambda q, top_k=5: "来源「local」：\n" + ("word " * 40),
    )
    # V14 R1：Middle 直接调 retrieve_knowledge，需同时 mock
    import rag.retrieve_knowledge as rk_m
    monkeypatch.setattr(
        rk_m, "retrieve_knowledge",
        lambda q, top_k=5, strategy="auto", filters=None, embedding_enabled=None: (
            [_fake],
            {"strategy_requested": "auto", "strategy_used": "auto:keyword",
             "auto_reason": "", "filter": {}, "top_k": top_k,
             "hits": 1, "no_match": False, "low_confidence": False,
             "score_max_normalized": 0.9},
        ),
    )
    monkeypatch.setattr("services.capabilities.web.web_orchestration_service.fetch_web_evidence_block", spy)
    agno_chat_service.run_agno_chat_turn(
        "继续问同主题",
        session_id="w3",
        use_knowledge=True,
    )
    assert not called


# --- 第二段 + 第三段：入库与回查 ---


def test_static_page_ingest_then_rag_recall(monkeypatch: pytest.MonkeyPatch) -> None:
    """网页文本→入库→知识检索能带回防伪子串（防伪：不是只写库）。"""
    fixture = REPO_ROOT / "data" / "samples" / "web" / "v3_static_fixture.html"
    assert fixture.is_file(), f"missing fixture {fixture}"

    def fake_http(_url: str) -> str:
        return fixture.read_text(encoding="utf-8")

    monkeypatch.setattr("services.capabilities.web.web_orchestration_service._http_get_text", fake_http)
    n = agno_web_service.ingest_static_page_from_url(
        "https://fixture.local/v3_static_fixture.html",
        source_id=agno_web_service.V3_WEB_SOURCE_PREFIX + "fixture_test.html",
    )
    assert n > 0
    block = agno_rag_service.fetch_knowledge_block(
        f"验收串里带 {INGEST_SUB} 的防伪条目是什么？"
    )
    assert INGEST_SUB in block


# V9 R3：旧 services.chat_service 已物理删除，原"防伪"测试无意义；
# 同等保障由 test_v9r1_default_main_body.py 的 T3/T5 + test_v9r3_no_legacy_chain.py 接管。
