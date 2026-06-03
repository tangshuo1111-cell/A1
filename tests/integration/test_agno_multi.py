"""V4：最小多环节协作（路由 → RAG/网页资料 → 统一 Agno 作答），不经旧 workflow。

仓库根执行：
  python -m pytest tests/integration/test_agno_multi.py -q
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

from agents.agno_chat_agent import reset_agent_cache_for_tests
from services import agno_chat_service


def disable_fast_lane_shortcuts(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import feature_flags

    for flag in feature_flags.LANE_FAST_FLAG.values():
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, flag, False)


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    disable_fast_lane_shortcuts(monkeypatch)
    agno_chat_service.clear_agno_session_history_for_tests()
    reset_agent_cache_for_tests()
    yield
    agno_chat_service.clear_agno_session_history_for_tests()
    reset_agent_cache_for_tests()


def _trace(out: dict) -> list[str]:
    return list(out.get("extra", {}).get("collaboration_trace") or [])


def _fp(out: dict) -> str:
    return str(out.get("extra", {}).get("v4_path_fingerprint") or "")


def _nodes(out: dict) -> dict[str, str]:
    return dict(out.get("extra", {}).get("v4_nodes") or {})


def test_v4_direct_path_has_route_and_skips_gather(monkeypatch: pytest.MonkeyPatch) -> None:
    """直接问答：不开知识，不触网，轨迹仍体现路由→跳过资料→作答。"""
    monkeypatch.setattr(
        "services.agno_chat_service.run_basic_qa",
        lambda _msg, **kw: "ok",
    )
    out = agno_chat_service.run_agno_chat_turn(
        "你好，简单打个招呼",
        session_id="m0",
        use_knowledge=False,
    )
    t = _trace(out)
    assert "v4:1_route:direct" in t
    assert "v4:2_gather:rag_skip" in t
    assert "v4:2_gather:web_skip" in t
    assert "v4:3_answer:agno_unified" in t
    assert "v4:2_gather:rag_call" not in t
    assert _fp(out) == "v4fp:direct"
    n = _nodes(out)
    assert n["rag_phase"] == "skipped" and n["web_phase"] == "skipped"


def test_v4_knowledge_first_rag_hit_skips_web(monkeypatch: pytest.MonkeyPatch) -> None:
    """知识优先：命中本地 RAG 则不应再走网页检索。"""
    from rag.schema import RetrievedChunk

    web_called: list[int] = []

    def no_web(*_a, **_k) -> str:
        web_called.append(1)
        raise AssertionError("知识已命中时不应调用网页检索")

    _fake_chunk = RetrievedChunk(
        source_id="fixture",
        chunk_id="fixture::chunk::0",
        text="事实段落 " * 20,
        metadata={},
        score=0.9,
    )
    # V12 R2：主路径调 fetch_knowledge_chunks（B 类兼容层 fetch_knowledge_block 已不在主路径）
    monkeypatch.setattr(
        "services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_chunks",
        lambda q, top_k=5, strategy="auto", filters=None: [_fake_chunk],
    )
    monkeypatch.setattr(
        "services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_block",
        lambda q, top_k=5: "来源「fixture」：\n" + ("事实段落 " * 20),
    )
    # V14 R1：Middle 直接调 retrieve_knowledge，需同时 mock
    import rag.retrieve_knowledge as rk_m
    monkeypatch.setattr(
        rk_m, "retrieve_knowledge",
        lambda q, top_k=5, strategy="auto", filters=None, embedding_enabled=None: (
            [_fake_chunk],
            {"strategy_requested": "auto", "strategy_used": "auto:keyword",
             "auto_reason": "", "filter": {}, "top_k": top_k,
             "hits": 1, "no_match": False, "low_confidence": False,
             "score_max_normalized": 0.9},
        ),
    )
    monkeypatch.setattr("services.capabilities.web.web_orchestration_service.fetch_web_evidence_block", no_web)
    monkeypatch.setattr(
        "services.agno_chat_service.run_basic_qa",
        lambda _msg, **kw: "ok",
    )

    out = agno_chat_service.run_agno_chat_turn(
        "根据知识库回答项目代号",
        session_id="m1",
        use_knowledge=True,
    )
    t = _trace(out)
    assert "v4:1_route:knowledge_first" in t
    assert "v4:2_gather:rag_hit" in t
    assert "v4:2_gather:web_skip" in t
    assert not web_called
    assert _fp(out) == "v4fp:kb_only"
    n = _nodes(out)
    assert n["rag_phase"] == "called" and n["rag_outcome"] == "hit"
    assert n["web_phase"] == "skipped"


def test_v4_rag_miss_then_web_supplement(monkeypatch: pytest.MonkeyPatch) -> None:
    """知识不足 → 网页补充：轨迹上须先后出现 rag_miss 与 web_hit。"""
    monkeypatch.setattr("services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_block", lambda q, top_k=5: "")
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
        lambda q, max_results=3: "[Web检索] 假\n摘要: V4-MULTI-WEB-9z",
    )
    monkeypatch.setattr(
        "services.agno_chat_service.run_basic_qa",
        lambda _msg, **kw: "ok",
    )

    out = agno_chat_service.run_agno_chat_turn(
        "随便问本地没有的东西",
        session_id="m2",
        use_knowledge=True,
    )
    t = _trace(out)
    assert "v4:1_route:knowledge_first" in t
    assert "v4:2_gather:rag_miss" in t
    assert "v4:2_gather:web_call" in t
    assert "v4:2_gather:web_hit" in t
    idx_miss = t.index("v4:2_gather:rag_miss")
    idx_hit = t.index("v4:2_gather:web_hit")
    assert idx_miss < idx_hit
    assert _fp(out) == "v4fp:kb_miss_web_hit"
    n = _nodes(out)
    assert n["rag_phase"] == "called" and n["rag_outcome"] == "miss"
    assert n["web_phase"] == "called" and n["web_outcome"] == "hit"


def test_v4_web_explicit_without_use_knowledge(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式上网查：不开 use_knowledge 也应走网页节点（rag 明确跳过）。"""
    rag_calls: list[int] = []

    def count_rag(*a, **k):
        rag_calls.append(1)
        return ""

    monkeypatch.setattr("services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_block", count_rag)
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
        lambda q, max_results=3: "[Web检索] x\n摘要: V4-R2-EXPL-88",
    )
    captured_kw: list[dict] = []

    def cap_basic(_msg, **kw):
        captured_kw.append(kw)
        return "ok"

    monkeypatch.setattr("services.agno_chat_service.run_basic_qa", cap_basic)
    out = agno_chat_service.run_agno_chat_turn(
        "请上网查一下 V4 第二轮显式路径",
        session_id="m4",
        use_knowledge=False,
    )
    assert not rag_calls, "显式网页路径不应调用 RAG"
    t = _trace(out)
    assert "v4:1_route:web_explicit" in t
    assert "v4:2_gather:rag_skip" in t
    assert "v4:2_gather:web_hit" in t
    assert _fp(out) == "v4fp:web_explicit_hit"
    assert captured_kw and "V4-R2-EXPL-88" in (captured_kw[0].get("web_search_block") or "")


def test_v4_three_paths_have_distinct_fingerprints(monkeypatch: pytest.MonkeyPatch) -> None:
    """非伪协作：三条主路径指纹必须互不相同。"""
    from rag.schema import RetrievedChunk

    monkeypatch.setattr(
        "services.agno_chat_service.run_basic_qa",
        lambda _m, **kw: "x",
    )

    a = agno_chat_service.run_agno_chat_turn("hello", session_id="p0", use_knowledge=False)

    _fake_chunk = RetrievedChunk(
        source_id="t", chunk_id="t::chunk::0", text="blk " * 30, metadata={}, score=0.8,
    )
    # V12 R2：patch 主路径 fetch_knowledge_chunks（B 类兼容层同步 patch 防止空回退）
    monkeypatch.setattr(
        "services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_chunks",
        lambda q, top_k=5, strategy="auto", filters=None: [_fake_chunk],
    )
    monkeypatch.setattr(
        "services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_block",
        lambda q, top_k=5: "来源「t」：\n" + ("blk " * 30),
    )
    # V14 R1：Middle 直接调 retrieve_knowledge，需同时 mock
    import rag.retrieve_knowledge as rk_m
    monkeypatch.setattr(
        rk_m, "retrieve_knowledge",
        lambda q, top_k=5, strategy="auto", filters=None, embedding_enabled=None: (
            [_fake_chunk],
            {"strategy_requested": "auto", "strategy_used": "auto:keyword",
             "auto_reason": "", "filter": {}, "top_k": top_k,
             "hits": 1, "no_match": False, "low_confidence": False,
             "score_max_normalized": 0.8},
        ),
    )
    b = agno_chat_service.run_agno_chat_turn(
        "kb only",
        session_id="p1",
        use_knowledge=True,
    )
    monkeypatch.setattr(
        "services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_chunks",
        lambda q, top_k=5, strategy="auto", filters=None: [],
    )
    monkeypatch.setattr(
        rk_m, "retrieve_knowledge",
        lambda q, top_k=5, strategy="auto", filters=None, embedding_enabled=None: (
            [],
            {"strategy_requested": "auto", "strategy_used": "auto:keyword",
             "auto_reason": "", "filter": {}, "top_k": top_k,
             "hits": 0, "no_match": True, "low_confidence": False,
             "score_max_normalized": 0.0},
        ),
    )
    monkeypatch.setattr("services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_block", lambda q, top_k=5: "")
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
        lambda q, max_results=3: "摘要 Z",
    )
    c = agno_chat_service.run_agno_chat_turn(
        "kb miss",
        session_id="p2",
        use_knowledge=True,
    )
    fps = {_fp(a), _fp(b), _fp(c)}
    assert fps == {"v4fp:direct", "v4fp:kb_only", "v4fp:kb_miss_web_hit"}


def test_v4_rag_node_really_invoked(monkeypatch: pytest.MonkeyPatch) -> None:
    """知识路径上 RAG 节点须真实调用（探针计数）。"""
    from rag.schema import RetrievedChunk

    rag_n = {"c": 0}
    fake = RetrievedChunk(
        source_id="x", chunk_id="x::chunk::0", text="ok", metadata={}, score=0.8,
    )

    def spy_rk(q, top_k=5, strategy="auto", filters=None, embedding_enabled=None):
        rag_n["c"] += 1
        return ([fake], {"strategy_requested": "auto", "strategy_used": "auto:keyword",
                         "auto_reason": "", "filter": {}, "top_k": top_k,
                         "hits": 1, "no_match": False, "low_confidence": False,
                         "score_max_normalized": 0.8})

    # V14 R1：spy retrieve_knowledge（Middle 直接调用的统一入口）
    import rag.retrieve_knowledge as rk_m
    monkeypatch.setattr(rk_m, "retrieve_knowledge", spy_rk)
    # V12 R2：仍 patch fetch_knowledge_chunks（兼容）
    monkeypatch.setattr(
        "services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_chunks",
        lambda q, top_k=5, strategy="auto", filters=None: [fake],
    )
    monkeypatch.setattr(
        "services.capabilities.knowledge.rag_orchestration_service.fetch_knowledge_block",
        lambda q, top_k=5: "来源「x」：\nok",
    )
    monkeypatch.setattr(
        "services.agno_chat_service.run_basic_qa",
        lambda _m, **kw: "ok",
    )
    agno_chat_service.run_agno_chat_turn("?", session_id="m5", use_knowledge=True)
    assert rag_n["c"] == 1


def test_v4_not_pseudo_collaboration_trace_length() -> None:
    """非伪协作：轨迹包含 v4 资料门 + V6 三强接管痕迹。"""
    # 使用真实 run_basic_qa 会要 key；只断言 trace 结构由 main/middle/service 写入
    import services.agno_chat_service as mod

    _, _, tr = mod._gather_materials_v4("noop", use_knowledge=False)
    assert len(tr) >= 5
    assert any(x.startswith("v4:") for x in tr)
    assert any(x.startswith("v6:") for x in tr)


def test_no_parallel_agno_multi_orchestrator_file() -> None:
    """未新建兜底厚 orchestrator 文件（协作逻辑收在 agno_chat_service）。"""
    assert not (MAIN_CORE_DIR / "backend" / "services" / "agno_multi_service.py").is_file()


def test_agno_chat_service_has_no_legacy_imports() -> None:
    import services.agno_chat_service as mod

    assert "chat_service" not in mod.__dict__
    assert "workflow" not in mod.__dict__
