"""Executor IO types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from application.chat.domain.context import TurnContext
from application.chat.domain.decision import TurnDecision
from application.chat.domain.execution_result import TurnExecutionResult
from schemas import ChatTurnResult


@dataclass
class ExecutorOutcome:
    """Result of an executor attempt."""

    handled: bool = False
    chat_turn: ChatTurnResult | dict[str, Any] | None = None
    effective_mode: str | None = None
    timing: dict[str, Any] = field(default_factory=dict)
    execution: TurnExecutionResult | None = None

    @classmethod
    def not_handled(cls, *, effective_mode: str, timing: dict[str, Any]) -> ExecutorOutcome:
        return cls(handled=False, effective_mode=effective_mode, timing=timing)

    @classmethod
    def from_chat_turn(
        cls,
        chat_turn: ChatTurnResult | dict[str, Any],
        *,
        effective_mode: str,
        timing: dict[str, Any],
    ) -> ExecutorOutcome:
        answer = chat_turn.get("answer", "") if isinstance(chat_turn, dict) else getattr(chat_turn, "answer", "")
        return cls(
            handled=True,
            chat_turn=chat_turn,
            effective_mode=effective_mode,
            timing=timing,
            execution=TurnExecutionResult(answer=str(answer or ""), trace=dict(chat_turn.get("extra") or {}) if isinstance(chat_turn, dict) else {}),
        )


@dataclass(frozen=True)
class ExecutorRequest:
    """Minimal executor invocation envelope."""

    ctx: TurnContext
    decision: TurnDecision
