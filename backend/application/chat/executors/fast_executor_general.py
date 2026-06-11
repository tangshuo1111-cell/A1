"""General-lane fast path — thin coordinator (Round 1 + R20 split)."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from application.chat.executors.fast_executor_general_attempts import (
    attempt_canned_fast,
    attempt_direct_llm_fast,
    attempt_weather_fast,
)
from application.chat.executors.fast_lanes.fast_llm import run_fast_llm_answer
from application.chat.executors.general_fast_rules import can_use_direct_fast_path
from application.chat.executors.general_fast_terms import try_canned_fast_answer
from application.chat.executors.general_fast_weather import try_fast_weather_answer
from application.chat.history_buffer import ChatTurnDeps
from application.chat.turn_state_machine import TurnStateBundle

__all__ = [
    "maybe_return_general_fast",
    "can_use_direct_fast_path",
    "try_canned_fast_answer",
    "try_fast_weather_answer",
    "run_fast_llm_answer",
]


def maybe_return_general_fast(
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
    turn_state: TurnStateBundle | None = None,
) -> tuple[Any | None, str, dict[str, Any]]:
    common = dict(
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

    weather_hit = attempt_weather_fast(
        weather_fast=try_fast_weather_answer(message),
        use_knowledge=use_knowledge,
        v13_file_content=v13_file_content,
        v13_text_content=v13_text_content,
        **common,
    )
    if weather_hit is not None:
        return weather_hit

    if effective_mode == "fast" and can_use_direct_fast_path(
        message,
        use_knowledge=use_knowledge,
        v13_file_content=v13_file_content,
        v13_text_content=v13_text_content,
    ):
        canned_hit = attempt_canned_fast(
            canned=try_canned_fast_answer(message),
            **common,
        )
        if canned_hit is not None:
            return canned_hit
        return attempt_direct_llm_fast(
            context_block=context_block,
            use_knowledge=use_knowledge,
            **common,
        )

    return None, effective_mode, timing
