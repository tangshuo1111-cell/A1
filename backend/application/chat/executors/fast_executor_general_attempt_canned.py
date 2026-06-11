"""Canned quick-answer attempt for general fast lane."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from application.chat.executors.fast_executor_general_attempt_common import (
    finish_general_fast_attempt,
)
from application.chat.history_buffer import ChatTurnDeps
from application.chat.turn_state_machine import TurnStateBundle


def attempt_canned_fast(
    *,
    message: str,
    canned: tuple[str, dict[str, Any]] | None,
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
    turn_state: TurnStateBundle | None,
) -> tuple[Any | None, str, dict[str, Any]] | None:
    if effective_mode != "fast" or canned is None:
        return None
    answer_text, canned_extra = canned
    return finish_general_fast_attempt(
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
        use_knowledge=False,
        turn_state=turn_state,
    )
