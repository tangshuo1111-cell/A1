"""Turn execution pipeline — phased orchestration."""

from __future__ import annotations

import logging

from application.chat.budget_clock import SLA_BUDGET_MS, BudgetClock
from application.chat.domain.context import TurnContext
from application.chat.history_buffer import ChatTurnDeps
from application.chat.pipeline.complex_stage import run_complex_stage
from application.chat.pipeline.fast_stage import run_fast_stage
from application.chat.pipeline.ingress_stage import run_ingress_stage
from application.chat.pipeline.pipeline_state import TurnPipelineState
from application.chat.pipeline.session_stage import run_session_stage
from schemas import ChatTurnResult

logger = logging.getLogger("light_maqa")


def execute_turn(ctx: TurnContext, *, deps: ChatTurnDeps) -> ChatTurnResult:
    state = TurnPipelineState(ctx=ctx, deps=deps)
    state.budget_clock = ctx.clock or BudgetClock.start(SLA_BUDGET_MS)
    state.deadline_at = state.budget_clock.deadline_at

    run_session_stage(state)

    early = run_ingress_stage(state)
    if early is not None:
        logger.info("turn_pipeline_exit", extra={"stage": "ingress"})
        return early

    early = run_fast_stage(state)
    if early is not None:
        logger.info("turn_pipeline_exit", extra={"stage": "fast"})
        return early

    logger.info("turn_pipeline_enter_complex")
    return run_complex_stage(state)
