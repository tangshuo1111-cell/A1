"""Ingress router runtime helpers: flag gating + legacy fallback decision."""

from __future__ import annotations

import time
from typing import Any

from application.chat.budget_clock import BudgetClock
from config.feature_flags import ingress_router_active

from .lane_decision_schema import LaneDecision
from .semantic_router import route_chat_request


def legacy_lane_decision(
    *,
    request_id: str | None,
    session_id: str | None,
) -> LaneDecision:
    """Unified main-chain fallback when ingress router v2 is disabled."""
    return LaneDecision(
        request_id=str(request_id or ""),
        session_id=str(session_id or ""),
        lane="general",
        mode="complex",
        router_source="rule",
        router_confidence=0.0,
        router_fallback=True,
        router_decision_ms=0,
        escalated_to_main_agent=False,
    )


def resolve_lane_decision(
    *,
    message: str,
    session_id: str | None,
    request_id: str | None,
    use_knowledge: bool,
    v13_file_content: str | bytes | None,
    v13_text_content: str | None,
    attachments: list[dict[str, Any]] | None = None,
    main_agent: Any = None,
    context_snippet: str = "",
    clock: BudgetClock,
) -> LaneDecision:
    if not ingress_router_active():
        return legacy_lane_decision(request_id=request_id, session_id=session_id)
    started = time.perf_counter()
    decision = route_chat_request(
        message=message,
        session_id=session_id,
        request_id=request_id,
        use_knowledge=use_knowledge,
        v13_file_content=v13_file_content,
        v13_text_content=v13_text_content,
        attachments=attachments,
        main_agent=main_agent,
        context_snippet=context_snippet,
        clock=clock,
    )
    if decision.router_decision_ms <= 0:
        decision.router_decision_ms = max(0, int((time.perf_counter() - started) * 1000))
    return decision
