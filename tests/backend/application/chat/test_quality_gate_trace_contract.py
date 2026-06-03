"""Trace field contracts for quality gate / ingress complex signals."""
from __future__ import annotations

from application.chat.chat_contracts import QualityGateResult
from application.chat.trace_writer import (
    apply_ingress_complex_extra,
    apply_profile_exit_extra,
    apply_quality_gate_extra,
)


def test_quality_gate_trace_fields():
    gate = QualityGateResult(
        pass_=False,
        upgrade_profile=True,
        reason_codes=("answer_too_shallow",),
    )
    extra = apply_quality_gate_extra(
        {},
        gate=gate,
        complex_candidate=True,
        fast_gate_pass=False,
    )
    assert extra["complex_candidate"] is True
    assert extra["quality_gate.pass"] is False
    assert extra["quality_gate.upgrade_profile"] is True
    assert extra["fast_gate_pass"] is False
    assert extra["upgrade_to_agent_reason"] == ["answer_too_shallow"]


def test_profile_exit_trace_fields():
    extra = apply_profile_exit_extra(
        {},
        profile_exit_reason="quality_gate_upgrade",
        from_profile="fast",
        to_profile="complex",
    )
    assert extra["profile_exit_reason"] == "quality_gate_upgrade"
    assert extra["executor_profile"] == "complex"


def test_ingress_complex_trace_fields():
    extra = apply_ingress_complex_extra(
        {},
        complex_candidate=True,
        complex_triggers=["strong:comparison"],
        complex_reason_codes=["comparison"],
    )
    assert extra["complex_candidate"] is True
    assert extra["complex_triggers"] == ["strong:comparison"]
    assert extra["complex_reason_codes"] == ["comparison"]
