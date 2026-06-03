from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_AUTONOMY_ROUNDS = 4

BUDGET_DEFAULTS: dict[str, dict[str, int]] = {
    "fast": {
        "budget_remaining_ms": 8000,
        "llm_calls_remaining": 2,
        "tool_calls_remaining": 4,
    },
    "complex": {
        "budget_remaining_ms": 45000,
        "llm_calls_remaining": 12,
        "tool_calls_remaining": 20,
    },
    "async_per_task": {
        "budget_remaining_ms": 600000,   # 10 min
        "llm_calls_remaining": 8,
        "tool_calls_remaining": 16,
    },
}

FUSE_RULES: dict[str, Any] = {
    "min_remaining_ms_to_continue": 500,
    "stop_on_zero_llm_calls": True,
    "stop_on_zero_tool_calls": True,
    "max_autonomy_rounds": MAX_AUTONOMY_ROUNDS,
}


@dataclass(frozen=True)
class BudgetPolicyDefaults:
    min_remaining_ms_to_continue: int = 500
    default_llm_calls_remaining: int = 4
    default_tool_calls_remaining: int = 6


BUDGET_POLICY_DEFAULTS = BudgetPolicyDefaults()
