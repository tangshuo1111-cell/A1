"""Integration-style tests for delivery / quality gate wiring."""
from __future__ import annotations

from threading import Lock
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agents.main_agent.schema import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent.schema import AgnoMaterialBundle, CailiaoPan
from application.chat.chat_contracts import QualityGateResult
from application.chat.delivery_gate_flow import gate_input_from_ingress, run_delivery_gate
from application.chat.history_buffer import ChatTurnDeps
from application.chat.executors.fast_executor_delivery import finalize_fast_path_delivery as _finalize_fast_path_delivery
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from application.ingress.lane_decision_schema import LaneDecision
from config import feature_flags
from schemas import MainDecision


def _ingress(**kwargs) -> LaneDecision:
    return LaneDecision(
        lane=kwargs.get("lane", "general"),
        mode="fast",
        router_source="rule",
        router_confidence=0.9,
        router_decision_ms=1,
        complex_candidate=kwargs.get("complex_candidate", True),
        complex_reason_codes=list(kwargs.get("complex_reason_codes", ("comparison",))),
    )


class TestFastUpgradeIntegration:
    def test_shallow_fast_answer_upgrades_to_complex(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_QUALITY_GATE", True)
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
        deliver, mode, extra = _finalize_fast_path_delivery(
            ingress=_ingress(),
            shared_prep=None,
            answer_text="太短",
            lane_extra={"lane": "general"},
        )
        assert deliver is False
        assert mode == "complex"
        assert extra.get("quality_gate.upgrade_profile") is True
        assert "answer_too_shallow" in (extra.get("upgrade_to_agent_reason") or [])


class TestKbSufficiencyIntegration:
    def test_same_hits_different_sufficiency_by_complexity(self) -> None:
        from application.chat.chat_contracts import RetrievalSnapshot
        from services.capabilities.knowledge.kb_sufficiency import evaluate_kb_sufficiency

        snap = RetrievalSnapshot(hits=2, top_score=0.5, evidence_tier="usable", rag_miss=False)
        simple = evaluate_kb_sufficiency(snap, complex_candidate=False)
        complex_ = evaluate_kb_sufficiency(snap, complex_candidate=True)
        assert simple.adequate is True
        assert complex_.adequate is False


class TestComplexSecondRoundIntegration:
    def test_round0_fail_triggers_second_round_signal(self) -> None:
        inp = gate_input_from_ingress(
            ingress=_ingress(complex_candidate=True),
            executor_profile="complex",
            round_index=0,
            answer_text="",
            limitations=["partial"],
        )
        outcome = run_delivery_gate(inp, ingress=_ingress(complex_candidate=True))
        assert outcome.gate.need_second_round is True
        assert "refine_reason_codes" in outcome.extra


class TestTraceContractIntegration:
    def test_fast_and_complex_share_quality_gate_field_names(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_QUALITY_GATE", True)
        _, _, fast_extra = _finalize_fast_path_delivery(
            ingress=_ingress(complex_candidate=False),
            shared_prep=None,
            answer_text="这是一段足够长的 fast 路径测试回答，用于验证 trace 字段一致性。" * 2,
            lane_extra={},
        )
        complex_inp = gate_input_from_ingress(
            ingress=_ingress(complex_candidate=True),
            executor_profile="complex",
            round_index=0,
            answer_text="这是一段足够长的 complex 路径测试回答，用于验证 trace 字段一致性。" * 2,
        )
        complex_out = run_delivery_gate(complex_inp, ingress=_ingress(complex_candidate=True))
        for key in ("quality_gate.pass", "complex_candidate"):
            assert key in fast_extra or key == "complex_candidate"
        assert "quality_gate.pass" in complex_out.extra


class TestMultisourceQualityGateIntegration:
    def test_multisource_uses_delivery_gate_not_answer_review(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from application.chat.executors.complex.complex_path_impl import run_multisource_round0_answer

        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_QUALITY_GATE", True)
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_THREE_AGENT_AUTONOMY", False)

        bundle = SimpleNamespace(
            bundle_id="b-ms",
            knowledge_block="kb",
            web_block="web",
            trace=[],
            answer_limitations=[],
        )
        plan = SimpleNamespace(job_type="multi_source_compare", decision=SimpleNamespace(task_id="t"))
        deps = SimpleNamespace(
            run_basic_qa=lambda *_a, **_k: "这是一段足够长的多来源比较回答，用于验证 quality_gate 接入。" * 2,
        )
        out_bundle, answer = run_multisource_round0_answer(
            "比较 A 和 B",
            plan,
            bundle,
            deps,
            use_knowledge=True,
            history_snapshot=SimpleNamespace(),
            session_id="s1",
            context_block="",
            knowledge_block="kb",
            web_block="web",
            main_dec=plan.decision,
            v13_text_content=None,
            v13_title=None,
            v13_file_content=None,
        )
        assert answer
        assert out_bundle is bundle

        inp = gate_input_from_ingress(
            ingress=_ingress(complex_candidate=True),
            executor_profile="complex",
            round_index=0,
            answer_text=answer,
            limitations=["partial"],
        )
        outcome = run_delivery_gate(inp, ingress=_ingress(complex_candidate=True))
        assert outcome.gate.need_second_round is True


class TestFeedbackExecutionGatedByQuality:
    def test_feedback_only_when_quality_requests(self) -> None:
        from application.chat.executors.complex.complex_path_impl import run_feedback_round_execution

        bundle = SimpleNamespace(bundle_id="b1", material_sufficiency="insufficient", web_block=None)
        deps = SimpleNamespace(answer_agent=SimpleNamespace(runtime=SimpleNamespace()))
        gate_pass = QualityGateResult(pass_=True, need_second_round=False)
        out = run_feedback_round_execution(
            "test",
            SimpleNamespace(max_rounds=2, decision=SimpleNamespace(task_id="t"), tools_allowed=(), privacy_scope="", budget_policy={}, fallback_steps=(), xiezuo_pan=SimpleNamespace(allow_web=False), original_user_intent=""),
            bundle,
            deps,
            quality_gate=gate_pass,
        )
        assert out is bundle

        gate_refine = QualityGateResult(
            pass_=False,
            need_second_round=True,
            need_more_material=True,
            reason_codes=("kb_insufficient",),
        )
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_THREE_AGENT_AUTONOMY", False)
        try:
            out2 = run_feedback_round_execution(
                "test",
                SimpleNamespace(max_rounds=2, decision=SimpleNamespace(task_id="t"), tools_allowed=(), privacy_scope="", budget_policy={}, fallback_steps=(), xiezuo_pan=SimpleNamespace(allow_web=False), original_user_intent=""),
                bundle,
                deps,
                quality_gate=gate_refine,
            )
            assert out2 is bundle
        finally:
            monkeypatch.undo()


def _complex_bundle() -> AgnoMaterialBundle:
    return AgnoMaterialBundle(
        knowledge_block="KB 材料",
        web_block=None,
        trace=["vtest:bundle_ready"],
        knowledge_adequate=True,
        web_judgment_reason="explicit_only",
        material_still_insufficient=False,
        material_sufficiency="sufficient",
        kb_evidence_tier="strong",
        insufficiency_signal="ok",
        cailiao_pan=CailiaoPan(
            gou=True,
            kb_qiangdu=0.2,
            bukong_xinhao="ok",
            laiyuan_zhu="kb",
            use_kb=True,
            use_web=False,
            que_shenme="none",
            xia_yi_bu="zhi_da",
        ),
    )


def _complex_plan() -> AgnoCollaborationPlan:
    return AgnoCollaborationPlan(
        decision=MainDecision(task_id="gate-complex", task_status="routed"),
        force_skip_evidence=False,
        web_supplement_mode="explicit_only",
        answer_composition="default",
        xiezuo_pan=MainXiezuoPan(
            renwu_lei="hunhe",
            zhengju_need=True,
            allow_kb=True,
            allow_web=False,
            fengxian_yinzi=0.6,
            celue_tag="complex",
        ),
    )


def _deps_for_complex() -> ChatTurnDeps:
    return ChatTurnDeps(
        histories={},
        session_prev_video={},
        session_pending_video={},
        lock=Lock(),
        main_agent=SimpleNamespace(pan=lambda *_a, **_k: _complex_plan()),
        middle_agent=SimpleNamespace(caipan=lambda *_a, **_k: _complex_bundle()),
        answer_agent=SimpleNamespace(
            pan=lambda *_a, **_k: SimpleNamespace(lane="general", primary_path="complex"),
            xiezuo_extra=lambda *_a, **_k: {},
        ),
        run_basic_qa=lambda *_a, **_k: "这是复杂路径下的完整回答。它不应被 canned 快答偷走。" * 2,
        path_fingerprint=lambda *_a, **_k: "fp",
        nodes_contract=lambda *_a, **_k: {},
    )


class TestComplexModeBlocksFastExits:
    def test_canned_fast_does_not_steal_complex_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_QUALITY_GATE", True)
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_INGRESS_ROUTER_V2", True)
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_THREE_AGENT_AUTONOMY", False)

        fake_ingress = LaneDecision(
            lane="general",
            mode="complex",
            router_source="rule",
            router_confidence=0.95,
            router_decision_ms=1,
            complex_candidate=True,
            complex_reason_codes=["decision_tradeoff"],
        )

        with (
            patch("application.ingress.resolve_lane_decision", return_value=fake_ingress),
            patch(
                "application.chat.executors.fast_executor_general.try_canned_fast_answer",
                return_value=("这是一条本可 canned 的快答。", {"fast_path": "local_term_explain"}),
            ),
        ):
            out = run_agno_chat_turn_impl(
                "帮我做决策：该不该现在重构主链？",
                session_id="gate-complex-canned",
                deps=_deps_for_complex(),
            )

        assert out["task_status"] == "succeeded"
        assert out["extra"]["mode"] == "complex"
        assert out["primary_path"] != "direct_llm"
        assert out["primary_path"] == out["extra"]["primary_path"]
        assert out["extra"].get("fast_path") is not True
