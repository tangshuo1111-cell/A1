"""Fast lane gate — block fast path when session carries pending context (§6.3 / R4)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from application.chat.complexity_policy import has_multisource_intent
from application.chat.pending_kind import PendingKind
from application.ingress.lane_decision_schema import LaneDecision
from config.feature_flags import is_enabled

if TYPE_CHECKING:
    from agents.history_context import PendingVideoText, PrevVideoRef


def resolve_fast_lane_session_pending(
    *,
    pending_video: PendingVideoText | None,
    prev_video: PrevVideoRef | None,
    document_pending: bool = False,
) -> PendingKind:
    """Map session snapshot + document pending to PendingKind for fast-lane gating."""
    if pending_video is not None:
        return PendingKind.PROCESSING_PENDING
    if prev_video is not None:
        return PendingKind.MATERIAL_PENDING
    if document_pending:
        return PendingKind.MATERIAL_PENDING
    return PendingKind.NONE


def should_allow_fast(
    *,
    session_pending: PendingKind,
    ingress: LaneDecision,
    message: str,
) -> bool:
    """Return False when fast lane must defer to complex (MainAgent state machine)."""
    if session_pending != PendingKind.NONE:
        return False
    if ingress.mode != "fast":
        return False
    # 复杂多源/对比/综合题：web/kb fast 让位给 complex 主链（Middle 工具）。
    return not (ingress.lane in ("web", "kb") and has_multisource_intent(message))


def fast_lane_gate_active() -> bool:
    return is_enabled("ENABLE_FAST_LANE_GATE")
