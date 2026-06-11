"""Thin facade — canonical main-chain logic lives in ``turn_orchestrator`` (Round 5+)."""

from __future__ import annotations

from application.chat.budget_clock import SLA_BUDGET_MS, BudgetClock
from application.chat.executors.async_path.build_pending import (
    build_async_pending_result as _build_async_pending_result,
)
from application.chat.fast_lane_gate import should_allow_fast
from application.chat.history_buffer import ChatTurnDeps
from application.chat.response_assembly import build_extra as _build_extra
from application.chat.shared_material_prep import run_shared_material_prep
from application.chat.turn_orchestrator import (
    TurnOrchestrator,
    build_turn_context,
    run_agno_chat_turn_impl,
)
from application.ingress import resolve_lane_decision
from services.capabilities.web import web_orchestration_service as agno_web_service

__all__ = [
    "ChatTurnDeps",
    "TurnOrchestrator",
    "SLA_BUDGET_MS",
    "BudgetClock",
    "_build_async_pending_result",
    "_build_extra",
    "agno_web_service",
    "build_turn_context",
    "resolve_lane_decision",
    "run_agno_chat_turn_impl",
    "run_shared_material_prep",
    "should_allow_fast",
]
