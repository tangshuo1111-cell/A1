"""Chat main-chain orchestrator — sole runtime entry (Round 3+)."""

from __future__ import annotations

from application.chat.budget_clock import BudgetClock
from application.chat.domain.context import TurnContext, TurnFlags, UploadMeta
from application.chat.history_buffer import ChatTurnDeps
from application.chat.pipeline.turn_pipeline import execute_turn as _execute_turn
from schemas import ChatTurnResult


def build_turn_context(
    message: str,
    *,
    session_id: str | None,
    request_id: str | None = None,
    use_knowledge: bool = False,
    v13_file_content: str | bytes | None = None,
    v13_text_content: str | None = None,
    v13_title: str | None = None,
    confirm_long_web_video_asr: bool = False,
    clock: BudgetClock | None = None,
) -> TurnContext:
    return TurnContext(
        user_input=message,
        session_id=session_id,
        request_id=request_id,
        upload=UploadMeta(
            file_content=v13_file_content,
            text_content=v13_text_content,
            title=v13_title,
        ),
        flags=TurnFlags(
            use_knowledge=use_knowledge,
            confirm_long_web_video_asr=confirm_long_web_video_asr,
        ),
        clock=clock,
    )


class TurnOrchestrator:
    """Single main-chain entry — routes one turn through ingress, gates, and executors."""

    @classmethod
    def run(cls, ctx: TurnContext, *, deps: ChatTurnDeps) -> ChatTurnResult:
        return _execute_turn(ctx, deps=deps)


def run_agno_chat_turn_impl(
    message: str,
    *,
    session_id: str | None,
    request_id: str | None = None,
    use_knowledge: bool = False,
    v13_file_content: str | bytes | None = None,
    v13_text_content: str | None = None,
    v13_title: str | None = None,
    confirm_long_web_video_asr: bool = False,
    deps: ChatTurnDeps,
) -> ChatTurnResult:
    ctx = build_turn_context(
        message,
        session_id=session_id,
        request_id=request_id,
        use_knowledge=use_knowledge,
        v13_file_content=v13_file_content,
        v13_text_content=v13_text_content,
        v13_title=v13_title,
        confirm_long_web_video_asr=confirm_long_web_video_asr,
    )
    return TurnOrchestrator.run(ctx, deps=deps)
