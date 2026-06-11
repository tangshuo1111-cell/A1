"""Complex pipeline — Middle/gather stage (Round 7)."""

from __future__ import annotations

from typing import Any

from application.chat.executors.complex_executor import run_middle_stage as _run_middle_stage
from application.chat.pipeline.pipeline_state import TurnPipelineState


def run_complex_collect_stage(state: TurnPipelineState, plan: Any) -> tuple[Any, Any]:
    return _run_middle_stage(
        deps=state.deps,
        message=state.message,
        plan=plan,
        use_knowledge=state.use_knowledge,
        shared_prep=state.shared_prep,
        history_snapshot=state.history_snapshot,
        session_id=state.session_id,
        v13_text_content=state.v13_text_content,
        v13_title=state.v13_title,
        v13_file_content=state.v13_file_content,
        confirm_long_web_video_asr=state.confirm_long_web_video_asr,
        budget_clock=state.budget_clock,
        deadline_at=state.deadline_at,
        timing=state.timing,
    )
