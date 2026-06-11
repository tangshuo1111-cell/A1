"""Complex executor AnswerAgent stage (Round 2)."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from application.chat.budget_clock import (
    BudgetClock,
    format_ms as _format_ms,
    remaining_ms as _remaining_ms,
    with_budget_plan as _with_budget_plan,
)
from application.chat.executors.complex.complex_deadline import build_deadline_limited_answer
from application.chat.executors.complex_executor_delivery import run_complex_delivery_with_gate
from application.chat.history_buffer import ChatTurnDeps
from domain.session_types import SessionHistorySnapshot


def run_answer_stage(
    *,
    deps: ChatTurnDeps,
    message: str,
    plan: Any,
    bundle: Any,
    ingress: Any,
    shared_prep: Any | None,
    context_block: str | None,
    main_dec: Any,
    history_snapshot: SessionHistorySnapshot,
    session_id: str | None,
    use_knowledge: bool,
    v13_text_content: str | None,
    v13_title: str | None,
    v13_file_content: str | bytes | None,
    session_pending_kind: Any,
    budget_clock: BudgetClock,
    deadline_at: float,
    effective_mode: str,
    timing: dict[str, int],
) -> tuple[Any, Any, str, dict[str, Any], Any | None, str | None, str | None, list[str], int, bool]:
    knowledge_block, web_block, collab_trace = (
        bundle.knowledge_block,
        bundle.web_block,
        bundle.trace,
    )
    ts = time.perf_counter()
    answer_started_remaining_ms = _remaining_ms(deadline_at=deadline_at)
    plan = _with_budget_plan(
        plan,
        remaining_ms_hint=answer_started_remaining_ms,
        answer_started_remaining_ms=answer_started_remaining_ms,
    )
    retrieved_chunk_count = len(list(getattr(bundle, "retrieved_chunks", []) or []))
    kb_answer_budget_override = (
        effective_mode == "complex"
        and str(getattr(plan, "answer_mode", "") or "") == "knowledge_grounded"
        and retrieved_chunk_count >= 2
    )
    hard_deadline_limited = answer_started_remaining_ms <= 1200 and not kb_answer_budget_override
    complex_delivery_extra: dict[str, Any] = {}
    if hard_deadline_limited:
        answer_text, deadline_status = build_deadline_limited_answer(bundle)
        deadline_limitations = list(
            dict.fromkeys(
                list(getattr(bundle, "answer_limitations", []) or [])
                + ["达到 20 秒主响应截止，后续重处理已停止或转后台。"]
            )
        )
        try:
            bundle = replace(
                bundle,
                execution_status="partial" if deadline_status != "pending" else "ok",
                material_sufficiency="insufficient",
                answer_limitations=deadline_limitations,
            )
        except TypeError:
            bundle.execution_status = "partial" if deadline_status != "pending" else "ok"
            bundle.material_sufficiency = "insufficient"
            bundle.answer_limitations = deadline_limitations
        collab_trace = list(collab_trace) + [f"v20:deadline_short_circuit remaining_ms={answer_started_remaining_ms}"]
    else:
        if kb_answer_budget_override and answer_started_remaining_ms <= 1200:
            collab_trace = list(collab_trace) + [
                f"v20:deadline_override kb_answer remaining_ms={answer_started_remaining_ms} chunks={retrieved_chunk_count}"
            ]
        (
            bundle,
            answer_text,
            complex_delivery_extra,
            shared_prep,
            knowledge_block,
            web_block,
            collab_trace,
        ) = run_complex_delivery_with_gate(
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
            collab_trace=collab_trace,
        )
    timing["answer_ms"] = _format_ms((time.perf_counter() - ts) * 1000)
    return (
        plan,
        bundle,
        answer_text,
        complex_delivery_extra,
        shared_prep,
        knowledge_block,
        web_block,
        collab_trace,
        answer_started_remaining_ms,
        hard_deadline_limited,
    )
