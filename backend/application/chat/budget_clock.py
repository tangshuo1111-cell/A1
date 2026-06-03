from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any

from config._helpers import _env_int

SLA_BUDGET_MS = _env_int("CHAT_SYNC_BUDGET_MS", 30_000)


class DeadlineExceeded(Exception):
    """Raised when a worker exceeds the turn budget (§5.1)."""

    def __init__(self, *, stage: str = "", remaining_ms: int = 0) -> None:
        self.stage = stage
        self.remaining_ms = remaining_ms
        super().__init__(f"deadline exceeded at stage={stage!r} remaining_ms={remaining_ms}")


class SkippedForBudget(Exception):
    """Raised when parallel budget allocation assigns zero ms to a worker (§5.9)."""

    def __init__(self, *, worker: str = "") -> None:
        self.worker = worker
        super().__init__(f"worker skipped for budget: {worker!r}")


@dataclass(frozen=True)
class BudgetClock:
    started_at: float
    deadline_at: float
    total_budget_ms: int

    @classmethod
    def start(cls, total_budget_ms: int = SLA_BUDGET_MS) -> BudgetClock:
        started = time.perf_counter()
        return cls(
            started_at=started,
            deadline_at=started + total_budget_ms / 1000.0,
            total_budget_ms=total_budget_ms,
        )

    def remaining_ms(self, reserve_ms: int = 0) -> int:
        current = time.perf_counter()
        raw = max(0, int((self.deadline_at - current) * 1000))
        return max(0, raw - max(0, reserve_ms))

    def elapsed_ms(self) -> int:
        return format_ms((time.perf_counter() - self.started_at) * 1000)

    def is_exhausted(self, reserve_ms: int = 0) -> bool:
        return self.remaining_ms(reserve_ms=reserve_ms) <= 0

    def child_budget(self, max_ms: int, reserve_ms: int = 0) -> int:
        return min(max(0, int(max_ms)), self.remaining_ms(reserve_ms=reserve_ms))


def format_ms(ms: float) -> int:
    return max(0, int(ms))


def remaining_ms(*, deadline_at: float, now: float | None = None) -> int:
    current = time.perf_counter() if now is None else now
    return max(0, int((deadline_at - current) * 1000))
def remaining_ms_from_clock(clock: BudgetClock | None, *, deadline_at: float | None = None) -> int:
    if clock is not None:
        return clock.remaining_ms()
    if deadline_at is not None:
        return remaining_ms(deadline_at=deadline_at)
    return SLA_BUDGET_MS


def with_budget_plan(plan: Any, **updates: Any) -> Any:
    try:
        return replace(plan, **updates)
    except TypeError:
        return plan
