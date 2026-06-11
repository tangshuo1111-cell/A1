"""Fast executor result assembly and async demotion (Round 1)."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Any

from application.chat.budget_clock import format_ms as _format_ms
from application.chat.executors.async_path.build_pending import build_async_pending_result
from application.chat.executors.fast_delivery import (
    build_fast_result as _build_fast_result,
    should_demote_fast_to_async as _should_demote_fast_to_async,
)
from application.chat.executors.fast_executor_delivery import finalize_fast_path_delivery
from application.chat.history_buffer import ChatTurnDeps
from application.chat.material_flow import material_trace_for_extra
from application.chat.trace_writer import apply_profile_exit_extra
from application.chat.turn_state_machine import TurnStateBundle
from services.capabilities.contracts import CapabilityFact


def maybe_return_fast_result(
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
    turn_state: TurnStateBundle | None = None,
) -> tuple[Any | None, str, dict[str, Any]]:
    """Run delivery gate; return (fast_result|None, effective_mode, timing)."""
    from application.chat.answer_text_polish import polish_user_answer

    answer_text = polish_user_answer(answer_text)
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
        async_pending = build_async_pending_result(
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

    deliver_fast, upgraded_mode, lane_extra_merged = finalize_fast_path_delivery(
        ingress=ingress,
        shared_prep=shared_prep,
        answer_text=answer_text,
        lane_extra=lane_extra_merged,
        turn_state=turn_state,
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
