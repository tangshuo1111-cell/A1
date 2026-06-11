"""Executor / agent aggregate result (mapped to ChatTurnResult at the boundary)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from application.chat.chat_contracts import TurnExitTaskStatus


@dataclass
class TurnExecutionResult:
    answer: str = ""
    materials: list[Any] = field(default_factory=list)
    pending: dict[str, Any] | None = None
    task_info: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    exit_status: TurnExitTaskStatus | None = None
