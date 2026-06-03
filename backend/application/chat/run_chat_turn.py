"""主链一轮对话：Main -> Middle -> Answer；由 facade 注入 ChatTurnDeps。"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Any

from agents.history_context import PendingVideoText, PrevVideoRef, SessionHistorySnapshot
from application.chat.approval_gate import is_commit_intent
from application.chat.approval_gate_flow import (
    build_approval_blocked_turn_result,
    evaluate_turn_approval,
    try_execute_commit_turn,
)
from application.chat.async_entry import build_async_pending_result as _build_async_pending_result
from application.chat.budget_clock import (
    SLA_BUDGET_MS,
    BudgetClock,
    remaining_ms_from_clock,
)
from application.chat.budget_clock import (
    format_ms as _format_ms,
)
from application.chat.budget_clock import (
    remaining_ms as _remaining_ms,
)
from application.chat.budget_clock import (
    with_budget_plan as _with_budget_plan,
)
from application.chat.complex_path_entry import FeedbackGatherContext
from application.chat.complex_path_entry import (
    build_deadline_limited_answer as _build_deadline_limited_answer,
)
from application.chat.complex_path_entry import (
    run_feedback_round_execution as _run_feedback_round_execution,
)
from application.chat.complex_path_entry import (
    run_multisource_round0_answer as _run_multisource_round0_answer,
)
from application.chat.complex_pending_mapping import complex_pending_kind_active
from application.chat.decision_arbitrator import arbitrate_mode, resolve_session_pending_kind
from application.chat.delivery_gate_flow import (
    gate_input_from_ingress,
    run_delivery_gate,
)
from application.chat.exit_signals import (
    primary_path_signal_from_extra,
    set_material_sufficiency_signal,
    set_mode_signal,
)
from application.chat.fast_lane_gate import (
    fast_lane_gate_active,
    resolve_fast_lane_session_pending,
    should_allow_fast,
)
from application.chat.fast_path_entry import build_fast_result as _build_fast_result
from application.chat.fast_path_entry import build_fast_trace_extra as _build_fast_trace_extra
from application.chat.fast_path_entry import can_use_direct_fast_path as _can_use_direct_fast_path
from application.chat.fast_path_entry import run_document_fast_path as _run_document_fast_path
from application.chat.fast_path_entry import run_fast_llm_answer as _run_fast_llm_answer
from application.chat.fast_path_entry import run_general_fast_path as _run_general_fast_path
from application.chat.fast_path_entry import run_kb_fast_path as _run_kb_fast_path
from application.chat.fast_path_entry import run_video_fast_path as _run_video_fast_path
from application.chat.fast_path_entry import run_web_fast_path as _run_web_fast_path
from application.chat.fast_path_entry import (
    should_demote_fast_to_async as _should_demote_fast_to_async,
)
from application.chat.fast_path_entry import try_canned_fast_answer as _try_canned_fast_answer
from application.chat.fast_path_entry import try_fast_weather_answer as _try_fast_weather_answer
from application.chat.history_buffer import ChatTurnDeps
from application.chat.history_buffer import format_context as _format_context
from application.chat.history_buffer import history_key as _history_key
from application.chat.material_flow import material_trace_for_extra
from application.chat.path_labels import resolve_complex_primary_path
from application.chat.pending_kind import PendingKind
from application.chat.response_assembly import build_extra as _build_extra
from application.chat.shared_material_prep import (
    run_shared_material_prep,
    shared_prep_trace_extra,
)
from application.chat.trace_writer import (
    append_arbitrator_trace,
    apply_arbitrator_extra,
    apply_ingress_complex_extra,
    apply_profile_exit_extra,
)
from application.chat.turn_cache import (
    TurnCache,
    bind_turn_cache,
    current_turn_cache,
    reset_turn_cache,
    turn_cache_active,
)
from application.chat.turn_exit_extra import build_common_exit_extra
from application.chat.turn_exit_gate import apply_turn_exit_to_chat_turn
from application.chat.turn_facts import build_complex_turn_facts, quality_gate_from_extra
from application.ingress import resolve_lane_decision
from application.ingress.main_plan_hints import apply_main_plan_hints
from config.feature_flags import (
    fast_lane_active,
    ingress_router_active,
    is_enabled,
    shared_retrieval_active,
)
from observability import enrich_turn_extra
from schemas import ChatTurnResult
from services.capabilities.contracts import CapabilityFact
from services.capabilities.web import (  # noqa: F401 - 测试经 run_chat_turn.agno_web_service 打桩
    web_orchestration_service as agno_web_service,
)
from tasks.orchestration.turn_stitcher import (
    consume_stitch_slot,
    stitch_slot_to_pending_video,
    turn_stitcher_active,
)
from video.web_video_chat_context import web_video_long_asr_confirmed

# Response assembly lives in application.chat.response_assembly (imported above as _build_extra).
# ---------------------------------------------------------------------------
# Mode arbitration helper
# ---------------------------------------------------------------------------


def _arbitrate_turn_mode(
    *,
    ingress: Any,
    pending_video: PendingVideoText | None,
    prev_video: PrevVideoRef | None,
    budget_clock: BudgetClock,
    main_plan: Any | None = None,
    capability_advice: Any | None = None,
) -> tuple[str, str, list[dict[str, Any]]]:
    if not is_enabled("ENABLE_DECISION_ARBITRATOR"):
        return ingress.mode, "arbitrator_inactive", []
    ts = time.perf_counter()
    session_pending = resolve_session_pending_kind(
        pending_video=pending_video,
        prev_video=prev_video,
    )
    decided_mode, reason = arbitrate_mode(
        session_pending=session_pending,
        ingress=ingress,
        main_plan=main_plan,
        capability_advice=capability_advice,
        clock=budget_clock,
    )
    trace = append_arbitrator_trace(
        [],
        name="mode_decision",
        decided_mode=decided_mode,
        reason=reason,
        elapsed_ms=_format_ms((time.perf_counter() - ts) * 1000),
    )
    return decided_mode, reason, trace


def _finalize_fast_path_delivery(
    *,
    ingress: Any,
    shared_prep: Any | None,
    answer_text: str,
    lane_extra: dict[str, Any],
) -> tuple[bool, str, dict[str, Any]]:
    """Return (deliver_fast, effective_mode, merged_extra)."""
    gate_input = gate_input_from_ingress(
        ingress=ingress,
        executor_profile="fast",
        round_index=0,
        answer_text=answer_text,
        shared_prep=shared_prep,
        limitations=list(lane_extra.get("limitations") or []),
    )
    outcome = run_delivery_gate(
        gate_input,
        ingress=ingress,
        shared_prep=shared_prep,
        base_extra=lane_extra,
    )
    return outcome.deliver, ("complex" if outcome.upgrade_profile else "fast"), outcome.extra


def _run_complex_delivery_with_gate(
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
    """Unified complex path: round0 answer -> quality_gate -> optional feedback round."""
    is_multisource = getattr(plan, "job_type", "") == "multi_source_compare"
    if is_multisource:
        bundle, answer_text = _run_multisource_round0_answer(
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
        knowledge_block = bundle.knowledge_block
        web_block = bundle.web_block
        collab_trace = list(bundle.trace)
    else:
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

    gate_input = gate_input_from_ingress(
        ingress=ingress,
        executor_profile="complex",
        round_index=0,
        answer_text=answer_text,
        shared_prep=shared_prep,
        limitations=list(getattr(bundle, "answer_limitations", []) or []),
    )
    complex_outcome = run_delivery_gate(
        gate_input,
        ingress=ingress,
        shared_prep=shared_prep,
    )
    delivery_extra = complex_outcome.extra
    shared_prep_out = shared_prep

    if complex_outcome.gate.need_second_round:
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
        bundle = _run_feedback_round_execution(
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
        collab_trace = list(bundle.trace)
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

    return bundle, answer_text, delivery_extra, shared_prep_out, knowledge_block, web_block, collab_trace


def _finalize_complex_exit_extra(
    *,
    base_extra: dict[str, Any],
    timing: dict[str, Any],
    ingress: Any,
    effective_mode: str,
    elapsed_ms: int,
    shared_prep: Any | None,
    complex_delivery_extra: dict[str, Any],
    arbitrator_reason: str,
    arbitrator_trace: list[dict[str, Any]],
    answer_started_remaining_ms: int,
    budget_clock: BudgetClock,
    deadline_at: float,
) -> dict[str, Any]:
    extra = build_common_exit_extra(
        extra_base={
            **base_extra,
            **timing,
        },
        ingress=ingress,
        mode=effective_mode,
        executor_profile="complex" if effective_mode == "complex" else effective_mode,
        progress_stage="completed",
        elapsed_ms=elapsed_ms,
    )
    extra = apply_ingress_complex_extra(
        extra,
        complex_candidate=bool(getattr(ingress, "complex_candidate", False)),
        complex_triggers=list(getattr(ingress, "complex_triggers", []) or []),
        complex_reason_codes=list(getattr(ingress, "complex_reason_codes", []) or []),
    )
    extra.update(shared_prep_trace_extra(shared_prep))
    extra.update(complex_delivery_extra)
    if is_enabled("ENABLE_DECISION_ARBITRATOR"):
        extra = apply_arbitrator_extra(
            extra,
            ingress_mode=ingress.mode,
            decided_mode=effective_mode,
            decided_reason=arbitrator_reason,
            collaboration_trace=arbitrator_trace,
        )
    extra["router_source"] = ingress.router_source
    extra["router_confidence"] = ingress.router_confidence
    extra["router_fallback"] = ingress.router_fallback
    extra["router_decision_ms"] = ingress.router_decision_ms
    extra["router_request_id"] = ingress.request_id
    extra["sla_deadline_ms"] = SLA_BUDGET_MS
    extra["remaining_ms"] = remaining_ms_from_clock(budget_clock, deadline_at=deadline_at)
    if budget_clock is not None:
        extra["budget.remaining_ms_after_main"] = budget_clock.remaining_ms()
        extra["budget.remaining_ms_after_middle"] = budget_clock.remaining_ms()
        extra["budget.remaining_ms_after_answer"] = budget_clock.remaining_ms()
    extra["remaining_ms_at_answer_start"] = answer_started_remaining_ms
    extra["agent_timings"] = {
        "session_snapshot_ms": timing.get("session_snapshot_ms", 0),
        "main_ms": timing.get("main_ms", 0),
        "middle_ms": timing.get("middle_ms", 0),
        "answer_ms": timing.get("answer_ms", 0),
        "session_update_ms": timing.get("session_update_ms", 0),
        "extra_build_ms": timing.get("extra_build_ms", 0),
        "total_ms": elapsed_ms,
    }
    set_mode_signal(extra, effective_mode)
    set_material_sufficiency_signal(
        extra,
        str(base_extra.get("material_sufficiency") or "sufficient"),
    )
    return extra


def _build_complex_turn_result(
    *,
    answer_text: str,
    session_id: str | None,
    request_id: str | None,
    extra: dict[str, Any],
    elapsed_ms: int,
) -> dict[str, Any]:
    return {
        "ok": True,
        "answer": answer_text,
        "session_id": session_id,
        "request_id": request_id,
        "task_id": None,
        "answer_type": "basic_agno",
        "pipeline_ok": True,
        "extra": extra,
        "workflow_elapsed_ms": elapsed_ms,
    }


def _with_turn_exit_gate(
    result: ChatTurnResult,
    *,
    ingress: Any,
    effective_mode: str | None = None,
    hard_deadline_limited: bool = False,
    bundle_pending_item_present: bool = False,
) -> ChatTurnResult:
    return apply_turn_exit_to_chat_turn(
        result,
        ingress=ingress,
        effective_mode=effective_mode,
        hard_deadline_limited=hard_deadline_limited,
        bundle_pending_item_present=bundle_pending_item_present,
    )


def _maybe_return_approval_or_commit(
    *,
    message: str,
    session_id: str | None,
    request_id: str | None,
    confirm_long_web_video_asr: bool,
    use_knowledge: bool,
    v13_file_content: str | bytes | None,
    v13_text_content: str | None,
    ingress: Any,
    timing: dict[str, int],
    t0: float,
) -> dict[str, Any] | None:
    approval = evaluate_turn_approval(
        message=message,
        session_id=session_id,
        confirm_long_web_video_asr=confirm_long_web_video_asr,
        use_knowledge=use_knowledge,
        v13_file_content=v13_file_content,
        v13_text_content=v13_text_content,
    )
    if approval.blocked:
        elapsed = _format_ms((time.perf_counter() - t0) * 1000)
        pending_count = 0
        if session_id and is_commit_intent(message):
            from services.capabilities.knowledge import pending_ingestion_service

            pending_count = len(
                pending_ingestion_service.list_pending(session_id, only_committable=True)
            )
        return build_approval_blocked_turn_result(
            result=approval,
            message=message,
            session_id=session_id,
            request_id=request_id,
            elapsed_ms=elapsed,
            ingress=ingress,
            extra_base={"elapsed_ms": elapsed, **timing},
            pending_count=pending_count,
        )

    elapsed_after_approval = _format_ms((time.perf_counter() - t0) * 1000)
    return try_execute_commit_turn(
        message=message,
        session_id=session_id,
        request_id=request_id,
        elapsed_ms=elapsed_after_approval,
        ingress=ingress,
        extra_base={"elapsed_ms": elapsed_after_approval, **timing},
    )


def _build_async_turn_result(
    *,
    message: str,
    ingress: Any,
    effective_mode: str,
    arbitrator_reason: str,
    arbitrator_trace: list[dict[str, Any]],
    session_id: str | None,
    request_id: str | None,
    elapsed_ms: int,
    v13_title: str | None,
    merge_turn_obs: Callable[[dict[str, Any]], dict[str, Any]],
) -> ChatTurnResult:
    async_result = _build_async_pending_result(
        message=message,
        lane=ingress.lane,
        router_source=ingress.router_source,
        router_confidence=ingress.router_confidence,
        router_fallback=ingress.router_fallback,
        router_decision_ms=ingress.router_decision_ms,
        session_id=session_id,
        request_id=request_id,
        elapsed_ms=elapsed_ms,
        file_path=v13_title,
    )
    if is_enabled("ENABLE_DECISION_ARBITRATOR"):
        async_result["extra"] = apply_arbitrator_extra(
            async_result["extra"],
            ingress_mode=ingress.mode,
            decided_mode=effective_mode,
            decided_reason=arbitrator_reason,
            collaboration_trace=arbitrator_trace,
        )
    async_result["extra"] = merge_turn_obs(async_result.get("extra") or {})
    async_extra = async_result.get("extra") or {}
    async_extra.update(
        material_trace_for_extra(
            lane=ingress.lane,
            executor_profile="async",
        )
    )
    async_result["extra"] = async_extra
    return async_result


def _run_main_stage(
    *,
    deps: ChatTurnDeps,
    message: str,
    session_id: str | None,
    use_knowledge: bool,
    context_block: str | None,
    history_snapshot: SessionHistorySnapshot,
    ingress: Any,
    budget_clock: BudgetClock,
    deadline_at: float,
    timing: dict[str, int],
    v13_file_content: str | bytes | None = None,
    v13_title: str | None = None,
    v13_text_content: str | None = None,
) -> tuple[Any, Any]:
    ts = time.perf_counter()
    plan = deps.main_agent.pan(
        message, session_id=session_id, http_use_knowledge=use_knowledge,
        context_snippet=context_block or "", history=history_snapshot,
        v13_file_content=v13_file_content, v13_title=v13_title,
        v13_text_content=v13_text_content,
        clock=budget_clock,
    )
    if is_enabled("ENABLE_MAIN_PLAN_CACHE") and ingress.cached_main_hints is not None:
        plan = apply_main_plan_hints(plan, ingress.cached_main_hints)
    main_dec = plan.decision
    timing["main_ms"] = _format_ms((time.perf_counter() - ts) * 1000)
    plan = _with_budget_plan(
        plan,
        sla_budget_ms=SLA_BUDGET_MS,
        deadline_monotonic=deadline_at,
        remaining_ms_hint=_remaining_ms(deadline_at=deadline_at),
        main_elapsed_ms=timing["main_ms"],
    )
    return plan, main_dec


def _run_middle_stage(
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
        bundle = deps.middle_agent.caipan(
            message, plan=plan, http_use_knowledge=use_knowledge,
            shared_prep=shared_prep,
            history=history_snapshot, session_id=session_id or "",
            v13_text_content=v13_text_content, v13_title=v13_title,
            v13_file_content=v13_file_content,
            clock=budget_clock,
        )
    finally:
        web_video_long_asr_confirmed.reset(wvac_tok)
    timing["middle_ms"] = _format_ms((time.perf_counter() - ts) * 1000)
    plan = _with_budget_plan(
        plan,
        remaining_ms_hint=_remaining_ms(deadline_at=deadline_at),
        middle_elapsed_ms=timing["middle_ms"],
    )
    return plan, bundle


def _run_answer_stage(
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
        bundle.knowledge_block, bundle.web_block, bundle.trace,
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
        answer_text, deadline_status = _build_deadline_limited_answer(bundle)
        deadline_limitations = list(dict.fromkeys(
            list(getattr(bundle, "answer_limitations", []) or [])
            + ["达到 20 秒主响应截止，后续重处理已停止或转后台。"])
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
        ) = _run_complex_delivery_with_gate(
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


def _maybe_return_general_fast(
    *,
    message: str,
    use_knowledge: bool,
    v13_file_content: str | bytes | None,
    v13_text_content: str | None,
    v13_title: str | None,
    context_block: str | None,
    ingress: Any,
    shared_prep: Any | None,
    effective_mode: str,
    timing: dict[str, Any],
    t0: float,
    deps: ChatTurnDeps,
    key: str,
    session_id: str | None,
    request_id: str | None,
    hist: deque,
    merge_turn_obs: Callable[[dict[str, Any]], dict[str, Any]],
    finalize_turn_cache: Callable[[], None],
) -> tuple[Any | None, str, dict[str, Any]]:
    weather_fast = _try_fast_weather_answer(message)
    if (
        effective_mode == "fast"
        and weather_fast is not None
        and not use_knowledge
        and v13_file_content is None
        and not (v13_text_content or "").strip()
    ):
        answer_text, weather_extra = weather_fast
        return _maybe_return_fast_result(
            answer_text=answer_text,
            lane_extra={
                **weather_extra,
                "lane": "general",
                "capabilities_called": ["capability.general.weather_quick"],
                "fast_path": "weather",
            },
            ingress=ingress,
            shared_prep=shared_prep,
            effective_mode=effective_mode,
            timing=timing,
            t0=t0,
            deps=deps,
            key=key,
            message=message,
            session_id=session_id,
            request_id=request_id,
            hist=hist,
            merge_turn_obs=merge_turn_obs,
            finalize_turn_cache=finalize_turn_cache,
            v13_title=v13_title,
            use_knowledge=use_knowledge,
        )

    if effective_mode == "fast" and _can_use_direct_fast_path(
        message,
        use_knowledge=use_knowledge,
        v13_file_content=v13_file_content,
        v13_text_content=v13_text_content,
    ):
        canned = _try_canned_fast_answer(message)
        if effective_mode == "fast" and canned is not None:
            answer_text, canned_extra = canned
            return _maybe_return_fast_result(
                answer_text=answer_text,
                lane_extra={
                    **canned_extra,
                    "lane": "general",
                    "capabilities_called": ["capability.general.canned_answer"],
                    "fast_path": "canned",
                },
                ingress=ingress,
                shared_prep=shared_prep,
                effective_mode=effective_mode,
                timing=timing,
                t0=t0,
                deps=deps,
                key=key,
                message=message,
                session_id=session_id,
                request_id=request_id,
                hist=hist,
                merge_turn_obs=merge_turn_obs,
                finalize_turn_cache=finalize_turn_cache,
                v13_title=v13_title,
            )
        ts = time.perf_counter()
        answer_text = _run_fast_llm_answer(message, context_block=context_block)
        timing["fast_answer_ms"] = _format_ms((time.perf_counter() - ts) * 1000)
        return _maybe_return_fast_result(
            answer_text=answer_text,
            lane_extra={
                "fast_path": "direct_llm",
                "lane": "general",
                "capabilities_called": ["capability.general.direct_answer"],
                **_build_fast_trace_extra(
                    lane="general",
                    capabilities_called=["capability.general.direct_answer"],
                    elapsed_ms=_format_ms((time.perf_counter() - t0) * 1000),
                    exit_reason="general_direct_answer",
                ),
            },
            ingress=ingress,
            shared_prep=shared_prep,
            effective_mode=effective_mode,
            timing=timing,
            t0=t0,
            deps=deps,
            key=key,
            message=message,
            session_id=session_id,
            request_id=request_id,
            hist=hist,
            merge_turn_obs=merge_turn_obs,
            finalize_turn_cache=finalize_turn_cache,
            v13_title=v13_title,
            use_knowledge=use_knowledge,
        )

    return None, effective_mode, timing


def _run_lane_fast_candidate(
    *,
    ingress: Any,
    message: str,
    session_id: str | None,
    context_block: str | None,
    clock: BudgetClock,
    v13_text_content: str | None,
    v13_file_content: str | bytes | None,
    v13_title: str | None,
    shared_prep: Any | None,
) -> tuple[str, dict[str, Any]] | None:
    if ingress.lane == "video":
        return _run_video_fast_path(
            message=message,
            session_id=session_id,
            context_block=context_block,
            clock=clock,
        )
    if ingress.lane == "document":
        return _run_document_fast_path(
            message=message,
            context_block=context_block,
            v13_text_content=v13_text_content,
            v13_file_content=v13_file_content,
            v13_title=v13_title,
            clock=clock,
        )
    if ingress.lane == "web":
        return _run_web_fast_path(
            message=message,
            context_block=context_block,
            clock=clock,
        )
    if ingress.lane == "kb":
        return _run_kb_fast_path(
            message=message,
            context_block=context_block,
            clock=clock,
            shared_prep=shared_prep,
            ingress=ingress,
        )
    if ingress.lane == "general":
        return _run_general_fast_path(
            message=message,
            context_block=context_block,
        )
    return None


def _maybe_return_lane_fast(
    *,
    ingress: Any,
    effective_mode: str,
    session_id: str | None,
    pending_video: Any,
    prev_video_ref: Any,
    message: str,
    context_block: str | None,
    budget_clock: BudgetClock,
    v13_text_content: str | None,
    v13_file_content: str | bytes | None,
    v13_title: str | None,
    shared_prep: Any | None,
    timing: dict[str, Any],
    t0: float,
    deps: ChatTurnDeps,
    key: str,
    request_id: str | None,
    hist: deque,
    merge_turn_obs: Callable[[dict[str, Any]], dict[str, Any]],
    finalize_turn_cache: Callable[[], None],
) -> tuple[Any | None, str, dict[str, Any]]:
    if not (effective_mode == "fast" and fast_lane_active(ingress.lane)):
        return None, effective_mode, timing

    document_pending = False
    if fast_lane_gate_active() and session_id:
        from services.capabilities.knowledge import pending_ingestion_service

        document_pending = bool(
            pending_ingestion_service.list_pending(session_id, only_committable=True)
        )
    gate_pending = resolve_fast_lane_session_pending(
        pending_video=pending_video,
        prev_video=prev_video_ref,
        document_pending=document_pending,
    )
    if fast_lane_gate_active() and not should_allow_fast(
        session_pending=gate_pending,
        ingress=ingress,
        message=message,
    ):
        return None, "complex", timing

    fast_answer = _run_lane_fast_candidate(
        ingress=ingress,
        message=message,
        session_id=session_id,
        context_block=context_block,
        clock=budget_clock,
        v13_text_content=v13_text_content,
        v13_file_content=v13_file_content,
        v13_title=v13_title,
        shared_prep=shared_prep,
    )
    if fast_answer is None:
        return None, effective_mode, timing

    answer_text, lane_extra = fast_answer
    return _maybe_return_fast_result(
        answer_text=answer_text,
        lane_extra=lane_extra,
        ingress=ingress,
        shared_prep=shared_prep,
        effective_mode=effective_mode,
        timing=timing,
        t0=t0,
        deps=deps,
        key=key,
        message=message,
        session_id=session_id,
        request_id=request_id,
        hist=hist,
        merge_turn_obs=merge_turn_obs,
        finalize_turn_cache=finalize_turn_cache,
        v13_title=v13_title,
    )


def _maybe_return_fast_result(
    *,
    answer_text: str,
    lane_extra: dict[str, Any],
    ingress: Any,
    shared_prep: Any | None,
    effective_mode: str,
    timing: dict[str, Any],
    t0: float,
    deps: ChatTurnDeps,
    key: str,
    message: str,
    session_id: str | None,
    request_id: str | None,
    hist: deque,
    merge_turn_obs: Callable[[dict[str, Any]], dict[str, Any]],
    finalize_turn_cache: Callable[[], None],
    v13_title: str | None = None,
    use_knowledge: bool = False,
) -> tuple[Any | None, str, dict[str, Any]]:
    """Run delivery gate; return (fast_result|None, effective_mode, timing)."""
    elapsed = _format_ms((time.perf_counter() - t0) * 1000)
    lane_extra_merged = {
        **timing,
        **lane_extra,
        "answer_generated_at": datetime.now().isoformat(timespec="seconds"),
        "router_lane": ingress.lane,
        "mode": effective_mode,
        "executor_profile": "fast",
        "router_source": ingress.router_source,
        "router_confidence": ingress.router_confidence,
        "router_fallback": ingress.router_fallback,
    }
    if _should_demote_fast_to_async(lane_extra_merged):
        with deps.lock:
            hist.append((message.strip(), answer_text))
        existing_task = str(lane_extra_merged.get("task_id") or "").strip()
        prefilled_raw = lane_extra_merged.get("capability_fact")
        prefilled_fact = prefilled_raw if isinstance(prefilled_raw, CapabilityFact) else None
        async_pending = _build_async_pending_result(
            message=message,
            lane=ingress.lane,
            router_source=ingress.router_source,
            router_confidence=ingress.router_confidence,
            router_fallback=ingress.router_fallback,
            router_decision_ms=ingress.router_decision_ms,
            session_id=session_id,
            request_id=request_id,
            elapsed_ms=elapsed,
            file_path=v13_title,
            prefilled_fact=prefilled_fact,
            existing_task_id=existing_task or None,
            queue_backend=str(lane_extra_merged.get("queue_backend") or "") or None,
        )
        async_extra = apply_profile_exit_extra(
            async_pending.get("extra") or {},
            profile_exit_reason=str(lane_extra_merged.get("fast_exit_reason") or "fast_demote_async"),
            from_profile="fast",
            to_profile="async",
        )
        async_extra.update(
            material_trace_for_extra(
                shared_prep=shared_prep,
                lane=ingress.lane,
                use_knowledge=use_knowledge,
                executor_profile="async",
                has_fast_material=bool(answer_text),
            )
        )
        async_pending["extra"] = merge_turn_obs(async_extra)
        finalize_turn_cache()
        return async_pending, effective_mode, timing

    deliver_fast, upgraded_mode, lane_extra_merged = _finalize_fast_path_delivery(
        ingress=ingress,
        shared_prep=shared_prep,
        answer_text=answer_text,
        lane_extra=lane_extra_merged,
    )
    if not deliver_fast and upgraded_mode == "complex":
        timing["fast_profile_ms"] = _format_ms((time.perf_counter() - t0) * 1000)
        return None, "complex", timing

    lane_extra_merged.update(
        material_trace_for_extra(
            shared_prep=shared_prep,
            lane=ingress.lane,
            use_knowledge=use_knowledge or ingress.lane == "kb",
            executor_profile="fast",
            has_fast_material=bool(answer_text),
        )
    )

    with deps.lock:
        hist.append((message.strip(), answer_text))
    merged_extra = merge_turn_obs(lane_extra_merged)
    finalize_turn_cache()
    return _build_fast_result(
        answer=answer_text,
        session_id=session_id,
        request_id=request_id,
        elapsed_ms=elapsed,
        extra=merged_extra,
    ), effective_mode, timing


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


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
    t0 = time.perf_counter()
    budget_clock = BudgetClock.start(SLA_BUDGET_MS)
    deadline_at = budget_clock.deadline_at
    key = _history_key(session_id)
    timing: dict[str, int] = {}
    turn_cache_token = None
    if turn_cache_active():
        turn_cache_token = bind_turn_cache(TurnCache(request_id=request_id))
    stitch_applied = False

    # --- Stage 1: session snapshot ---
    ts = time.perf_counter()
    with deps.lock:
        hist = deps.histories.setdefault(key, deque(maxlen=deps.max_history_pairs))
        context_block = _format_context(hist)
        prev_video_ref = deps.session_prev_video.get(key)
        pending_video = deps.session_pending_video.get(key)
        if turn_stitcher_active() and pending_video is None:
            stitch_slot = consume_stitch_slot(session_id)
            if stitch_slot is not None and stitch_slot.lane == "video":
                pending_video = stitch_slot_to_pending_video(stitch_slot)
                deps.session_pending_video[key] = pending_video
                stitch_applied = True
        history_snapshot = SessionHistorySnapshot.from_history(
            session_id=session_id, context_block=context_block,
            turns=len(hist), prev_video=prev_video_ref,
            pending_video_text=pending_video,
        )
    timing["session_snapshot_ms"] = _format_ms((time.perf_counter() - ts) * 1000)

    ingress = resolve_lane_decision(
        message=message,
        session_id=session_id,
        request_id=request_id,
        use_knowledge=use_knowledge,
        v13_file_content=v13_file_content,
        v13_text_content=v13_text_content,
        main_agent=deps.main_agent,
        context_snippet=context_block or "",
        clock=budget_clock,
    )
    turn_cache = current_turn_cache()
    if turn_cache is not None:
        turn_cache.set_lane(ingress.lane)
    timing["router_decision_ms"] = ingress.router_decision_ms

    early_turn = _maybe_return_approval_or_commit(
        message=message,
        session_id=session_id,
        request_id=request_id,
        confirm_long_web_video_asr=confirm_long_web_video_asr,
        use_knowledge=use_knowledge,
        v13_file_content=v13_file_content,
        v13_text_content=v13_text_content,
        ingress=ingress,
        timing=timing,
        t0=t0,
    )
    if early_turn is not None:
        if turn_cache_token is not None:
            reset_turn_cache(turn_cache_token)
        return _with_turn_exit_gate(early_turn, ingress=ingress)

    effective_mode, arbitrator_reason, arbitrator_trace = _arbitrate_turn_mode(
        ingress=ingress,
        pending_video=pending_video,
        prev_video=prev_video_ref,
        budget_clock=budget_clock,
    )
    session_pending_kind = resolve_session_pending_kind(
        pending_video=pending_video,
        prev_video=prev_video_ref,
    )

    shared_prep = None
    if shared_retrieval_active():
        shared_prep = run_shared_material_prep(
            message=message,
            lane=ingress.lane,
            use_knowledge=use_knowledge,
            complex_candidate=bool(getattr(ingress, "complex_candidate", False)),
            clock=budget_clock,
        )

    def _merge_turn_obs(extra: dict[str, Any]) -> dict[str, Any]:
        tc = current_turn_cache()
        if tc is not None:
            stats = tc.hits()
            extra["turn_cache.hits"] = int(stats.get("hits", 0))
            extra["turn_cache.misses"] = int(stats.get("misses", 0))
            from agents.answer_agent.llm_exec import load_answer_llm_metrics

            extra.update(load_answer_llm_metrics())
        if stitch_applied:
            extra["turn_stitch.applied"] = True
        kb_calls = 1 if int(extra.get("v15_retrieved_chunks_count") or 0) > 0 else 0
        if tc is not None and int(extra.get("turn_cache.hits") or 0) > 0:
            kb_calls = max(kb_calls, 1)
        return enrich_turn_extra(extra, main_plan_call_count=1, kb_retrieve_call_count=kb_calls)

    def _finalize_turn_cache() -> None:
        if turn_cache_token is not None:
            reset_turn_cache(turn_cache_token)

    if effective_mode == "async":
        elapsed = _format_ms((time.perf_counter() - t0) * 1000)
        async_result = _build_async_turn_result(
            message=message,
            ingress=ingress,
            effective_mode=effective_mode,
            arbitrator_reason=arbitrator_reason,
            arbitrator_trace=arbitrator_trace,
            session_id=session_id,
            request_id=request_id,
            elapsed_ms=elapsed,
            v13_title=v13_title,
            merge_turn_obs=_merge_turn_obs,
        )
        _finalize_turn_cache()
        return _with_turn_exit_gate(
            async_result,
            ingress=ingress,
            effective_mode=effective_mode,
        )

    if ingress_router_active():
        if fast_lane_active("general"):
            fast_result, effective_mode, timing = _maybe_return_general_fast(
                message=message,
                use_knowledge=use_knowledge,
                v13_file_content=v13_file_content,
                v13_text_content=v13_text_content,
                v13_title=v13_title,
                context_block=context_block,
                ingress=ingress,
                shared_prep=shared_prep,
                effective_mode=effective_mode,
                timing=timing,
                t0=t0,
                deps=deps,
                key=key,
                session_id=session_id,
                request_id=request_id,
                hist=hist,
                merge_turn_obs=_merge_turn_obs,
                finalize_turn_cache=_finalize_turn_cache,
            )
            if fast_result is not None:
                return _with_turn_exit_gate(
                    fast_result,
                    ingress=ingress,
                    effective_mode=effective_mode,
                )

        fast_result, effective_mode, timing = _maybe_return_lane_fast(
            ingress=ingress,
            effective_mode=effective_mode,
            session_id=session_id,
            pending_video=pending_video,
            prev_video_ref=prev_video_ref,
            message=message,
            context_block=context_block,
            budget_clock=budget_clock,
            v13_text_content=v13_text_content,
            v13_file_content=v13_file_content,
            v13_title=v13_title,
            shared_prep=shared_prep,
            timing=timing,
            t0=t0,
            deps=deps,
            key=key,
            request_id=request_id,
            hist=hist,
            merge_turn_obs=_merge_turn_obs,
            finalize_turn_cache=_finalize_turn_cache,
        )
        if fast_result is not None:
            return _with_turn_exit_gate(
                fast_result,
                ingress=ingress,
                effective_mode=effective_mode,
            )

    plan, main_dec = _run_main_stage(
        deps=deps,
        message=message,
        session_id=session_id,
        use_knowledge=use_knowledge,
        context_block=context_block,
        history_snapshot=history_snapshot,
        ingress=ingress,
        budget_clock=budget_clock,
        deadline_at=deadline_at,
        timing=timing,
        v13_file_content=v13_file_content,
        v13_title=v13_title,
        v13_text_content=v13_text_content,
    )
    plan, bundle = _run_middle_stage(
        deps=deps,
        message=message,
        plan=plan,
        use_knowledge=use_knowledge,
        shared_prep=shared_prep,
        history_snapshot=history_snapshot,
        session_id=session_id,
        v13_text_content=v13_text_content,
        v13_title=v13_title,
        v13_file_content=v13_file_content,
        confirm_long_web_video_asr=confirm_long_web_video_asr,
        budget_clock=budget_clock,
        deadline_at=deadline_at,
        timing=timing,
    )
    (
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
    ) = _run_answer_stage(
        deps=deps,
        message=message,
        plan=plan,
        bundle=bundle,
        ingress=ingress,
        shared_prep=shared_prep,
        context_block=context_block,
        main_dec=main_dec,
        history_snapshot=history_snapshot,
        session_id=session_id,
        use_knowledge=use_knowledge,
        v13_text_content=v13_text_content,
        v13_title=v13_title,
        v13_file_content=v13_file_content,
        session_pending_kind=session_pending_kind,
        budget_clock=budget_clock,
        deadline_at=deadline_at,
        effective_mode=effective_mode,
        timing=timing,
    )

    # --- Stage 5: session update ---
    ts = time.perf_counter()
    with deps.lock:
        hist.append((message.strip(), answer_text))
        _v13_video_pending = (
            bundle.pending_item is not None
            and getattr(bundle.pending_item, "source_type", "") in ("local_video", "web_video")
        )
        if bundle.v11_pending_video_text is not None and not _v13_video_pending:
            deps.session_pending_video[key] = bundle.v11_pending_video_text  # type: ignore[assignment]
        elif bundle.v11_saved_to_kb:
            deps.session_pending_video.pop(key, None)
        if bundle.v11_saved_to_kb and bundle.v11_saved_source_id:
            deps.session_prev_video[key] = PrevVideoRef(
                source_id=bundle.v11_saved_source_id,
                basename=bundle.v11_saved_title,
                path=None,
            )
    timing["session_update_ms"] = _format_ms((time.perf_counter() - ts) * 1000)

    # --- Stage 6: output guard ---
    from config.cost_rule import COST

    if len(answer_text) > COST.max_output_chars:
        answer_text = answer_text[: COST.max_output_chars]

    # --- Stage 7: build response ---
    ts = time.perf_counter()
    extra = _build_extra(
        message, plan, bundle, main_dec, answer_text, deps,
        use_knowledge=use_knowledge, knowledge_block=knowledge_block,
        web_block=web_block, collab_trace=collab_trace,
        history_snapshot=history_snapshot,
    )
    timing["extra_build_ms"] = _format_ms((time.perf_counter() - ts) * 1000)
    elapsed_ms = _format_ms((time.perf_counter() - t0) * 1000)
    extra = _finalize_complex_exit_extra(
        base_extra=extra,
        timing=timing,
        ingress=ingress,
        effective_mode=effective_mode,
        elapsed_ms=elapsed_ms,
        shared_prep=shared_prep,
        complex_delivery_extra=complex_delivery_extra,
        arbitrator_reason=arbitrator_reason,
        arbitrator_trace=arbitrator_trace,
        answer_started_remaining_ms=answer_started_remaining_ms,
        budget_clock=budget_clock,
        deadline_at=deadline_at,
    )

    extra = _merge_turn_obs(extra)
    _finalize_turn_cache()
    facts = build_complex_turn_facts(
        bundle=bundle,
        extra=extra,
        ingress=ingress,
        effective_mode=effective_mode,
        history_snapshot=history_snapshot,
        session_pending_kind=session_pending_kind,
        hard_deadline_limited=hard_deadline_limited,
        public_mode=effective_mode,
        executor_profile="complex" if effective_mode == "complex" else effective_mode,
        primary_path_candidate=str(
            primary_path_signal_from_extra(extra)
            or extra.get("answer_view_path")
            or resolve_complex_primary_path(bundle)
            or "default"
        ),
        material_sufficiency=str(getattr(bundle, "material_sufficiency", "sufficient") or "sufficient"),
        quality_gate=quality_gate_from_extra(complex_delivery_extra),
        limitations=tuple(getattr(bundle, "answer_limitations", []) or ()),
    )
    if not complex_pending_kind_active():
        facts = replace(facts, pending_kind=PendingKind.NONE)
    return apply_turn_exit_to_chat_turn(
        _build_complex_turn_result(
            answer_text=answer_text,
            session_id=session_id,
            request_id=request_id,
            extra=extra,
            elapsed_ms=elapsed_ms,
        ),
        facts=facts,
        ingress=ingress,
        effective_mode=effective_mode,
        hard_deadline_limited=hard_deadline_limited,
        bundle_pending_item_present=getattr(bundle, "pending_item", None) is not None,
    )
