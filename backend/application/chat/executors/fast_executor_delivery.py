"""Fast executor delivery gate wiring (Round 1)."""

from __future__ import annotations

from typing import Any

from application.chat.delivery_gate_flow import (
    build_delivery_events,
    gate_input_from_ingress,
    run_delivery_gate,
)
from application.chat.turn_state_machine import TurnStateBundle, apply_event


def finalize_fast_path_delivery(
    *,
    ingress: Any,
    shared_prep: Any | None,
    answer_text: str,
    lane_extra: dict[str, Any],
    turn_state: TurnStateBundle | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Return (deliver_fast, effective_mode, merged_extra)."""
    gate_input = gate_input_from_ingress(
        ingress=ingress,
        executor_profile="fast",
        round_index=0,
        answer_text=answer_text,
        shared_prep=shared_prep,
        limitations=list(lane_extra.get("limitations") or []),
    )
    outcome = run_delivery_gate(
        gate_input,
        ingress=ingress,
        shared_prep=shared_prep,
        base_extra=lane_extra,
    )
    effective_mode = "complex" if outcome.upgrade_profile else "fast"
    if turn_state is not None:
        for event in build_delivery_events(outcome):
            turn_state.runtime, turn_state.decision = apply_event(
                turn_state.runtime,
                turn_state.decision,
                event,
            )
        effective_mode = turn_state.decision.mode
    return outcome.deliver, effective_mode, outcome.extra
