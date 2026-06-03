"""Parallel worker budget allocation for Middle gather (§5.9)."""
from __future__ import annotations

from dataclasses import dataclass

from application.chat.budget_clock import BudgetClock


@dataclass(frozen=True)
class WorkerSpec:
    name: str
    priority: int
    default_cap_ms: int


def allocate_parallel_budgets(
    clock: BudgetClock,
    workers: list[WorkerSpec],
    *,
    reserve_ms: int = 500,
) -> dict[str, int]:
    """Allocate per-worker caps without exceeding the turn budget."""
    usable = max(0, clock.remaining_ms(reserve_ms=reserve_ms))
    if not workers or usable <= 0:
        return {worker.name: 0 for worker in workers}

    remaining = usable
    allocations: dict[str, int] = {worker.name: 0 for worker in workers}
    priorities = sorted({worker.priority for worker in workers}, reverse=True)

    for priority in priorities:
        group = [worker for worker in workers if worker.priority == priority]
        if not group or remaining <= 0:
            continue
        share = remaining // len(group)
        for worker in group:
            cap = min(worker.default_cap_ms, share)
            allocations[worker.name] = cap
            remaining -= cap

    total = sum(allocations.values())
    if total > usable:
        overflow = total - usable
        for worker in sorted(workers, key=lambda w: w.priority):
            if overflow <= 0:
                break
            take = min(allocations[worker.name], overflow)
            allocations[worker.name] -= take
            overflow -= take

    return allocations
