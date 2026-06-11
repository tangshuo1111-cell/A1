"""Shared fast-result wrapper for general-lane attempt modules."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from application.chat.executors.fast_executor_result import maybe_return_fast_result
from application.chat.history_buffer import ChatTurnDeps
from application.chat.turn_state_machine import TurnStateBundle


def finish_general_fast_attempt(
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
    v13_title: str | None,
    use_knowledge: bool,
    turn_state: TurnStateBundle | None,
) -> tuple[Any | None, str, dict[str, Any]]:
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
        use_knowledge=use_knowledge,
        turn_state=turn_state,
    )
