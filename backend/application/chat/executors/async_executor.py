"""Async executor profile — task enqueue contract only."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from application.chat.executors.async_path.build_pending import build_async_pending_result
from application.chat.material_flow import material_trace_for_extra
from application.chat.trace_writer import apply_arbitrator_extra
from config.feature_flags import is_enabled
from schemas import ChatTurnResult


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
    async_result = build_async_pending_result(
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


build_async_turn_result = _build_async_turn_result


class AsyncExecutor:
    """Async profile — enqueue task contract; does not run Main/Middle/Answer."""

    build_turn_result = staticmethod(_build_async_turn_result)
