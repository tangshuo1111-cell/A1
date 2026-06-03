"""Thin orchestrator — single entry for delivery / upgrade / refine decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.chat.chat_contracts import (
    ExecutorProfile,
    KbSufficiencyResult,
    QualityGateResult,
    SharedMaterialPrepResult,
)
from application.chat.quality_gate import evaluate_quality_gate
from application.chat.shared_material_prep import shared_prep_trace_extra
from application.chat.trace_writer import (
    apply_ingress_complex_extra,
    apply_profile_exit_extra,
    apply_quality_gate_extra,
)
from config.feature_flags import quality_gate_active


@dataclass(frozen=True)
class QualityGateInput:
    executor_profile: ExecutorProfile
    round_index: int
    complex_candidate: bool
    complex_reason_codes: tuple[str, ...]
    lane: str
    answer_text: str
    kb_sufficiency: KbSufficiencyResult | None = None
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeliveryGateOutcome:
    gate: QualityGateResult
    extra: dict[str, Any]
    deliver: bool
    upgrade_profile: bool


def run_delivery_gate(
    gate_input: QualityGateInput,
    *,
    ingress: Any | None = None,
    shared_prep: SharedMaterialPrepResult | None = None,
    base_extra: dict[str, Any] | None = None,
) -> DeliveryGateOutcome:
    """Evaluate quality gate and merge trace fields. No retrieval or answer generation."""
    extra = dict(base_extra or {})
    if ingress is not None:
        extra = apply_ingress_complex_extra(
            extra,
            complex_candidate=bool(getattr(ingress, "complex_candidate", False)),
            complex_triggers=list(getattr(ingress, "complex_triggers", []) or []),
            complex_reason_codes=list(getattr(ingress, "complex_reason_codes", []) or []),
        )
    extra["executor_profile"] = gate_input.executor_profile
    extra["round_index"] = gate_input.round_index
    extra.update(shared_prep_trace_extra(shared_prep))

    if gate_input.kb_sufficiency is None and shared_prep is not None:
        kb_suff = shared_prep.kb_sufficiency
    else:
        kb_suff = gate_input.kb_sufficiency

    if not quality_gate_active():
        extra["fast_gate_pass"] = gate_input.executor_profile == "fast"
        gate = QualityGateResult(pass_=True, reason_codes=())
        return DeliveryGateOutcome(gate=gate, extra=extra, deliver=True, upgrade_profile=False)

    gate = evaluate_quality_gate(
        executor_profile=gate_input.executor_profile,
        complex_candidate=gate_input.complex_candidate,
        answer_text=gate_input.answer_text,
        kb_sufficiency=kb_suff,
        limitations=list(gate_input.limitations),
        lane=gate_input.lane,
        round_index=gate_input.round_index,
        complex_reason_codes=gate_input.complex_reason_codes,
    )
    extra = apply_quality_gate_extra(
        extra,
        gate=gate,
        complex_candidate=gate_input.complex_candidate,
        fast_gate_pass=gate.pass_ if gate_input.executor_profile == "fast" else None,
    )

    if gate_input.executor_profile == "fast":
        if gate.upgrade_profile:
            extra = apply_profile_exit_extra(
                extra,
                profile_exit_reason="quality_gate_upgrade",
                from_profile="fast",
                to_profile="complex",
            )
            extra["upgrade_to_agent_reason"] = list(gate.reason_codes)
            return DeliveryGateOutcome(gate=gate, extra=extra, deliver=False, upgrade_profile=True)
        extra["fast_gate_pass"] = gate.pass_
        return DeliveryGateOutcome(gate=gate, extra=extra, deliver=True, upgrade_profile=False)

    if gate.pass_:
        return DeliveryGateOutcome(gate=gate, extra=extra, deliver=True, upgrade_profile=False)

    if gate.need_second_round:
        return DeliveryGateOutcome(gate=gate, extra=extra, deliver=False, upgrade_profile=False)

    return DeliveryGateOutcome(gate=gate, extra=extra, deliver=True, upgrade_profile=False)


def gate_input_from_ingress(
    *,
    ingress: Any,
    executor_profile: ExecutorProfile,
    round_index: int,
    answer_text: str,
    shared_prep: SharedMaterialPrepResult | None = None,
    limitations: list[str] | None = None,
) -> QualityGateInput:
    kb_suff = shared_prep.kb_sufficiency if shared_prep is not None else None
    return QualityGateInput(
        executor_profile=executor_profile,
        round_index=round_index,
        complex_candidate=bool(getattr(ingress, "complex_candidate", False)),
        complex_reason_codes=tuple(getattr(ingress, "complex_reason_codes", ()) or ()),
        lane=str(getattr(ingress, "lane", "general") or "general"),
        answer_text=answer_text,
        kb_sufficiency=kb_suff,
        limitations=tuple(limitations or ()),
    )


def merge_delivery_extra(target: dict[str, Any], outcome: DeliveryGateOutcome) -> dict[str, Any]:
    merged = dict(target)
    merged.update(outcome.extra)
    return merged
