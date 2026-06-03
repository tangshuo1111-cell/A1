"""§5.1 / §5.9 — BudgetClock propagation and parallel allocation."""
from __future__ import annotations

import time

import pytest
from tests.backend.application.chat.test_main_plan_cache import (
    _deps_with_counting_pan,
    _disable_fast_lanes,
)

from application.chat.budget_allocator import WorkerSpec, allocate_parallel_budgets
from application.chat.budget_clock import SLA_BUDGET_MS, BudgetClock
from application.chat.run_chat_turn import run_agno_chat_turn_impl
from config import feature_flags
from services.capabilities.video.duration_probe import should_force_video_background


def _clock_with_remaining_ms(remaining_ms: int) -> BudgetClock:
    now = time.perf_counter()
    return BudgetClock(
        started_at=now,
        deadline_at=now + remaining_ms / 1000.0,
        total_budget_ms=remaining_ms,
    )


class TestParallelBudgetAllocation:
    def test_two_workers_split_remaining_after_reserve(self):
        clock = _clock_with_remaining_ms(3000)
        workers = [
            WorkerSpec(name="a", priority=1, default_cap_ms=5000),
            WorkerSpec(name="b", priority=1, default_cap_ms=5000),
        ]
        budgets = allocate_parallel_budgets(clock, workers, reserve_ms=500)
        assert budgets["a"] == budgets["b"]
        assert sum(budgets.values()) <= 2500
        assert budgets["a"] >= 1200


class TestBudgetClockPropagation:
    def test_long_video_forces_background_under_turn_budget(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_BUDGET_CLOCK_V2", True)
        clock = _clock_with_remaining_ms(1000)
        force, reason = should_force_video_background(
            remaining_budget_ms=SLA_BUDGET_MS,
            probe_elapsed_ms=0,
            source_type="web",
            subtitle_available=False,
            duration_sec=50.0,
            clock=clock,
        )
        assert force is True
        assert reason in {"remaining_budget_low", "deadline_exhausted", "duration_implies_background"}

    def test_run_chat_turn_records_budget_fields_when_v2_enabled(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _disable_fast_lanes(monkeypatch)
        monkeypatch.setitem(feature_flags.FEATURE_FLAGS, "ENABLE_BUDGET_CLOCK_V2", True)
        monkeypatch.setattr(
            "application.chat.run_chat_turn._build_extra",
            lambda *a, **k: {"lane": "agno_basic", "primary_path": "agno_basic", "mode": "complex"},
        )
        started = time.perf_counter()
        out = run_agno_chat_turn_impl(
            "你好",
            session_id="s2-budget-v2",
            deps=_deps_with_counting_pan([]),
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        extra = out["extra"]
        assert elapsed_ms <= SLA_BUDGET_MS + 500
        assert "budget.remaining_ms_after_main" in extra
        assert "budget.remaining_ms_after_middle" in extra
        assert extra["remaining_ms"] >= 0
