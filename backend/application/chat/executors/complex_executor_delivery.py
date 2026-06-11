"""Complex executor delivery — thin coordinator (Round 2 + R20 split)."""

from __future__ import annotations

from typing import Any

from application.chat.budget_clock import BudgetClock
from application.chat.executors.complex_executor_delivery_feedback import (
    run_complex_feedback_loop,
    run_feedback_round_execution,
)
from application.chat.executors.complex_executor_delivery_round0 import (
    produce_complex_round0_answer,
)
from application.chat.history_buffer import ChatTurnDeps
from domain.session_types import SessionHistorySnapshot

__all__ = ["run_complex_delivery_with_gate", "run_feedback_round_execution"]


def run_complex_delivery_with_gate(
    *,
    message: str,
    plan: Any,
    bundle: Any,
    deps: ChatTurnDeps,
    ingress: Any,
    shared_prep: Any | None,
    context_block: str | None,
    knowledge_block: str | None,
    web_block: str | None,
    main_dec: Any,
    history_snapshot: SessionHistorySnapshot,
    session_id: str | None,
    use_knowledge: bool,
    v13_text_content: str | None,
    v13_title: str | None,
    v13_file_content: str | bytes | None,
    session_pending_kind: Any,
    budget_clock: BudgetClock,
    collab_trace: list[str],
) -> tuple[Any, str, dict[str, Any], Any | None, str | None, str | None, list[str]]:
    bundle, answer_text, knowledge_block, web_block, collab_trace = produce_complex_round0_answer(
        message=message,
        plan=plan,
        bundle=bundle,
        deps=deps,
        use_knowledge=use_knowledge,
        history_snapshot=history_snapshot,
        session_id=session_id,
        context_block=context_block,
        knowledge_block=knowledge_block,
        web_block=web_block,
        main_dec=main_dec,
        v13_text_content=v13_text_content,
        v13_title=v13_title,
        v13_file_content=v13_file_content,
        session_pending_kind=session_pending_kind,
        budget_clock=budget_clock,
        collab_trace=collab_trace,
    )
    bundle, answer_text, delivery_extra, shared_prep_out, knowledge_block, web_block = run_complex_feedback_loop(
        message=message,
        plan=plan,
        bundle=bundle,
        deps=deps,
        ingress=ingress,
        shared_prep=shared_prep,
        context_block=context_block,
        knowledge_block=knowledge_block,
        web_block=web_block,
        main_dec=main_dec,
        history_snapshot=history_snapshot,
        session_id=session_id,
        use_knowledge=use_knowledge,
        v13_text_content=v13_text_content,
        v13_title=v13_title,
        v13_file_content=v13_file_content,
        session_pending_kind=session_pending_kind,
        budget_clock=budget_clock,
        answer_text=answer_text,
        delivery_extra={},
    )
    if getattr(bundle, "trace", None):
        collab_trace = list(bundle.trace)
    return bundle, answer_text, delivery_extra, shared_prep_out, knowledge_block, web_block, collab_trace
