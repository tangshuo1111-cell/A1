"""Turn state machine — sole writer of ``TurnDecision.mode`` and profile selection."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from application.chat.domain.decision import TurnDecision
from application.chat.domain.events import TurnEvent
from application.chat.domain.runtime_state import TurnPhase, TurnRuntimeState


@dataclass
class TurnStateBundle:
    """Mutable holder for state-machine runtime + decision snapshot."""

    runtime: TurnRuntimeState
    decision: TurnDecision


class InvalidTransition(Exception):
    """Raised when an event is not legal in the current phase."""


def _append_reason(decision: TurnDecision, codes: tuple[str, ...]) -> TurnDecision:
    merged = decision.reason_codes + codes
    # de-dupe preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for c in merged:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return replace(decision, reason_codes=tuple(unique))


def _visit(runtime: TurnRuntimeState, phase: TurnPhase) -> None:
    runtime.state = phase
    runtime.visited_states.append(phase)


def _log(runtime: TurnRuntimeState, event: TurnEvent, *, note: str = "") -> None:
    runtime.last_event = event.kind
    entry: dict[str, Any] = {
        "event": event.kind,
        "reason_codes": list(event.reason_codes),
        "detail_reason": event.detail_reason,
        "state": runtime.state,
    }
    if note:
        entry["note"] = note
    runtime.transition_log.append(entry)


def _profile_phase(mode: str) -> TurnPhase:
    if mode == "async":
        return "ASYNC_SELECTED"
    if mode == "complex":
        return "COMPLEX_SELECTED"
    return "FAST_SELECTED"


def apply_event(
    runtime: TurnRuntimeState,
    decision: TurnDecision,
    event: TurnEvent,
) -> tuple[TurnRuntimeState, TurnDecision]:
    """Apply one event; return updated runtime + decision snapshots."""
    phase = runtime.state

    if event.kind == "IngressClassified":
        if phase not in ("RECEIVED",):
            raise InvalidTransition(f"IngressClassified invalid from {phase}")
        lane = event.lane or decision.lane
        mode = event.mode or decision.mode
        decision = replace(
            decision,
            lane=lane,
            mode=mode,
            primary_path=event.primary_path or decision.primary_path,
            should_async=mode == "async",
        )
        decision = _append_reason(decision, event.reason_codes)
        _visit(runtime, "INGRESSED")
        _log(runtime, event)
        return runtime, decision

    if event.kind == "ApprovalRequired":
        decision = replace(decision, requires_approval=True)
        decision = _append_reason(decision, event.reason_codes)
        _visit(runtime, "APPROVAL_BLOCKED")
        _log(runtime, event)
        return runtime, decision

    if event.kind == "ModeArbitrated":
        if phase not in ("INGRESSED", "ARBITRATED"):
            raise InvalidTransition(f"ModeArbitrated invalid from {phase}")
        mode = event.mode or decision.mode
        decision = replace(decision, mode=mode, should_async=mode == "async")
        decision = _append_reason(decision, event.reason_codes)
        _visit(runtime, "ARBITRATED")
        _visit(runtime, _profile_phase(mode))
        _log(runtime, event)
        return runtime, decision

    if event.kind == "FastRejected":
        if phase not in ("FAST_SELECTED", "ARBITRATED", "INGRESSED"):
            raise InvalidTransition(f"FastRejected invalid from {phase}")
        decision = replace(decision, mode="complex", should_async=False)
        decision = _append_reason(decision, event.reason_codes)
        _visit(runtime, "COMPLEX_SELECTED")
        _log(runtime, event)
        return runtime, decision

    if event.kind == "QualityEscalated":
        if phase not in ("FAST_SELECTED", "EXECUTING"):
            raise InvalidTransition(f"QualityEscalated invalid from {phase}")
        decision = replace(decision, mode="complex", should_async=False)
        decision = _append_reason(decision, event.reason_codes)
        _visit(runtime, "COMPLEX_SELECTED")
        _log(runtime, event)
        return runtime, decision

    if event.kind == "AsyncFallbackTriggered":
        if phase not in ("INGRESSED", "ARBITRATED", "FAST_SELECTED", "COMPLEX_SELECTED"):
            raise InvalidTransition(f"AsyncFallbackTriggered invalid from {phase}")
        decision = replace(decision, mode="async", should_async=True)
        decision = _append_reason(decision, event.reason_codes)
        _visit(runtime, "ASYNC_SELECTED")
        _log(runtime, event)
        return runtime, decision

    if event.kind == "ExecutionCompleted":
        _visit(runtime, "COMPLETED")
        _log(runtime, event)
        return runtime, decision

    if event.kind == "ExecutionFailed":
        _visit(runtime, "FAILED")
        _log(runtime, event)
        return runtime, decision

    raise InvalidTransition(f"Unknown event kind: {event.kind}")


def apply_events(
    runtime: TurnRuntimeState,
    decision: TurnDecision,
    events: list[TurnEvent],
) -> tuple[TurnRuntimeState, TurnDecision]:
    for event in events:
        runtime, decision = apply_event(runtime, decision, event)
    return runtime, decision
