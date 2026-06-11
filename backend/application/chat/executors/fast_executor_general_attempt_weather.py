"""Weather quick-answer attempt for general fast lane."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from application.chat.executors.fast_executor_general_attempt_common import (
    finish_general_fast_attempt,
)
from application.chat.history_buffer import ChatTurnDeps
from application.chat.turn_state_machine import TurnStateBundle


def attempt_weather_fast(
    *,
    message: str,
    weather_fast: tuple[str, dict[str, Any]] | None,
    use_knowledge: bool,
    v13_file_content: str | bytes | None,
    v13_text_content: str | None,
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
    if (
        effective_mode != "fast"
        or weather_fast is None
        or use_knowledge
        or v13_file_content is not None
        or (v13_text_content or "").strip()
    ):
        return None
    answer_text, weather_extra = weather_fast
    return finish_general_fast_attempt(
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
        turn_state=turn_state,
    )
