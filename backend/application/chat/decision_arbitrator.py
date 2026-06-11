"""Mode arbitration — emits events; ``TurnDecision.mode`` is written by state machine only."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from application.chat.budget_clock import BudgetClock
from application.chat.domain.events import TurnEvent, mode_arbitrated_event
from application.chat.domain.reason_codes import canonical_code
from application.chat.pending_kind import PendingKind
from application.ingress.lane_decision_schema import LaneDecision, ModeName
from services.capabilities.contracts import CapabilityAdvice

if TYPE_CHECKING:
    from agents.main_agent.schema import AgnoCollaborationPlan

ARBITRATOR_RESERVE_MS = 500


def resolve_session_pending_kind(
    *,
    pending_video: Any | None,
    prev_video: Any | None = None,
) -> PendingKind:
    """Map session snapshot fields to PendingKind for early arbitration."""
    if pending_video is not None:
        return PendingKind.PROCESSING_PENDING
    if prev_video is not None:
        return PendingKind.MATERIAL_PENDING
    return PendingKind.NONE


def resolve_arbitration_detail(
    *,
    session_pending: PendingKind,
    ingress: LaneDecision,
    main_plan: AgnoCollaborationPlan | None,
    capability_advice: CapabilityAdvice | None,
    clock: BudgetClock,
    reserved_ms: int = ARBITRATOR_RESERVE_MS,
) -> tuple[ModeName, str]:
    """Return proposed mode and detail reason (§5.6 precedence). Does not mutate turn state."""
    if session_pending != PendingKind.NONE:
        return "complex", "session_pending_active"

    if capability_advice is not None and capability_advice.suggested_mode == "demote_to_async":
        return "async", capability_advice.reason or "capability_demote_to_async"

    if clock.remaining_ms(reserve_ms=reserved_ms) <= 0:
        return "async", "budget_reserved_exhausted"

    if main_plan is not None and str(getattr(main_plan, "job_type", "") or "") == "multi_source_compare":
        return "complex", "multi_source_compare"

    return ingress.mode, "ingress_mode"


def build_arbitration_event(
    *,
    session_pending: PendingKind,
    ingress: LaneDecision,
    main_plan: AgnoCollaborationPlan | None,
    capability_advice: CapabilityAdvice | None,
    clock: BudgetClock,
    reserved_ms: int = ARBITRATOR_RESERVE_MS,
) -> TurnEvent:
    """Emit ``ModeArbitrated`` event with canonical reason codes."""
    mode, detail = resolve_arbitration_detail(
        session_pending=session_pending,
        ingress=ingress,
        main_plan=main_plan,
        capability_advice=capability_advice,
        clock=clock,
        reserved_ms=reserved_ms,
    )
    code = canonical_code(detail, lane=ingress.lane, ingress_mode=ingress.mode)
    return mode_arbitrated_event(mode=mode, reason_codes=(code,), detail_reason=detail)


def arbitrate_mode(
    *,
    session_pending: PendingKind,
    ingress: LaneDecision,
    main_plan: AgnoCollaborationPlan | None,
    capability_advice: CapabilityAdvice | None,
    clock: BudgetClock,
    reserved_ms: int = ARBITRATOR_RESERVE_MS,
) -> tuple[ModeName, str]:
    """Backward-compatible detail API for tests and trace strings."""
    return resolve_arbitration_detail(
        session_pending=session_pending,
        ingress=ingress,
        main_plan=main_plan,
        capability_advice=capability_advice,
        clock=clock,
        reserved_ms=reserved_ms,
    )
