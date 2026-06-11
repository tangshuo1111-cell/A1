"""Complex delivery — round-0 answer production (rules vs multisource branch)."""

from __future__ import annotations

from typing import Any

from application.chat.budget_clock import BudgetClock
from application.chat.executors.complex.complex_multisource_impl import run_multisource_round0_answer
from application.chat.history_buffer import ChatTurnDeps
from domain.session_types import SessionHistorySnapshot


def produce_complex_round0_answer(
    *,
    message: str,
    plan: Any,
    bundle: Any,
    deps: ChatTurnDeps,
    use_knowledge: bool,
    history_snapshot: SessionHistorySnapshot,
    session_id: str | None,
    context_block: str | None,
    knowledge_block: str | None,
    web_block: str | None,
    main_dec: Any,
    v13_text_content: str | None,
    v13_title: str | None,
    v13_file_content: str | bytes | None,
    session_pending_kind: Any,
    budget_clock: BudgetClock,
    collab_trace: list[str],
) -> tuple[Any, str, str | None, str | None, list[str]]:
    is_multisource = getattr(plan, "job_type", "") == "multi_source_compare"
    if is_multisource:
        bundle, answer_text = run_multisource_round0_answer(
            message,
            plan,
            bundle,
            deps,
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
        )
        return bundle, answer_text, bundle.knowledge_block, bundle.web_block, list(bundle.trace)

    answer_text = deps.run_basic_qa(
        message,
        context_block=context_block,
        knowledge_block=knowledge_block,
        web_search_block=web_block,
        main_decision=main_dec,
        collaboration_plan=plan,
        material_bundle=bundle,
        clock=budget_clock,
    )
    return bundle, answer_text, knowledge_block, web_block, collab_trace
