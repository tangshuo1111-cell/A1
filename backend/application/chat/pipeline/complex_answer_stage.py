"""Complex pipeline — Answer generation stage."""

from __future__ import annotations

from typing import Any

from application.chat.executors.complex_executor import run_answer_stage as _run_answer_stage
from application.chat.pipeline.pipeline_state import TurnPipelineState


def run_complex_answer_stage(
    state: TurnPipelineState,
    *,
    plan: Any,
    bundle: Any,
    main_dec: Any,
) -> tuple[Any, Any, str, dict[str, Any], Any | None, str | None, str | None, list[str], int, bool]:
    return _run_answer_stage(
        deps=state.deps,
        message=state.message,
        plan=plan,
        bundle=bundle,
        ingress=state.ingress,
        shared_prep=state.shared_prep,
        context_block=state.context_block,
        main_dec=main_dec,
        history_snapshot=state.history_snapshot,
        session_id=state.session_id,
        use_knowledge=state.use_knowledge,
        v13_text_content=state.v13_text_content,
        v13_title=state.v13_title,
        v13_file_content=state.v13_file_content,
        session_pending_kind=state.session_pending_kind,
        budget_clock=state.budget_clock,
        deadline_at=state.deadline_at,
        effective_mode=state.effective_mode,
        timing=state.timing,
    )
