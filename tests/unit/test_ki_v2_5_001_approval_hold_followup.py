"""KI-V2.5-001 — approval hold session facts and follow-up blocked exit."""

from __future__ import annotations

from threading import Lock
from unittest.mock import patch

import pytest

from application.chat.approval_gate_flow import (
    build_approval_blocked_turn_result,
    persist_approval_blocked_session_hold,
)
from application.chat.approval_gate import ApprovalGateResult
from application.chat.history_buffer import ChatTurnDeps
from application.chat.pipeline.turn_helpers import with_turn_exit_gate
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from application.chat.turn_facts import TurnFacts, lift_session_approval_hold
from config import feature_flags
from domain.session_types import SessionApprovalHold, looks_like_task_status_inquiry
from services.session_store import get_session_store, reset_session_store_for_tests
from storage.memory_chat_session_store import MemoryChatSessionStore


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    reset_session_store_for_tests()


@pytest.fixture(autouse=True)
def _enable_approval_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_APPROVAL_GATE_V1", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_DECISION_ARBITRATOR", True)


def test_task_status_inquiry_detects_followup_phrase() -> None:
    assert looks_like_task_status_inquiry("现在处理完成了吗？") is True
    assert looks_like_task_status_inquiry("你好") is False


def test_persist_approval_hold_writes_structured_session_fact() -> None:
    store = get_session_store()
    persist_approval_blocked_session_hold(
        session_id="eval_v2_5_background_task",
        result=ApprovalGateResult(
            required=True,
            kind="long_video_asr",
            reason="await_user_confirm",
            blocked=True,
        ),
    )
    hold = store.get_approval_hold("eval_v2_5_background_task")
    assert hold is not None
    assert hold.blocked is True
    assert hold.kind == "long_video_asr"
    assert hold.has_real_task is False


def test_lift_session_approval_hold_sets_approval_blocked_facts() -> None:
    facts = TurnFacts(effective_mode="fast", executor_profile="fast", answer_type="fast_path")
    hold = SessionApprovalHold(blocked=True, kind="long_video_asr", reason="await_user_confirm")
    lifted, extra = lift_session_approval_hold(
        facts=facts,
        extra={"lane": "general", "fast_path": True},
        approval_hold=hold,
        user_message="现在处理完成了吗？",
    )
    assert lifted.approval is not None
    assert lifted.approval.blocked is True
    assert lifted.answer_type == "approval_blocked"
    assert extra.get("approval_gate.blocked") is True
    assert not extra.get("task_id")
    assert not extra.get("background_task_id")


def test_with_turn_exit_gate_reuses_approval_blocked_rule() -> None:
    hold = SessionApprovalHold(blocked=True, kind="long_video_asr", reason="await_user_confirm")
    out = with_turn_exit_gate(
        {
            "answer": "后台任务已经处理完成。",
            "session_id": "s1",
            "request_id": "r1",
            "task_status": "succeeded",
            "primary_path": "direct_llm",
            "answer_type": "fast_path",
            "pipeline_ok": True,
            "extra": {"lane": "general", "mode": "fast", "fast_path": True},
        },
        ingress=None,
        user_message="现在处理完成了吗？",
        approval_hold=hold,
    )
    assert out["task_status"] == "blocked"
    assert out["primary_path"] == "approval_gate"
    assert out.get("task_id") in (None, "")
    assert "没有可追踪的后台任务" in str(out.get("answer") or "")
    assert out["extra"].get("exit", {}).get("winner_rule") == "approval_blocked"


def _deps(store: MemoryChatSessionStore) -> ChatTurnDeps:
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
        run_basic_qa=lambda *_a, **_k: "后台任务已经处理完成，总结如下：视频主要讲了……",
        path_fingerprint=lambda *_a, **_k: "fp",
        nodes_contract=lambda *_a, **_k: {},
    )


def test_two_turn_flow_blocked_then_followup_not_default_success() -> None:
    store = get_session_store()
    session_id = "eval_v2_5_background_task"
    message_1 = "请后台处理这个长视频并总结：https://www.youtube.com/watch?v=rfscVS0vtbw"

    turn_1 = run_agno_chat_turn_impl(
        message_1,
        session_id=session_id,
        deps=_deps(store),
    )

    assert turn_1["task_status"] == "blocked"
    assert turn_1.get("task_id") in (None, "")
    hold = store.get_approval_hold(session_id)
    assert hold is not None
    assert hold.blocked is True
    assert hold.kind == "long_video_asr"

    with patch(
        "application.chat.executors.fast_lanes.fast_llm.run_fast_llm_answer",
        return_value="后台任务已经处理完成。",
    ):
        turn_2 = run_agno_chat_turn_impl(
            "现在处理完成了吗？",
            session_id=session_id,
            deps=_deps(store),
        )

    assert turn_2["task_status"] == "blocked"
    assert turn_2["task_status"] != "succeeded"
    assert turn_2["primary_path"] == "approval_gate"
    assert turn_2.get("task_id") in (None, "")
    assert turn_2["extra"].get("exit", {}).get("winner_rule") == "approval_blocked"
    assert "没有可追踪的后台任务" in str(turn_2.get("answer") or "")


def test_build_approval_blocked_turn_result_persists_hold_without_task_id() -> None:
    store = get_session_store()
    out = build_approval_blocked_turn_result(
        result=ApprovalGateResult(
            required=True,
            kind="long_video_asr",
            reason="await_user_confirm",
            blocked=True,
        ),
        message="长视频 https://youtube.com/watch?v=abc",
        session_id="sess-hold",
        request_id="req-1",
        elapsed_ms=5,
        ingress=None,
    )
    assert out["task_status"] == "blocked"
    assert out.get("task_id") in (None, "")
    assert store.get_approval_hold("sess-hold") is not None
