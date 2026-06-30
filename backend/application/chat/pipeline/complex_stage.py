"""Pipeline stage 4 — complex orchestration (thin coordinator)."""

from __future__ import annotations

import logging

from application.chat.pipeline.complex_answer_stage import run_complex_answer_stage
from application.chat.pipeline.complex_collect_stage import run_complex_collect_stage
from application.chat.pipeline.complex_finalize_stage import run_complex_finalize_stage
from application.chat.pipeline.complex_plan_stage import run_complex_plan_stage
from application.chat.pipeline.pipeline_state import TurnPipelineState
from schemas import ChatTurnResult

logger = logging.getLogger("light_maqa")


def run_complex_stage(state: TurnPipelineState) -> ChatTurnResult:
    logger.info(
        "turn_stage_complex",
        extra={
            "lane": state.ingress.lane,
            "mode": state.ingress.mode,
            "effective_mode": state.effective_mode,
        },
    )
    plan, main_dec = run_complex_plan_stage(state)
    plan, bundle = run_complex_collect_stage(state, plan)
    (
        plan,
        bundle,
        answer_text,
        complex_delivery_extra,
        state.shared_prep,
        knowledge_block,
        web_block,
        collab_trace,
        answer_started_remaining_ms,
        hard_deadline_limited,
    ) = run_complex_answer_stage(state, plan=plan, bundle=bundle, main_dec=main_dec)
    return run_complex_finalize_stage(
        state,
        plan=plan,
        bundle=bundle,
        main_dec=main_dec,
        answer_text=answer_text,
        complex_delivery_extra=complex_delivery_extra,
        knowledge_block=knowledge_block,
        web_block=web_block,
        collab_trace=collab_trace,
        answer_started_remaining_ms=answer_started_remaining_ms,
        hard_deadline_limited=hard_deadline_limited,
    )
