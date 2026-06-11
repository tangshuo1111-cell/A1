"""Lane-specific fast path dispatch from executor (Round 1)."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from application.chat.budget_clock import BudgetClock
from application.chat.executors.fast_executor_result import maybe_return_fast_result
from application.chat.executors.fast_lanes.dispatch import run_lane_fast_candidate
from application.chat.fast_lane_gate import (
    build_fast_lane_event,
    fast_lane_gate_active,
    resolve_fast_lane_session_pending,
)
from application.chat.history_buffer import ChatTurnDeps
from application.chat.turn_state_machine import TurnStateBundle, apply_event
from config.feature_flags import fast_lane_active


def maybe_return_lane_fast(
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
    turn_state: TurnStateBundle | None = None,
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
    if fast_lane_gate_active():
        fast_event = build_fast_lane_event(
            session_pending=gate_pending,
            ingress=ingress,
            message=message,
        )
        if fast_event is not None:
            if turn_state is not None:
                turn_state.runtime, turn_state.decision = apply_event(
                    turn_state.runtime,
                    turn_state.decision,
                    fast_event,
                )
                return None, turn_state.decision.mode, timing
            return None, "complex", timing

    fast_answer = run_lane_fast_candidate(
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
    return maybe_return_fast_result(
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
        turn_state=turn_state,
    )
