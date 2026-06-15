"""KI-V2.5-002 — empty-session follow-up must not default_success."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from application.chat.history_buffer import ChatTurnDeps
from application.chat.pipeline.turn_helpers import with_turn_exit_gate
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from application.chat.turn_facts import (
    TurnFacts,
    build_empty_context_followup_answer,
    lift_empty_context_followup,
)
from config import feature_flags
from domain.session_types import (
    SessionApprovalHold,
    SessionHistorySnapshot,
    looks_like_followup_reference,
)
from services.session_store import get_session_store, reset_session_store_for_tests

_FORBIDDEN_WORDS = ("刚才", "上一轮", "继续刚才", "我会继续处理", "已经继续", "正在处理")


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    reset_session_store_for_tests()


@pytest.fixture(autouse=True)
def _enable_router(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_DECISION_ARBITRATOR", True)


def test_followup_reference_detects_continue_phrase() -> None:
    assert looks_like_followup_reference("继续刚才那个内容。") is True
    assert looks_like_followup_reference("你好") is False


def test_empty_context_followup_answer_has_no_strong_continuation_words() -> None:
    answer = build_empty_context_followup_answer()
    assert "没有可承接的上文" in answer
    for word in _FORBIDDEN_WORDS:
        assert word not in answer


def test_lift_empty_context_followup_sets_blocked_facts() -> None:
    facts = TurnFacts(effective_mode="fast", executor_profile="fast", answer_type="fast_path")
    snapshot = SessionHistorySnapshot.empty("eval_v2_5_continue_without_context")
    lifted, extra = lift_empty_context_followup(
        facts=facts,
        extra={"lane": "general", "fast_path": "direct_llm"},
        user_message="继续刚才那个内容。",
        history_snapshot=snapshot,
    )
    assert lifted.approval is not None
    assert lifted.approval.blocked is True
    assert lifted.answer_type == "approval_blocked"
    assert lifted.legacy_task_status == "blocked"
    assert extra.get("empty_context_followup") is True
    assert extra.get("history_used") is False


def test_lift_empty_context_followup_skips_web_url_new_request() -> None:
    facts = TurnFacts(effective_mode="fast", executor_profile="fast")
    snapshot = SessionHistorySnapshot.empty("eval_v2_5_web_followup")
    lifted, _extra = lift_empty_context_followup(
        facts=facts,
        extra={"lane": "web", "web_evidence_chars": 100, "web_primary_source": "page_body"},
        user_message="请总结这个网页：https://docs.python.org/3/tutorial/index.html",
        history_snapshot=snapshot,
    )
    assert lifted is facts
    facts = TurnFacts(effective_mode="fast", executor_profile="fast")
    snapshot = SessionHistorySnapshot.from_history(
        session_id="s1",
        context_block="用户：上一轮问题\n助手：上一轮回答",
        turns=1,
        prev_video=None,
    )
    lifted, _extra = lift_empty_context_followup(
        facts=facts,
        extra={"lane": "general"},
        user_message="继续刚才，帮我总结。",
        history_snapshot=snapshot,
    )
    assert lifted is facts


def test_with_turn_exit_gate_skips_empty_context_when_approval_hold_active() -> None:
    snapshot = SessionHistorySnapshot.empty("s1")
    hold = SessionApprovalHold(blocked=True, kind="long_video_asr", reason="await_user_confirm")
    out = with_turn_exit_gate(
        {
            "answer": "我会继续处理刚才那个内容。",
            "session_id": "s1",
            "request_id": "r1",
            "task_status": "succeeded",
            "primary_path": "direct_llm",
            "answer_type": "fast_path",
            "pipeline_ok": True,
            "extra": {"lane": "general", "mode": "fast", "fast_path": "direct_llm"},
        },
        ingress=None,
        user_message="继续刚才那个内容。",
        approval_hold=hold,
        history_snapshot=snapshot,
    )
    assert out["extra"].get("empty_context_followup") is not True


def test_with_turn_exit_gate_blocks_empty_context_followup() -> None:
    snapshot = SessionHistorySnapshot.empty("eval_v2_5_continue_without_context")
    out = with_turn_exit_gate(
        {
            "answer": "我会继续处理刚才那个内容，当前结果如下。",
            "session_id": "eval_v2_5_continue_without_context",
            "request_id": "r1",
            "task_status": "succeeded",
            "primary_path": "direct_llm",
            "answer_type": "fast_path",
            "pipeline_ok": True,
            "extra": {"lane": "general", "mode": "fast", "fast_path": "direct_llm"},
        },
        ingress=None,
        user_message="继续刚才那个内容。",
        history_snapshot=snapshot,
    )
    assert out["task_status"] == "blocked"
    assert out["task_status"] != "succeeded"
    assert out["extra"].get("empty_context_followup") is True
    assert out["extra"].get("exit", {}).get("winner_rule") == "approval_blocked"
    answer = str(out.get("answer") or "")
    assert answer == build_empty_context_followup_answer()
    for word in _FORBIDDEN_WORDS:
        assert word not in answer


def _deps(store) -> ChatTurnDeps:
    from agents.answer_agent import AnswerAgent
    from agents.main_agent import MainAgent
    from agents.middle_agent import MiddleAgent

    return ChatTurnDeps(
        histories=store.histories,
        session_prev_video=store.session_prev_video,
        session_pending_video=store.session_pending_video,
        session_approval_hold=store.session_approval_hold,
        lock=store.lock,
        main_agent=MainAgent(),
        middle_agent=MiddleAgent(),
        answer_agent=AnswerAgent(),
        run_basic_qa=lambda *_a, **_k: "我会继续处理刚才那个内容。",
        path_fingerprint=lambda *_a, **_k: "fp",
        nodes_contract=lambda *_a, **_k: {},
    )


def test_empty_session_continue_followup_not_default_success() -> None:
    store = get_session_store()
    session_id = "eval_v2_5_continue_without_context"
    with patch(
        "application.chat.executors.fast_lanes.fast_llm.run_fast_llm_answer",
        return_value="我会继续处理刚才那个内容，当前进展如下。",
    ):
        out = run_agno_chat_turn_impl(
            "继续刚才那个内容。",
            session_id=session_id,
            deps=_deps(store),
        )

    assert out["task_status"] == "blocked"
    assert out["task_status"] != "succeeded"
    assert out["extra"].get("empty_context_followup") is True
    assert out["extra"].get("exit", {}).get("winner_rule") == "approval_blocked"
    answer = str(out.get("answer") or "")
    assert answer == build_empty_context_followup_answer()
    for word in _FORBIDDEN_WORDS:
        assert word not in answer
