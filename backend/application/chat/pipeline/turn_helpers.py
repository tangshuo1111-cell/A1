"""Shared turn pipeline helpers (Cleanup C4)."""

from __future__ import annotations

import time
from typing import Any

from application.chat.approval_gate import is_commit_intent
from application.chat.approval_gate_flow import (
    build_approval_blocked_turn_result,
    evaluate_turn_approval,
    try_execute_commit_turn,
)
from application.chat.budget_clock import BudgetClock, format_ms as _format_ms
from application.chat.decision_arbitrator import (
    build_arbitration_event,
    resolve_session_pending_kind,
)
from application.chat.domain.decision import TurnDecision
from application.chat.domain.events import mode_arbitrated_event
from application.chat.domain.reason_codes import ARBITRATOR_INACTIVE
from application.chat.domain.runtime_state import TurnRuntimeState
from application.chat.turn_exit_gate import apply_turn_exit_to_chat_turn
from application.chat.turn_state_machine import TurnStateBundle, apply_event
from application.chat.trace_writer import append_arbitrator_trace
from config.feature_flags import is_enabled
from domain.session_types import PendingVideoText, PrevVideoRef
from schemas import ChatTurnResult


def arbitrate_turn_mode(
    *,
    ingress: Any,
    pending_video: PendingVideoText | None,
    prev_video: PrevVideoRef | None,
    budget_clock: BudgetClock,
    main_plan: Any | None = None,
    capability_advice: Any | None = None,
    turn_state: TurnStateBundle | None = None,
) -> tuple[str, str, list[dict[str, Any]], TurnStateBundle | None]:
    ts = time.perf_counter()
    if not is_enabled("ENABLE_DECISION_ARBITRATOR"):
        event = mode_arbitrated_event(
            mode=ingress.mode,
            reason_codes=(ARBITRATOR_INACTIVE,),
            detail_reason="arbitrator_inactive",
        )
    else:
        session_pending = resolve_session_pending_kind(
            pending_video=pending_video,
            prev_video=prev_video,
        )
        event = build_arbitration_event(
            session_pending=session_pending,
            ingress=ingress,
            main_plan=main_plan,
            capability_advice=capability_advice,
            clock=budget_clock,
        )
    decided_mode = event.mode or ingress.mode
    reason = event.detail_reason
    if turn_state is not None:
        turn_state.runtime, turn_state.decision = apply_event(
            turn_state.runtime,
            turn_state.decision,
            event,
        )
        decided_mode = turn_state.decision.mode
    trace = append_arbitrator_trace(
        [],
        name="mode_decision",
        decided_mode=decided_mode,
        reason=reason,
        elapsed_ms=_format_ms((time.perf_counter() - ts) * 1000),
    )
    return decided_mode, reason, trace, turn_state


def with_turn_exit_gate(
    result: ChatTurnResult,
    *,
    ingress: Any,
    effective_mode: str | None = None,
    hard_deadline_limited: bool = False,
    bundle_pending_item_present: bool = False,
    user_message: str | None = None,
) -> ChatTurnResult:
    return apply_turn_exit_to_chat_turn(
        result,
        ingress=ingress,
        effective_mode=effective_mode,
        hard_deadline_limited=hard_deadline_limited,
        bundle_pending_item_present=bundle_pending_item_present,
        user_message=user_message,
    )


def maybe_return_approval_or_commit(
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
