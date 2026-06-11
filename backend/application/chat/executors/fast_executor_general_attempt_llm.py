"""Direct LLM attempt for general fast lane."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from typing import Any

from application.chat.budget_clock import format_ms as _format_ms
from application.chat.executors.fast_delivery import (
    build_fast_trace_extra as _build_fast_trace_extra,
)
from application.chat.executors.fast_executor_general_attempt_common import (
    finish_general_fast_attempt,
)
from application.chat.executors.fast_lanes.fast_llm import run_fast_llm_answer
from application.chat.history_buffer import ChatTurnDeps
from application.chat.turn_state_machine import TurnStateBundle


def attempt_direct_llm_fast(
    *,
    message: str,
    context_block: str | None,
    effective_mode: str,
    ingress: Any,
    shared_prep: Any | None,
    timing: dict[str, Any],
    t0: float,
    deps: ChatTurnDeps,
    key: str,
    session_id: str | None,
    request_id: str | None,
    hist: deque,
    merge_turn_obs: Callable[[dict[str, Any]], dict[str, Any]],
    finalize_turn_cache: Callable[[], None],
    v13_title: str | None,
    use_knowledge: bool,
    turn_state: TurnStateBundle | None,
) -> tuple[Any | None, str, dict[str, Any]]:
    ts = time.perf_counter()
    answer_text = run_fast_llm_answer(message, context_block=context_block)
    timing["fast_answer_ms"] = _format_ms((time.perf_counter() - ts) * 1000)
    return finish_general_fast_attempt(
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
        turn_state=turn_state,
    )
