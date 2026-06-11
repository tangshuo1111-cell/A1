"""Current routing decision snapshot (written by state machine from Round 2)."""

from __future__ import annotations

from dataclasses import dataclass

from application.chat.chat_contracts import ExecutorProfile


@dataclass(frozen=True)
class TurnDecision:
    lane: str = "general"
    mode: ExecutorProfile = "fast"
    primary_path: str = ""
    reason_codes: tuple[str, ...] = ()
    requires_approval: bool = False
    should_async: bool = False
