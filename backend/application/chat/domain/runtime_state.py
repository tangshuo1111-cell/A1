"""State-machine runtime (Round 2 will own transitions)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TurnPhase = Literal[
    "RECEIVED",
    "INGRESSED",
    "ARBITRATED",
    "APPROVAL_BLOCKED",
    "FAST_SELECTED",
    "COMPLEX_SELECTED",
    "ASYNC_SELECTED",
    "EXECUTING",
    "COMPLETED",
    "FAILED",
]


@dataclass
class TurnRuntimeState:
    state: TurnPhase = "RECEIVED"
    visited_states: list[TurnPhase] = field(default_factory=list)
    last_event: str | None = None
    transition_log: list[dict[str, Any]] = field(default_factory=list)
