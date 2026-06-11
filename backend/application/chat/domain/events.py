"""Turn state-machine events — gates emit these; only the state machine applies them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from application.chat.chat_contracts import ExecutorProfile

EventKind = Literal[
    "IngressClassified",
    "ApprovalRequired",
    "ModeArbitrated",
    "FastRejected",
    "QualityEscalated",
    "AsyncFallbackTriggered",
    "ExecutionCompleted",
    "ExecutionFailed",
]


@dataclass(frozen=True)
class TurnEvent:
    kind: EventKind
    reason_codes: tuple[str, ...]
    lane: str | None = None
    mode: ExecutorProfile | None = None
    primary_path: str | None = None
    detail_reason: str = ""

    def __post_init__(self) -> None:
        if not self.reason_codes:
            raise ValueError(f"TurnEvent {self.kind!r} requires at least one reason_code")


def ingress_classified_event(
    *,
    lane: str,
    mode: ExecutorProfile,
    reason_codes: tuple[str, ...],
    primary_path: str = "",
) -> TurnEvent:
    return TurnEvent(
        kind="IngressClassified",
        lane=lane,
        mode=mode,
        primary_path=primary_path,
        reason_codes=reason_codes,
        detail_reason="ingress_classified",
    )


def mode_arbitrated_event(
    *,
    mode: ExecutorProfile,
    reason_codes: tuple[str, ...],
    detail_reason: str,
) -> TurnEvent:
    return TurnEvent(
        kind="ModeArbitrated",
        mode=mode,
        reason_codes=reason_codes,
        detail_reason=detail_reason,
    )


def fast_rejected_event(*, reason_codes: tuple[str, ...], detail_reason: str = "fast_lane_blocked") -> TurnEvent:
    return TurnEvent(
        kind="FastRejected",
        mode="complex",
        reason_codes=reason_codes,
        detail_reason=detail_reason,
    )


def quality_escalated_event(*, reason_codes: tuple[str, ...], detail_reason: str = "quality_gate_upgrade") -> TurnEvent:
    return TurnEvent(
        kind="QualityEscalated",
        mode="complex",
        reason_codes=reason_codes,
        detail_reason=detail_reason,
    )


def approval_required_event(*, reason_codes: tuple[str, ...]) -> TurnEvent:
    return TurnEvent(
        kind="ApprovalRequired",
        reason_codes=reason_codes,
        detail_reason="approval_required",
    )


def async_fallback_event(*, reason_codes: tuple[str, ...], detail_reason: str) -> TurnEvent:
    return TurnEvent(
        kind="AsyncFallbackTriggered",
        mode="async",
        reason_codes=reason_codes,
        detail_reason=detail_reason,
    )
