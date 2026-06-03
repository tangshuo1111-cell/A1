"""§5.9 — parallel worker budget allocation."""
from __future__ import annotations

import time

from application.chat.budget_allocator import WorkerSpec, allocate_parallel_budgets
from application.chat.budget_clock import BudgetClock


def _clock_with_remaining_ms(remaining_ms: int) -> BudgetClock:
    now = time.perf_counter()
    return BudgetClock(
        started_at=now,
        deadline_at=now + remaining_ms / 1000.0,
        total_budget_ms=remaining_ms,
    )


def test_parallel_budget_allocation_two_workers():
    clock = _clock_with_remaining_ms(3000)
    workers = [
        WorkerSpec(name="w1", priority=1, default_cap_ms=9000),
        WorkerSpec(name="w2", priority=1, default_cap_ms=9000),
    ]
    budgets = allocate_parallel_budgets(clock, workers, reserve_ms=500)
    assert budgets["w1"] == budgets["w2"]
    assert sum(budgets.values()) <= 2500
    assert budgets["w1"] >= 1200
