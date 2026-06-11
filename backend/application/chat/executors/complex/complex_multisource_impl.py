"""Multisource complex round-0 answer (Round 2)."""

from __future__ import annotations

from dataclasses import is_dataclass
from typing import Any

from application.chat.autonomy_loop import append_autonomy_trace, autonomy_stop_reason_with_clock
from application.chat.complex_pending_mapping import (
    apply_multisource_budget_short_circuit,
    attach_complex_pending_context,
    complex_pending_kind_active,
)
from application.chat.pending_kind import PendingKind
from config.feature_flags import three_agent_autonomy_active


def run_multisource_round0_answer(
    message: str,
    plan: Any,
    bundle: Any,
    deps: Any,
    *,
    use_knowledge: bool,
    history_snapshot: Any,
    session_id: str | None,
    context_block: str | None,
    knowledge_block: str | None,
    web_block: str | None,
    main_dec: Any,
    v13_text_content: str | None,
    v13_title: str | None,
    v13_file_content: str | bytes | None,
    session_pending_kind: PendingKind = PendingKind.NONE,
    budget_clock: Any | None = None,
) -> tuple[Any, str]:
    """Produce round-0 answer only; second round is driven by quality_gate in run_chat_turn."""
    bundle = attach_complex_pending_context(bundle, session_pending=session_pending_kind)
    if not three_agent_autonomy_active():
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
        return bundle, answer_text
    stop_reason = autonomy_stop_reason_with_clock(
        plan,
        current_round=0,
        clock=budget_clock if complex_pending_kind_active() else None,
    )
    if stop_reason:
        bundle = append_autonomy_trace(
            bundle,
            plan=plan,
            round_index=0,
            trigger="budget_guard",
            requested_action="abort_and_finalize",
            requested_by="MainAgent",
            stop_reason=stop_reason,
            answer_check="pass",
        )
        if complex_pending_kind_active():
            bundle = apply_multisource_budget_short_circuit(bundle, stop_reason=stop_reason)
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
        return bundle, answer_text

    if is_dataclass(bundle):
        bundle = append_autonomy_trace(
            bundle,
            plan=plan,
            round_index=0,
            trigger="initial_dispatch",
            requested_action="await_quality_gate",
            requested_by="MainAgent",
            answer_check="pending",
            payload={"job_type": "multi_source_compare"},
        )

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
    return bundle, answer_text
