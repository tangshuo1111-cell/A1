"""
V15 最终 clean-state 默认入口冒烟：空库 + 清空 pending + 清 session 后走 run_agno_chat_turn。

不 monkeypatch MiddleAgent / AnswerAgent / run_basic_qa 本体；仅 mock 外部 V13 路由器（llm.router）。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from tests._support.bootstrap import bootstrap_historical_test

_ROOT = str(bootstrap_historical_test(__file__))
_CORE = _ROOT
_CAP = _ROOT
for _p in [_ROOT, _CORE, _CAP]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def disable_fast_lane_shortcuts(monkeypatch: pytest.MonkeyPatch) -> None:
    from config import feature_flags

    for flag in feature_flags.LANE_FAST_FLAG.values():
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, flag, False)


@pytest.fixture
def clean_agno_stack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """PG-only: 确保 schema 就绪 + 重置 pending + 清 session。"""
    from rag import store as rag_store

    rag_store.init_schema()

    from rag.pending_store import reset_for_tests

    reset_for_tests()

    from services import agno_chat_service

    disable_fast_lane_shortcuts(monkeypatch)
    agno_chat_service.clear_agno_session_history_for_tests()
    yield tmp_path
    reset_for_tests()
    agno_chat_service.clear_agno_session_history_for_tests()


def _fake_v13_prepare(msg: str):
    from llm.router import V13IntentResult

    if "CLEANSTATE_PREP_FLAG" in msg:
        return V13IntentResult.ok("prepare_text", source_type="text", raw_source="")
    return V13IntentResult.ok("none")


def test_clean_state_prepare_commit_retrieve_no_video_ingest(
    clean_agno_stack: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A) prepare：pending + temporary_materials，无 commit_results
    B) commit：保存后 commit_results 含 source_id
    C) retrieve：知识库命中 retrieved_chunks
    """
    from services import agno_chat_service

    monkeypatch.setattr(
        "llm.router.classify_v13_intent_with_llm",
        _fake_v13_prepare,
    )

    sid = "cleanstate-smoke-session"
    unique = "CLEANSTATE_UNIQUE_TOKEN_XXYYZZ"

    # 避免「待保存」等词触发 Middle 的 save_requested，与本轮 prepare 同轮误走 commit 拦截
    msg_prepare = (
        "请把下文加入资料草稿 CLEANSTATE_PREP_FLAG，"
        "这是一段用于满足 Main 对 prepare_text 消息长度判定的补充说明文字。"
    )
    with patch("rag.video_ingest.ingest_video_bundle") as ingest_bundle:
        out1 = agno_chat_service.run_agno_chat_turn(
            msg_prepare,
            session_id=sid,
            use_knowledge=False,
            v13_text_content=f"标题：验收材料\n\n正文含关键词 {unique}。",
            v13_title="CleanStateDoc",
        )
        assert out1.get("ok") is True
        ex1 = out1.get("extra") or {}
        assert ingest_bundle.call_count == 0, "默认主链不得调 ingest_video_bundle"

        assert ex1.get("v13_material_status") == "pending", "prepare 后应为 pending"
        assert "v15_commit_results" not in ex1 or not ex1.get("v15_commit_results")

        out2 = agno_chat_service.run_agno_chat_turn(
            "保存到知识库",
            session_id=sid,
            use_knowledge=False,
        )
        assert out2.get("ok") is True
        ex2 = out2.get("extra") or {}
        assert out2.get("answer_type") == "commit_executed"
        assert ex2.get("commit_success") is True, f"保存后应返回 commit_executed 成功标记，实际 extra={ex2.keys()}"
        assert ex2.get("commit_source_id")

        out3 = agno_chat_service.run_agno_chat_turn(
            unique,
            session_id=sid,
            use_knowledge=True,
        )
        assert out3.get("ok") is True
        assert out3.get("primary_path") in {
            "agno_basic_v2_kb",
            "kb_fast",
            "agno_basic_v3_web",
            "agno_basic_v2_kb_v3_web",
        }
        assert out3.get("task_status") in {"succeeded", "pending", "partial"}
        assert ingest_bundle.call_count == 0
