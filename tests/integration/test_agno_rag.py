"""V2：最小样例知识闭环（入库 → 检索 → 进 Agno 提示 → 不经旧 workflow）。

运行（仓库根）：
  python -m pytest tests/integration/test_agno_rag.py -q

防伪串见 `knowledge_samples/sample.md`（仅样例内存在的代号）。
"""

from __future__ import annotations

import os

from tests._support.bootstrap import bootstrap_historical_test

REPO_ROOT = bootstrap_historical_test(__file__)

os.environ.setdefault("ENABLE_RAG", "1")
os.environ.setdefault("EMBEDDING_ENABLED", "0")
os.environ.setdefault("RETRIEVAL_MODE", "keyword")

import pytest
from tests._support.pg_fixtures import pg_required_marks

from agents.agno_chat_agent import reset_agent_cache_for_tests
from services import agno_chat_service
from services.capabilities.knowledge import rag_orchestration_service as agno_rag_service
from storage.pg_pool import get_pool

pytestmark = pg_required_marks()


def disable_fast_lane_shortcuts(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import feature_flags

    for flag in feature_flags.LANE_FAST_FLAG.values():
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, flag, False)

# 与 sample.md 中「V2 闭环防伪」行一致（短子串便于检索）
ANTI_FAKE_SUBSTRING = "K9mL-pq83"


def _delete_sample_chunks() -> None:
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM rag_chunks WHERE source_id = %s;",
                (agno_rag_service.SAMPLE_SOURCE_ID,),
            )
        conn.commit()


@pytest.fixture(autouse=True)
def _reset_agno_and_kb(monkeypatch: pytest.MonkeyPatch, pg_settings: None) -> None:  # noqa: ARG001
    disable_fast_lane_shortcuts(monkeypatch)
    agno_chat_service.clear_agno_session_history_for_tests()
    reset_agent_cache_for_tests()
    _delete_sample_chunks()
    yield
    agno_chat_service.clear_agno_session_history_for_tests()
    reset_agent_cache_for_tests()
    _delete_sample_chunks()


def test_ingest_and_retrieve_contains_only_sample_fact() -> None:
    """样例入库后，检索结果必须含防伪子串（非常识裸答可替代）。"""
    n = agno_rag_service.ingest_default_sample_md()
    assert n > 0
    block = agno_rag_service.fetch_knowledge_block(
        f"验收代号里带 {ANTI_FAKE_SUBSTRING} 的那串是什么？"
    )
    assert ANTI_FAKE_SUBSTRING in block
    assert agno_rag_service.SAMPLE_SOURCE_ID in block or "knowledge_samples" in block


def test_without_sample_retrieval_empty_or_no_hit() -> None:
    """去掉样例行后：同一问句检索不到防伪串（证明依赖样例而非模型常识）。"""
    _delete_sample_chunks()
    block = agno_rag_service.fetch_knowledge_block(ANTI_FAKE_SUBSTRING)
    assert ANTI_FAKE_SUBSTRING not in block


def test_agno_service_passes_kb_to_agent_when_use_knowledge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """use_knowledge=True 时，run_basic_qa 收到含防伪串的知识块（不经旧 workflow）。"""
    agno_rag_service.ingest_default_sample_md()
    captured: list[str | None] = []

    def fake_basic(
        user_message: str,
        *,
        context_block: str | None = None,
        knowledge_block: str | None = None,
        web_search_block: str | None = None,
        **_extra: object,
    ) -> str:
        captured.append(knowledge_block)
        return "mock-answer"

    monkeypatch.setattr("services.agno_chat_service.run_basic_qa", fake_basic)
    out = agno_chat_service.run_agno_chat_turn(
        f"请根据知识回答：{ANTI_FAKE_SUBSTRING} 出现在哪份文档？",
        session_id="rag-t1",
        use_knowledge=True,
    )
    assert out["ok"] is True
    assert out.get("primary_path") in ("agno_basic_v2_kb", "agno_basic_v2_kb_v3_web")
    assert captured and captured[0] is not None
    assert ANTI_FAKE_SUBSTRING in (captured[0] or "")


def test_agno_service_kb_empty_after_delete_still_calls_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """入库后曾命中；删掉样例后 knowledge_block 为空，与「有知识时」行为可区分。"""
    agno_rag_service.ingest_default_sample_md()
    captured: list[str | None] = []

    def fake_basic(
        user_message: str,
        *,
        context_block: str | None = None,
        knowledge_block: str | None = None,
        web_search_block: str | None = None,
        **_extra: object,
    ) -> str:
        captured.append(knowledge_block)
        return "x"

    monkeypatch.setattr("services.agno_chat_service.run_basic_qa", fake_basic)
    agno_chat_service.run_agno_chat_turn(
        ANTI_FAKE_SUBSTRING,
        session_id="rag-t2",
        use_knowledge=True,
    )
    assert captured[0] is not None and ANTI_FAKE_SUBSTRING in captured[0]

    captured.clear()
    _delete_sample_chunks()
    agno_chat_service.run_agno_chat_turn(
        ANTI_FAKE_SUBSTRING,
        session_id="rag-t3",
        use_knowledge=True,
    )
    assert captured[0] is None


# V9 R3：旧 services.chat_service 已物理删除，原"防伪"测试无意义；
# 同等保障由 test_v9r1_default_main_body.py 的 T3/T5 + test_v9r3_no_legacy_chain.py 接管。
