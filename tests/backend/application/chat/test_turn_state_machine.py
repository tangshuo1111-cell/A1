"""Round 2 — turn state machine transitions and reason codes."""

from __future__ import annotations

import pytest

from application.chat.decision_arbitrator import build_arbitration_event
from application.chat.domain.decision import TurnDecision
from application.chat.domain.events import ingress_classified_event
from application.chat.domain.reason_codes import (
    BUDGET_ASYNC_FALLBACK,
    INGRESS_FAST_KB,
    PENDING_BLOCKS_FAST,
    QUALITY_REQUIRES_COMPLEX,
)
from application.chat.domain.runtime_state import TurnRuntimeState
from application.chat.fast_lane_gate import build_fast_lane_event
from application.chat.pending_kind import PendingKind
from application.chat.turn_state_machine import InvalidTransition, apply_event
from application.ingress.lane_decision_schema import LaneDecision


def _ingress(*, lane: str = "kb", mode: str = "fast") -> LaneDecision:
    return LaneDecision(
        lane=lane,  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        router_source="rule",
        router_confidence=0.9,
        router_decision_ms=1,
    )


class TestTurnStateMachine:
    def test_ingress_classified_sets_lane_and_mode(self) -> None:
        runtime = TurnRuntimeState()
        decision = TurnDecision()
        event = ingress_classified_event(
            lane="kb",
            mode="fast",
            reason_codes=(INGRESS_FAST_KB,),
        )
        runtime, decision = apply_event(runtime, decision, event)
        assert runtime.state == "INGRESSED"
        assert decision.lane == "kb"
        assert decision.mode == "fast"
        assert INGRESS_FAST_KB in decision.reason_codes

    def test_mode_arbitrated_promotes_to_complex_with_reason(self) -> None:
        from application.chat.budget_clock import BudgetClock

        runtime = TurnRuntimeState(state="INGRESSED")
        runtime.visited_states.append("INGRESSED")
        decision = TurnDecision(lane="video", mode="fast")
        event = build_arbitration_event(
            session_pending=PendingKind.PROCESSING_PENDING,
            ingress=_ingress(lane="video", mode="fast"),
            main_plan=None,
            capability_advice=None,
            clock=BudgetClock.start(30_000),
        )
        runtime, decision = apply_event(runtime, decision, event)
        assert runtime.state == "COMPLEX_SELECTED"
        assert decision.mode == "complex"
        assert PENDING_BLOCKS_FAST in decision.reason_codes

    def test_budget_exhaustion_maps_to_async_code(self) -> None:
        import time

        from application.chat.budget_clock import BudgetClock

        runtime = TurnRuntimeState(state="INGRESSED")
        runtime.visited_states.append("INGRESSED")
        decision = TurnDecision(lane="video", mode="fast")
        now = time.perf_counter()
        clock = BudgetClock(started_at=now, deadline_at=now + 0.001, total_budget_ms=1)
        event = build_arbitration_event(
            session_pending=PendingKind.NONE,
            ingress=_ingress(lane="video", mode="fast"),
            main_plan=None,
            capability_advice=None,
            clock=clock,
        )
        runtime, decision = apply_event(runtime, decision, event)
        assert decision.mode == "async"
        assert BUDGET_ASYNC_FALLBACK in decision.reason_codes

    def test_fast_lane_rejected_escalates_to_complex(self) -> None:
        runtime = TurnRuntimeState(state="FAST_SELECTED")
        runtime.visited_states.extend(["INGRESSED", "ARBITRATED", "FAST_SELECTED"])
        decision = TurnDecision(lane="kb", mode="fast")
        event = build_fast_lane_event(
            session_pending=PendingKind.PROCESSING_PENDING,
            ingress=_ingress(),
            message="compare these two links",
        )
        assert event is not None
        runtime, decision = apply_event(runtime, decision, event)
        assert decision.mode == "complex"
        assert runtime.state == "COMPLEX_SELECTED"

    def test_invalid_transition_raises(self) -> None:
        runtime = TurnRuntimeState(state="COMPLETED")
        decision = TurnDecision()
        event = ingress_classified_event(lane="kb", mode="fast", reason_codes=(INGRESS_FAST_KB,))
        with pytest.raises(InvalidTransition):
            apply_event(runtime, decision, event)

    @pytest.mark.parametrize(
        ("detail", "expected_code"),
        [
            ("session_pending_active", PENDING_BLOCKS_FAST),
            ("budget_reserved_exhausted", BUDGET_ASYNC_FALLBACK),
            ("quality_gate_upgrade", QUALITY_REQUIRES_COMPLEX),
        ],
    )
    def test_arbitration_event_always_has_reason_codes(self, detail: str, expected_code: str) -> None:
        from application.chat.domain.events import mode_arbitrated_event
        from application.chat.domain.reason_codes import canonical_code

        code = canonical_code(detail, lane="kb", ingress_mode="fast")
        assert code == expected_code
        event = mode_arbitrated_event(mode="complex", reason_codes=(code,), detail_reason=detail)
        assert event.reason_codes
