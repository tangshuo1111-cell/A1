"""Feedback round execution requires quality_gate approval."""
from __future__ import annotations

from unittest.mock import MagicMock

from application.chat.chat_contracts import QualityGateResult
from application.chat.complex_path_entry import FeedbackGatherContext, run_feedback_round_execution
from application.chat.pending_kind import PendingKind
from config import feature_flags


def test_feedback_execution_skipped_when_gate_does_not_request_refine():
    plan = MagicMock()
    plan.max_rounds = 2
    plan.decision.task_id = "t1"
    plan.tools_allowed = ()
    plan.privacy_scope = ""
    plan.budget_policy = {}
    plan.fallback_steps = ()
    plan.xiezuo_pan.allow_web = True
    plan.original_user_intent = "test"

    bundle = MagicMock()
    bundle.bundle_id = "b1"
    bundle.material_sufficiency = "insufficient"
    bundle.web_block = None
    bundle.answer_limitations = []
    bundle.autonomy_events = []

    deps = MagicMock()
    deps.answer_agent.runtime.build_feedback_request.return_value = {
        "feedback_request_id": "fb1",
        "requested_fallback_step_ids": ["default_web_round1"],
        "requested_fallback_steps": [{"step_id": "default_web_round1", "tool_name": "fetch_web"}],
        "original_user_intent": "test",
    }

    gate = QualityGateResult(pass_=True, need_second_round=False)
    result = run_feedback_round_execution(
        "hello",
        plan,
        bundle,
        deps,
        quality_gate=gate,
        session_pending_kind=PendingKind.NONE,
    )
    assert result is bundle
    deps.answer_agent.runtime.build_feedback_request.assert_not_called()


def test_feedback_execution_can_refresh_kb_bundle_from_shared_prep(monkeypatch):
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_THREE_AGENT_AUTONOMY", True)
    monkeypatch.setattr("application.chat.complex_path_entry.three_agent_autonomy_active", lambda: True)
    monkeypatch.setattr("application.chat.complex_path_entry.autonomy_stop_reason_with_clock", lambda *a, **k: "")
    monkeypatch.setattr(
        "application.chat.complex_path_entry.evaluate_feedback_request",
        lambda **_kwargs: {"allowed": True, "allowed_fallback_steps": [{"step_id": "default_web_round1", "tool_name": "fetch_web"}]},
    )

    plan = MagicMock()
    plan.max_rounds = 2
    plan.decision.task_id = "t2"
    plan.tools_allowed = ("fetch_web",)
    plan.privacy_scope = ""
    plan.budget_policy = {
        "budget_remaining_ms": 20000,
        "llm_calls_remaining": 2,
        "tool_calls_remaining": 2,
    }
    plan.fallback_steps = ({"step_id": "default_web_round1", "tool_name": "fetch_web"},)
    plan.xiezuo_pan.allow_web = True
    plan.original_user_intent = "kb test"
    plan.job_type = ""

    bundle = MagicMock()
    bundle.bundle_id = "b2"
    bundle.material_sufficiency = "insufficient"
    bundle.web_block = None
    bundle.answer_limitations = []
    bundle.autonomy_events = []
    bundle.retrieved_chunks = []

    refreshed = MagicMock()
    refreshed.retrieved_chunks = [MagicMock()]
    refreshed.bundle_id = "b2r1"

    deps = MagicMock()
    deps.answer_agent.runtime.build_feedback_request.return_value = {
        "feedback_request_id": "fb2",
        "requested_fallback_step_ids": ["default_web_round1"],
        "requested_fallback_steps": [{"step_id": "default_web_round1", "tool_name": "fetch_web"}],
        "original_user_intent": "kb test",
    }
    deps.middle_agent.caipan.return_value = refreshed

    gate = QualityGateResult(
        pass_=False,
        need_second_round=True,
        need_more_material=True,
        reason_codes=("kb_insufficient",),
    )
    gather_context = FeedbackGatherContext(
        use_knowledge=True,
        history_snapshot=MagicMock(),
        session_id="s1",
        v13_text_content=None,
        v13_title=None,
        v13_file_content=None,
        shared_prep=MagicMock(snapshot=MagicMock(chunks=[MagicMock()])),
    )

    result = run_feedback_round_execution(
        "hello",
        plan,
        bundle,
        deps,
        quality_gate=gate,
        session_pending_kind=PendingKind.NONE,
        gather_context=gather_context,
    )

    deps.middle_agent.caipan.assert_called_once()
    assert result is refreshed
