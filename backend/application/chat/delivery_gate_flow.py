"""Thin orchestrator — single entry for delivery / upgrade / refine decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.chat.chat_contracts import (
    ExecutorProfile,
    KbSufficiencyResult,
    MaterialGateFacts,
    QualityGateResult,
    SharedMaterialPrepResult,
)
from application.chat.domain.events import TurnEvent, quality_escalated_event
from application.chat.domain.reason_codes import QUALITY_REQUIRES_COMPLEX
from application.chat.refine_kind import resolve_refine_kind, would_answer_only_refine_apply
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
    use_knowledge: bool = False
    retrieved_chunks_count: int = 0
    pending_kind: str | None = None
    insufficient_evidence: bool = False
    kb_sufficiency: KbSufficiencyResult | None = None
    material_facts: MaterialGateFacts | None = None
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
        material_facts=gate_input.material_facts,
        use_knowledge=gate_input.use_knowledge,
        retrieved_chunks_count=gate_input.retrieved_chunks_count,
    )
    extra = apply_quality_gate_extra(
        extra,
        gate=gate,
        complex_candidate=gate_input.complex_candidate,
        fast_gate_pass=gate.pass_ if gate_input.executor_profile == "fast" else None,
    )
    refine_kind = resolve_refine_kind(
        need_second_round=gate.need_second_round,
        need_more_material=gate.need_more_material,
        reason_codes=gate.reason_codes,
        insufficient_evidence=gate_input.insufficient_evidence,
        pending_kind=gate_input.pending_kind,
        answer_text=gate_input.answer_text,
        limitations=list(gate_input.limitations),
        lane=gate_input.lane,
        use_knowledge=gate_input.use_knowledge,
        retrieved_chunks_count=gate_input.retrieved_chunks_count,
    )
    extra["refine_kind"] = refine_kind
    extra["metrics.would_answer_refine"] = would_answer_only_refine_apply(
        reason_codes=gate.reason_codes,
        need_second_round=gate.need_second_round,
        need_more_material=gate.need_more_material,
        insufficient_evidence=gate_input.insufficient_evidence,
        pending_kind=gate_input.pending_kind,
        answer_text=gate_input.answer_text,
        live=False,
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


def material_gate_facts_from_bundle(
    bundle: Any,
    *,
    plan: Any | None = None,
) -> MaterialGateFacts | None:
    """Assemble read-only Middle facts for quality_gate (no re-judgment)."""
    if bundle is None:
        return None
    web_block = str(getattr(bundle, "web_block", "") or "").strip()
    xiezuo = getattr(plan, "xiezuo_pan", None) if plan is not None else None
    return MaterialGateFacts(
        material_sufficiency=str(getattr(bundle, "material_sufficiency", "sufficient") or "sufficient"),
        material_still_insufficient=bool(getattr(bundle, "material_still_insufficient", False)),
        try_rag_executed=bool(getattr(plan, "needs_retrieval", False)) if plan is not None else False,
        has_web_evidence=bool(web_block),
        allow_web=bool(getattr(xiezuo, "allow_web", False)) if xiezuo is not None else False,
    )


def gate_input_from_ingress(
    *,
    ingress: Any,
    executor_profile: ExecutorProfile,
    round_index: int,
    answer_text: str,
    shared_prep: SharedMaterialPrepResult | None = None,
    limitations: list[str] | None = None,
    material_facts: MaterialGateFacts | None = None,
    use_knowledge: bool = False,
    retrieved_chunks_count: int = 0,
    pending_kind: str | None = None,
    insufficient_evidence: bool = False,
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
        material_facts=material_facts,
        limitations=tuple(limitations or ()),
        use_knowledge=use_knowledge,
        retrieved_chunks_count=retrieved_chunks_count,
        pending_kind=pending_kind,
        insufficient_evidence=insufficient_evidence,
    )


def build_delivery_events(outcome: DeliveryGateOutcome) -> list[TurnEvent]:
    """Emit profile events from delivery gate outcome (no direct mode mutation)."""
    if outcome.upgrade_profile:
        codes = tuple(outcome.gate.reason_codes) or (QUALITY_REQUIRES_COMPLEX,)
        return [quality_escalated_event(reason_codes=codes)]
    return []


def merge_delivery_extra(target: dict[str, Any], outcome: DeliveryGateOutcome) -> dict[str, Any]:
    merged = dict(target)
    merged.update(outcome.extra)
    return merged
