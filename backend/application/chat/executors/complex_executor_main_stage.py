"""Complex executor MainAgent stage (Round 2)."""

from __future__ import annotations

import time
from typing import Any

from application.chat.agent_invoke import invoke_main_agent
from application.chat.budget_clock import (
    SLA_BUDGET_MS,
    BudgetClock,
)
from application.chat.budget_clock import (
    format_ms as _format_ms,
)
from application.chat.budget_clock import (
    remaining_ms as _remaining_ms,
)
from application.chat.budget_clock import (
    with_budget_plan as _with_budget_plan,
)
from application.chat.history_buffer import ChatTurnDeps
from application.ingress.main_plan_hints import apply_main_plan_hints
from config.feature_flags import is_enabled
from domain.session_types import SessionHistorySnapshot


def run_main_stage(
    *,
    deps: ChatTurnDeps,
    message: str,
    session_id: str | None,
    use_knowledge: bool,
    context_block: str | None,
    history_snapshot: SessionHistorySnapshot,
    ingress: Any,
    budget_clock: BudgetClock,
    deadline_at: float,
    timing: dict[str, int],
    v13_file_content: str | bytes | None = None,
    v13_title: str | None = None,
    v13_text_content: str | None = None,
) -> tuple[Any, Any]:
    ts = time.perf_counter()
    main_result = invoke_main_agent(
        deps.main_agent,
        message=message,
        session_id=session_id,
        use_knowledge=use_knowledge,
        context_block=context_block,
        history_snapshot=history_snapshot,
        budget_clock=budget_clock,
        v13_file_content=v13_file_content,
        v13_title=v13_title,
        v13_text_content=v13_text_content,
    )
    plan = main_result.plan
    if is_enabled("ENABLE_MAIN_PLAN_CACHE") and ingress.cached_main_hints is not None:
        plan = apply_main_plan_hints(plan, ingress.cached_main_hints)
    main_dec = plan.decision
    timing["main_ms"] = _format_ms((time.perf_counter() - ts) * 1000)
    plan = _with_budget_plan(
        plan,
        sla_budget_ms=SLA_BUDGET_MS,
        deadline_monotonic=deadline_at,
        remaining_ms_hint=_remaining_ms(deadline_at=deadline_at),
        main_elapsed_ms=timing["main_ms"],
    )
    return plan, main_dec
