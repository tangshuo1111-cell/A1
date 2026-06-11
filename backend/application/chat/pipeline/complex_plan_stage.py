"""Complex pipeline — Main/plan stage (Round 7)."""

from __future__ import annotations

from typing import Any

from application.chat.executors.complex_executor import run_main_stage as _run_main_stage
from application.chat.pipeline.pipeline_state import TurnPipelineState


def run_complex_plan_stage(state: TurnPipelineState) -> tuple[Any, Any]:
    return _run_main_stage(
        deps=state.deps,
        message=state.message,
        session_id=state.session_id,
        use_knowledge=state.use_knowledge,
        context_block=state.context_block,
        history_snapshot=state.history_snapshot,
        ingress=state.ingress,
        budget_clock=state.budget_clock,
        deadline_at=state.deadline_at,
        timing=state.timing,
        v13_file_content=state.v13_file_content,
        v13_title=state.v13_title,
        v13_text_content=state.v13_text_content,
    )
