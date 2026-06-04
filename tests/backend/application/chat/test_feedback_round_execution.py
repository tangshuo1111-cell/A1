"""Feedback round execution requires quality_gate approval."""
from __future__ import annotations

from unittest.mock import MagicMock

from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
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


def test_feedback_execution_synthesizes_web_when_material_insufficient(monkeypatch):
    monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_THREE_AGENT_AUTONOMY", True)
    monkeypatch.setattr("application.chat.complex_path_entry.three_agent_autonomy_active", lambda: True)
    monkeypatch.setattr("application.chat.complex_path_entry.autonomy_stop_reason_with_clock", lambda *a, **k: "")
    monkeypatch.setattr(
        "application.chat.complex_path_entry.evaluate_feedback_request",
        lambda **_kwargs: {"allowed": True, "allowed_fallback_steps": [{"step_id": "default_web_round1", "tool_name": "fetch_web"}]},
    )
    monkeypatch.setattr(
        "application.chat.complex_path_entry.agno_web_service.fetch_web_evidence_block",
        lambda message, max_results=3: "[Web检索] hybrid retrieval summary",
    )

    plan = MagicMock()
    plan.max_rounds = 2
    plan.decision.task_id = "t3"
    plan.tools_allowed = ("fetch_web",)
    plan.privacy_scope = ""
    plan.budget_policy = {"tool_calls_remaining": 2}
    plan.fallback_steps = ({"step_id": "default_web_round1", "tool_name": "fetch_web"},)
    plan.xiezuo_pan.allow_web = True
    plan.original_user_intent = "compare retrieval"
    plan.job_type = ""

    bundle = AgnoMaterialBundle(
        knowledge_block=None,
        web_block=None,
        trace=[],
        knowledge_adequate=False,
        material_still_insufficient=True,
        web_judgment_reason="skip",
        kb_evidence_tier="none",
        insufficiency_signal="still_empty_after_gather",
        cailiao_pan=CailiaoPan(
            gou=False,
            kb_qiangdu=0.0,
            bukong_xinhao="que",
            laiyuan_zhu="wu",
            use_kb=True,
            use_web=False,
            que_shenme="web_yinzheng",
            xia_yi_bu="bu_wang",
        ),
        material_sufficiency="insufficient",
        bundle_id="b3",
    )

    deps = MagicMock()
    deps.answer_agent.runtime.build_feedback_request.return_value = None

    gate = QualityGateResult(
        pass_=False,
        need_second_round=True,
        need_more_material=True,
        reason_codes=("material_insufficient",),
    )

    result = run_feedback_round_execution(
        "compare keyword vector hybrid",
        plan,
        bundle,
        deps,
        quality_gate=gate,
        session_pending_kind=PendingKind.NONE,
        gather_context=FeedbackGatherContext(
            use_knowledge=False,
            history_snapshot=MagicMock(),
            session_id="s2",
            v13_text_content=None,
            v13_title=None,
            v13_file_content=None,
            shared_prep=None,
        ),
    )

    assert result.web_block == "[Web检索] hybrid retrieval summary"
    assert result.final_answer_based_on_round == "round_1"
