"""Complex delivery — quality gate and optional feedback round actions."""

from __future__ import annotations

from typing import Any

from application.chat.budget_clock import BudgetClock
from application.chat.delivery_gate_flow import (
    gate_input_from_ingress,
    material_gate_facts_from_bundle,
    merge_delivery_extra,
    run_delivery_gate,
)
from application.chat.executors.complex.complex_deadline import FeedbackGatherContext
from application.chat.executors.complex.complex_feedback_impl import run_feedback_round_execution
from application.chat.history_buffer import ChatTurnDeps
from application.chat.shared_material_prep import run_shared_material_prep
from config.feature_flags import shared_retrieval_active
from domain.session_types import SessionHistorySnapshot

# Re-export for tests that patch the delivery namespace.
__all__ = ["run_feedback_round_execution", "run_complex_feedback_loop"]


def run_complex_feedback_loop(
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
    answer_text: str,
    delivery_extra: dict[str, Any],
) -> tuple[Any, str, dict[str, Any], Any | None, str | None, str | None]:
    gate_input = gate_input_from_ingress(
        ingress=ingress,
        executor_profile="complex",
        round_index=0,
        answer_text=answer_text,
        shared_prep=shared_prep,
        limitations=list(getattr(bundle, "answer_limitations", []) or []),
        material_facts=material_gate_facts_from_bundle(bundle, plan=plan),
        use_knowledge=use_knowledge,
        retrieved_chunks_count=len(list(getattr(bundle, "retrieved_chunks", []) or [])),
        pending_kind=str(getattr(session_pending_kind, "value", session_pending_kind) or "") or None,
        insufficient_evidence=bool(getattr(bundle, "insufficient_evidence", False)),
    )
    complex_outcome = run_delivery_gate(
        gate_input,
        ingress=ingress,
        shared_prep=shared_prep,
    )
    delivery_extra = complex_outcome.extra
    shared_prep_out = shared_prep

    if not complex_outcome.gate.need_second_round:
        return bundle, answer_text, delivery_extra, shared_prep_out, knowledge_block, web_block

    if complex_outcome.gate.need_more_material and shared_retrieval_active():
        new_prep = run_shared_material_prep(
            message=message,
            lane=ingress.lane,
            use_knowledge=use_knowledge,
            complex_candidate=bool(getattr(ingress, "complex_candidate", False)),
            clock=budget_clock,
            supplementary_retrieve=True,
        )
        if new_prep is not None:
            shared_prep_out = new_prep
            if new_prep.knowledge_block:
                knowledge_block = new_prep.knowledge_block

    bundle = run_feedback_round_execution(
        message,
        plan,
        bundle,
        deps,
        quality_gate=complex_outcome.gate,
        current_round=0,
        session_pending_kind=session_pending_kind,
        budget_clock=budget_clock,
        gather_context=FeedbackGatherContext(
            use_knowledge=use_knowledge,
            history_snapshot=history_snapshot,
            session_id=session_id,
            v13_text_content=v13_text_content,
            v13_title=v13_title,
            v13_file_content=v13_file_content,
            shared_prep=shared_prep_out,
        ),
    )
    knowledge_block = bundle.knowledge_block
    web_block = bundle.web_block

    if getattr(bundle, "final_answer_based_on_round", "round_0") == "round_1":
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
        gate_input_r1 = gate_input_from_ingress(
            ingress=ingress,
            executor_profile="complex",
            round_index=1,
            answer_text=answer_text,
            shared_prep=shared_prep_out,
            limitations=list(getattr(bundle, "answer_limitations", []) or []),
            material_facts=material_gate_facts_from_bundle(bundle, plan=plan),
            use_knowledge=use_knowledge,
            retrieved_chunks_count=len(list(getattr(bundle, "retrieved_chunks", []) or [])),
            pending_kind=str(getattr(session_pending_kind, "value", session_pending_kind) or "") or None,
            insufficient_evidence=bool(getattr(bundle, "insufficient_evidence", False)),
        )
        r1_outcome = run_delivery_gate(
            gate_input_r1,
            ingress=ingress,
            shared_prep=shared_prep_out,
        )
        delivery_extra = merge_delivery_extra(delivery_extra, r1_outcome)

    return bundle, answer_text, delivery_extra, shared_prep_out, knowledge_block, web_block
