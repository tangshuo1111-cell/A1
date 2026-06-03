"""主链四条路径：寒暄、知识库、显式网页检索、视频字幕 URL（可控 mock）。

文件名用 four_paths：平实英文，对齐 answer 侧的 lane/kb/web 语义。
"""

from __future__ import annotations

import os
import sys

import pytest
from tests._support.bootstrap import bootstrap_historical_test

from config import feature_flags

REPO_ROOT = bootstrap_historical_test(__file__)
MAIN_CORE_DIR = REPO_ROOT.resolve()
for p in (str(REPO_ROOT), str(MAIN_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("ENABLE_RAG", "1")
os.environ.setdefault("EMBEDDING_ENABLED", "0")
os.environ.setdefault("RETRIEVAL_MODE", "keyword")
os.environ.setdefault("LIGHT_MAQA_FAKE_LLM", "1")


from agents.agno_chat_agent import reset_agent_cache_for_tests  # noqa: E402
from services import agno_chat_service

KB_MARK = "K9mL-pq83"


@pytest.fixture(autouse=True)
def _reset_session() -> None:
    agno_chat_service.clear_agno_session_history_for_tests()
    reset_agent_cache_for_tests()
    yield
    agno_chat_service.clear_agno_session_history_for_tests()
    reset_agent_cache_for_tests()


def test_path_plain_greeting_lane() -> None:
    """短寒暄：默认走 general fast path，不进入完整 complex 主链。"""
    out = agno_chat_service.run_agno_chat_turn("你好", session_id="p-plain")
    assert out["ok"] is True
    extra = out.get("extra") or {}
    assert extra.get("lane") == "general"
    assert extra.get("mode") == "fast"
    assert extra.get("fast_lane_name") == "general"
    assert extra.get("material_layer_used") == "temporary"
    assert extra.get("material_scope") == "session"
    assert out.get("primary_path") in {"local_greeting", "canned", "general"}


def test_path_kb_when_sample_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """KB fast lane：材料含防伪子串时答案可追溯。"""
    from application.chat.chat_contracts import (
        KbSufficiencyResult,
        RetrievalSnapshot,
        SharedMaterialPrepResult,
    )
    from application.ingress.lane_decision_schema import LaneDecision

    kb_snip = f"样例文档含 {KB_MARK}"

    monkeypatch.setattr(
        "application.chat.run_chat_turn.resolve_lane_decision",
        lambda **kw: LaneDecision(
            request_id="req-kb",
            session_id=str(kw.get("session_id") or ""),
            lane="kb",
            mode="fast",
            router_source="rule",
            router_confidence=0.99,
            router_decision_ms=1,
        ),
    )

    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_DECISION_ARBITRATOR", False)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_COMPLEX_PENDING_KIND_V2", False)

    def _fake_shared_prep(**_kwargs: object) -> SharedMaterialPrepResult:
        snap = RetrievalSnapshot(
            chunks=(kb_snip,),
            hits=1,
            top_score=0.92,
            evidence_tier="strong",
            rag_miss=False,
        )
        return SharedMaterialPrepResult(
            snapshot=snap,
            kb_sufficiency=KbSufficiencyResult(
                level="adequate_simple",
                adequate=True,
                hits=1,
                top_score=0.92,
                evidence_tier="strong",
            ),
            knowledge_block=kb_snip,
            material_text=kb_snip,
            capabilities_called=("capability.kb.retrieve",),
        )

    monkeypatch.setattr("application.chat.run_chat_turn.run_shared_material_prep", _fake_shared_prep)
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
        lambda *_a, **_k: "",
    )
    monkeypatch.setattr(
        "application.chat.fast_path_entry.summarize_fast_material",
        lambda **kw: f"ok-kb-{KB_MARK}",
    )
    out = agno_chat_service.run_agno_chat_turn(
        f"请根据知识回答：代号里含 {KB_MARK} 的那段说明在哪个样例文档？",
        session_id="p-kb",
        use_knowledge=True,
    )
    assert out["ok"] is True
    assert KB_MARK in (out.get("answer") or "")
    extra = out.get("extra") or {}
    assert extra.get("fast_lane_name") == "kb"
    assert extra.get("material_layer_used") == "temporary"
    assert extra.get("material_scope") == "knowledge"


def test_path_web_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 7：显式网页读取优先走 web fast lane，不再默认进旧 agno_basic_v3_web。"""
    web_snip = "FOURPATH-WEB-9xQz"
    monkeypatch.setattr(
        "services.capabilities.web.web_orchestration_service.fetch_web_evidence_block",
        lambda q, max_results=3: f"[Web]\n{web_snip}",
    )
    seen: list[str | None] = []

    def cap(
        *_a: object,
        web_search_block: str | None = None,
        **_k: object,
    ) -> str:
        seen.append(web_search_block)
        return "ok-web"

    monkeypatch.setattr("services.agno_chat_service.run_basic_qa", cap)
    out = agno_chat_service.run_agno_chat_turn(
        "请上网查一下 四类路径 网页指纹测试在说什么",
        session_id="p-web",
    )
    assert out["ok"]
    assert out.get("primary_path") == "web_fast"
    extra = out.get("extra") or {}
    assert extra.get("fast_lane_name") == "web"
    assert extra.get("capabilities_called") == ["capability.web.static_fetch"]


def test_path_video_url_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """B 站白名单 URL + mock 字幕；extra 带出视频链路指纹。"""
    from tools.video.tool_result import VideoToolResult

    bili = "https://www.bilibili.com/video/BV1xx411c7mD"

    def fake_extract(url: str, *, session_id: str = ""):
        return VideoToolResult(
            tool_name="extract_web_video_subtitle",
            source_type="web_video",
            source_ref=url,
            title="stub-video",
            text=f"字幕占位含 {KB_MARK}",
            status="success",
            metadata={"text_source": "subtitle"},
        )

    monkeypatch.setattr(
        "tools.video.extract_web_video_subtitle._extract_web_video_subtitle",
        fake_extract,
    )

    out = agno_chat_service.run_agno_chat_turn(
        f"请总结视频 {bili} 的主要内容",
        session_id="p-vid",
    )
    extra = out.get("extra") or {}
    assert extra.get("fast_lane_name") == "video" or extra.get("v10_main_explicit_kind") == "video_url"
    assert "video_task_id" not in extra
