"""Tests for delivery_gate_flow thin orchestrator."""
from __future__ import annotations

from application.chat.delivery_gate_flow import (
    QualityGateInput,
    gate_input_from_ingress,
    run_delivery_gate,
)
from application.ingress.lane_decision_schema import LaneDecision


def _ingress(**kwargs) -> LaneDecision:
    return LaneDecision(
        lane="kb",
        mode="fast",
        router_source="rule",
        router_confidence=0.9,
        router_decision_ms=1,
        complex_candidate=kwargs.get("complex_candidate", False),
        complex_reason_codes=list(kwargs.get("complex_reason_codes", ())),
    )


class TestDeliveryGateFlow:
    def test_fast_upgrade_delegates_to_quality_gate(self):
        inp = QualityGateInput(
            executor_profile="fast",
            round_index=0,
            complex_candidate=True,
            complex_reason_codes=("comparison",),
            lane="general",
            answer_text="太短",
        )
        outcome = run_delivery_gate(inp, ingress=_ingress(complex_candidate=True, complex_reason_codes=("comparison",)))
        assert outcome.upgrade_profile is True
        assert outcome.deliver is False
        assert outcome.extra["quality_gate.upgrade_profile"] is True

    def test_complex_round0_need_second_round(self):
        inp = gate_input_from_ingress(
            ingress=_ingress(complex_candidate=True),
            executor_profile="complex",
            round_index=0,
            answer_text="",
            limitations=["partial"],
        )
        outcome = run_delivery_gate(inp, ingress=_ingress(complex_candidate=True))
        assert outcome.gate.need_second_round is True
        assert outcome.deliver is False
        assert "refine_reason_codes" in outcome.extra

    def test_complex_round0_pass_delivers(self):
        text = (
            "相比方案A，方案B在成本上更优，但在扩展性方面较弱。"
            "从实施周期看，A更适合短期上线，B更适合长期演进。"
            "1. 成本：B更低\n2. 扩展：A更好\n总结：视场景取舍。"
        )
        inp = gate_input_from_ingress(
            ingress=_ingress(),
            executor_profile="complex",
            round_index=0,
            answer_text=text,
            shared_prep=None,
        )
        outcome = run_delivery_gate(
            inp,
            ingress=_ingress(),
            shared_prep=None,
        )
        assert outcome.gate.pass_ is True
        assert outcome.deliver is True
