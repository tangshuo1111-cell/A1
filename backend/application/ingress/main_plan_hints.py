"""Lightweight hints from ingress for MainAgent.pan (§6.1).

Ingress may populate hints on low-confidence routes; run_chat_turn remains the
sole caller of main_agent.pan and merges hints into the final plan.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.main_agent.schema import AgnoCollaborationPlan


@dataclass(frozen=True)
class MainPlanHints:
    lane_override: str | None = None
    mode_override: str | None = None
    job_type: str | None = None
    max_rounds: int | None = None
    router_reason: str = ""


def apply_main_plan_hints(
    plan: AgnoCollaborationPlan,
    hints: MainPlanHints | None,
) -> AgnoCollaborationPlan:
    """Merge ingress hints into a full plan after the single MainAgent.pan call."""
    if hints is None:
        return plan
    updates: dict[str, object] = {}
    if hints.job_type is not None:
        updates["job_type"] = hints.job_type
    if hints.max_rounds is not None:
        updates["max_rounds"] = hints.max_rounds
    if not updates:
        return plan
    return replace(plan, **updates)
