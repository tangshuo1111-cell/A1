"""Complex executor exit extra assembly."""

from __future__ import annotations

from typing import Any

from application.chat.budget_clock import (
    SLA_BUDGET_MS,
    BudgetClock,
    remaining_ms_from_clock,
)
from application.chat.exit_signals import set_material_sufficiency_signal, set_mode_signal
from application.chat.shared_material_prep import shared_prep_trace_extra
from application.chat.trace_writer import apply_arbitrator_extra, apply_ingress_complex_extra
from application.chat.turn_exit_extra import build_common_exit_extra
from application.chat.turn_response_builder import build_chat_turn_result
from config.feature_flags import is_enabled


def finalize_complex_exit_extra(
    *,
    base_extra: dict[str, Any],
    timing: dict[str, Any],
    ingress: Any,
    effective_mode: str,
    elapsed_ms: int,
    shared_prep: Any | None,
    complex_delivery_extra: dict[str, Any],
    arbitrator_reason: str,
    arbitrator_trace: list[dict[str, Any]],
    answer_started_remaining_ms: int,
    budget_clock: BudgetClock,
    deadline_at: float,
) -> dict[str, Any]:
    extra = build_common_exit_extra(
        extra_base={
            **base_extra,
            **timing,
        },
        ingress=ingress,
        mode=effective_mode,
        executor_profile="complex" if effective_mode == "complex" else effective_mode,
        progress_stage="completed",
        elapsed_ms=elapsed_ms,
    )
    extra = apply_ingress_complex_extra(
        extra,
        complex_candidate=bool(getattr(ingress, "complex_candidate", False)),
        complex_triggers=list(getattr(ingress, "complex_triggers", []) or []),
        complex_reason_codes=list(getattr(ingress, "complex_reason_codes", []) or []),
    )
    extra.update(shared_prep_trace_extra(shared_prep))
    extra.update(complex_delivery_extra)
    if is_enabled("ENABLE_DECISION_ARBITRATOR"):
        extra = apply_arbitrator_extra(
            extra,
            ingress_mode=ingress.mode,
            decided_mode=effective_mode,
            decided_reason=arbitrator_reason,
            collaboration_trace=arbitrator_trace,
        )
    extra["router_source"] = ingress.router_source
    extra["router_confidence"] = ingress.router_confidence
    extra["router_fallback"] = ingress.router_fallback
    extra["router_decision_ms"] = ingress.router_decision_ms
    extra["router_request_id"] = ingress.request_id
    extra["sla_deadline_ms"] = SLA_BUDGET_MS
    extra["remaining_ms"] = remaining_ms_from_clock(budget_clock, deadline_at=deadline_at)
    if budget_clock is not None:
        extra["budget.remaining_ms_after_main"] = budget_clock.remaining_ms()
        extra["budget.remaining_ms_after_middle"] = budget_clock.remaining_ms()
        extra["budget.remaining_ms_after_answer"] = budget_clock.remaining_ms()
    extra["remaining_ms_at_answer_start"] = answer_started_remaining_ms
    extra["agent_timings"] = {
        "session_snapshot_ms": timing.get("session_snapshot_ms", 0),
        "main_ms": timing.get("main_ms", 0),
        "middle_ms": timing.get("middle_ms", 0),
        "answer_ms": timing.get("answer_ms", 0),
        "session_update_ms": timing.get("session_update_ms", 0),
        "extra_build_ms": timing.get("extra_build_ms", 0),
        "total_ms": elapsed_ms,
    }
    set_mode_signal(extra, effective_mode)
    set_material_sufficiency_signal(
        extra,
        str(base_extra.get("material_sufficiency") or "sufficient"),
    )
    return extra


def build_complex_turn_result(
    *,
    answer_text: str,
    session_id: str | None,
    request_id: str | None,
    extra: dict[str, Any],
    elapsed_ms: int,
) -> dict[str, Any]:
    return build_chat_turn_result(
        answer=answer_text,
        session_id=session_id,
        request_id=request_id,
        extra=extra,
        elapsed_ms=elapsed_ms,
    )
