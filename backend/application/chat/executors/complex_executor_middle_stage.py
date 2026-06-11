"""Complex executor MiddleAgent stage (Round 2)."""

from __future__ import annotations

import time
from typing import Any

from application.chat.agent_invoke import invoke_middle_agent
from application.chat.budget_clock import (
    BudgetClock,
    format_ms as _format_ms,
    remaining_ms as _remaining_ms,
    with_budget_plan as _with_budget_plan,
)
from application.chat.history_buffer import ChatTurnDeps
from domain.session_types import SessionHistorySnapshot
from video.web_video_chat_context import web_video_long_asr_confirmed


def run_middle_stage(
    *,
    deps: ChatTurnDeps,
    message: str,
    plan: Any,
    use_knowledge: bool,
    shared_prep: Any | None,
    history_snapshot: SessionHistorySnapshot,
    session_id: str | None,
    v13_text_content: str | None,
    v13_title: str | None,
    v13_file_content: str | bytes | None,
    confirm_long_web_video_asr: bool,
    budget_clock: BudgetClock,
    deadline_at: float,
    timing: dict[str, int],
) -> tuple[Any, Any]:
    ts = time.perf_counter()
    wvac_tok = web_video_long_asr_confirmed.set(bool(confirm_long_web_video_asr))
    try:
        middle_result = invoke_middle_agent(
            deps.middle_agent,
            message=message,
            plan=plan,
            use_knowledge=use_knowledge,
            shared_prep=shared_prep,
            history_snapshot=history_snapshot,
            session_id=session_id,
            v13_text_content=v13_text_content,
            v13_title=v13_title,
            v13_file_content=v13_file_content,
            budget_clock=budget_clock,
        )
        bundle = middle_result.bundle
    finally:
        web_video_long_asr_confirmed.reset(wvac_tok)
    timing["middle_ms"] = _format_ms((time.perf_counter() - ts) * 1000)
    plan = _with_budget_plan(
        plan,
        remaining_ms_hint=_remaining_ms(deadline_at=deadline_at),
        middle_elapsed_ms=timing["middle_ms"],
    )
    return plan, bundle
