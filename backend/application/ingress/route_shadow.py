"""Route shadow observability — compare rule baseline vs final ingress decision.

Shadow mode is observability-only unless ENABLE_SEMANTIC_ROUTE_CUTOVER is on.
Does not mint parallel routing control; attaches fields for eval / metrics only.
"""

from __future__ import annotations

from typing import Any

from application.chat.complexity_policy import evaluate_complex_candidate
from config.feature_flags import is_enabled

from .lane_decision_schema import LaneDecision, ModeName
from .mode_selector import select_mode
from .request_classifier import RequestSignals


def shadow_mode_for_message(
    *,
    lane: str,
    signals: RequestSignals,
    message: str,
    complex_reason_codes: tuple[str, ...] = (),
) -> tuple[ModeName, float]:
    complex_signal = evaluate_complex_candidate(message)
    codes = complex_reason_codes or tuple(complex_signal.reason_codes)
    candidate = complex_signal.complex_candidate or bool(codes)
    return select_mode(
        lane=lane,
        signals=signals,
        message=message,
        complex_candidate=candidate,
        complex_reason_codes=codes,
    )


def should_skip_main_agent_escalation(
    *,
    rule_lane: str,
    rule_mode: str,
    message: str,
    signals: RequestSignals,
    complex_reason_codes: tuple[str, ...],
) -> bool:
    """Cutover: rule baseline and shadow semantic agree on mode → skip LLM escalation."""
    if not is_enabled("ENABLE_SEMANTIC_ROUTE_CUTOVER"):
        return False
    shadow_mode, _ = shadow_mode_for_message(
        lane=rule_lane,
        signals=signals,
        message=message,
        complex_reason_codes=complex_reason_codes,
    )
    return shadow_mode == rule_mode


def attach_route_shadow(
    decision: LaneDecision,
    *,
    rule_lane: str,
    rule_mode: str,
    message: str,
    signals: RequestSignals,
) -> LaneDecision:
    """Fill shadow observability fields on an existing decision (no routing change)."""
    if not is_enabled("ENABLE_ROUTE_SHADOW_OBSERVABILITY"):
        return decision
    shadow_mode, shadow_conf = shadow_mode_for_message(
        lane=rule_lane,
        signals=signals,
        message=message,
        complex_reason_codes=tuple(decision.complex_reason_codes),
    )
    return decision.model_copy(
        update={
            "route_shadow_rule_lane": rule_lane,
            "route_shadow_rule_mode": rule_mode,
            "route_shadow_semantic_mode": shadow_mode,
            "route_shadow_semantic_confidence": round(shadow_conf, 4),
            "route_shadow_lane_match": rule_lane == decision.lane,
            "route_shadow_mode_match": rule_mode == decision.mode,
            "route_shadow_semantic_mode_match": shadow_mode == decision.mode,
        }
    )


def route_shadow_extra(ingress: Any) -> dict[str, Any]:
    """Map ingress shadow fields → fragile extra (C-level observability)."""
    keys = (
        "route_shadow_rule_lane",
        "route_shadow_rule_mode",
        "route_shadow_semantic_mode",
        "route_shadow_semantic_confidence",
        "route_shadow_lane_match",
        "route_shadow_mode_match",
        "route_shadow_semantic_mode_match",
    )
    out: dict[str, Any] = {}
    for key in keys:
        val = getattr(ingress, key, None)
        if val is not None:
            out[key] = val
    return out
