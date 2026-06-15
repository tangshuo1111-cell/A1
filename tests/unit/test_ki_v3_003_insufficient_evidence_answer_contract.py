"""KI-V3-003 — insufficient_evidence answer contract must stay stable."""

from __future__ import annotations

from application.chat.chat_contracts import TurnExitEnvelope
from application.chat.insufficient_evidence_answer_contract import (
    INSUFFICIENT_EVIDENCE_ANSWER_PREFIX,
    apply_insufficient_evidence_answer_contract,
    has_limitation_statement,
)
from application.chat.response_builders.exit_extra_builder import apply_exit_envelope

_ABSOLUTE_PHRASES = ("已经达到准生产级", "完整如下", "可以确定", "毫无疑问")


def test_has_limitation_statement_detects_canonical_markers() -> None:
    assert has_limitation_statement("基于当前材料，无法确认结论。") is True
    assert has_limitation_statement("根据现有材料，无法判断该项目是否已经达到准生产级。") is False


def test_apply_contract_adds_stable_prefix_when_missing_limitation() -> None:
    raw = "根据现有材料，无法判断该项目是否已经达到准生产级。"
    out = apply_insufficient_evidence_answer_contract(raw)
    assert out.startswith("结论：现有材料不足，无法确认。")
    assert "无法确认" in out
    assert raw in out


def test_apply_contract_skips_when_limitation_already_present() -> None:
    raw = "基于当前材料，无法确认该项目是否达到准生产级。"
    assert apply_insufficient_evidence_answer_contract(raw) == raw


def test_apply_contract_empty_answer_returns_prefix_only() -> None:
    assert apply_insufficient_evidence_answer_contract("") == INSUFFICIENT_EVIDENCE_ANSWER_PREFIX.strip()


def test_apply_contract_does_not_add_absolute_conclusion_phrases() -> None:
    out = apply_insufficient_evidence_answer_contract("材料分析如下。")
    for phrase in _ABSOLUTE_PHRASES:
        assert phrase not in out.split("\n", 1)[0]


def test_apply_exit_envelope_applies_contract_only_when_insufficient_evidence_true() -> None:
    envelope = TurnExitEnvelope(
        task_status="partial",
        primary_path="agno_basic_v2_kb_v3_web",
        mode="fast",
        executor_profile="fast",
        router_lane="kb",
        pending_kind="partial_pending",
        material_sufficiency="sufficient",
        quality_gate={
            "pass": False,
            "need_second_round": True,
            "need_more_material": True,
            "reason_codes": ["kb_insufficient", "limitations_present"],
        },
        winner_rule="pending_kind",
        trace={"winner_rule": "pending_kind"},
    )
    raw_answer = "根据现有材料，无法判断该项目是否已经达到准生产级。"
    out = apply_exit_envelope(
        {"answer": raw_answer, "task_status": "partial", "primary_path": "agno_basic_v2_kb_v3_web", "extra": {}},
        envelope,
    )
    assert out["extra"]["insufficient_evidence"] is True
    assert out["task_status"] == "partial"
    assert out["answer"].startswith("结论：现有材料不足，无法确认。")
    assert "无法确认" in out["answer"]


def test_apply_exit_envelope_skips_contract_when_insufficient_evidence_false() -> None:
    envelope = TurnExitEnvelope(
        task_status="succeeded",
        primary_path="document_complex",
        mode="complex",
        executor_profile="complex",
        router_lane="document",
        pending_kind=None,
        material_sufficiency="sufficient",
        quality_gate={"pass": True, "reason_codes": []},
        winner_rule="default_success",
        trace={"winner_rule": "default_success"},
    )
    raw_answer = "项目评测体系分为五层，覆盖 route 到 agent collaboration。"
    out = apply_exit_envelope(
        {"answer": raw_answer, "task_status": "succeeded", "primary_path": "document_complex", "extra": {}},
        envelope,
    )
    assert out["extra"]["insufficient_evidence"] is False
    assert out["answer"] == raw_answer
