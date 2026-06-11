"""Port adapters — application layer invokes agents without reaching into runtime internals."""

from __future__ import annotations

from typing import Any

from agents.ports import AnswerAgentPort, MainAgentPort, MiddleAgentPort
from application.chat.budget_clock import BudgetClock
from application.chat.chat_contracts import (
    AnswerAgentResult,
    MainAgentResult,
    MiddleAgentResult,
    coerce_answer_agent_result,
    coerce_main_agent_result,
    coerce_middle_agent_result,
)
from domain.session_types import SessionHistorySnapshot


def invoke_main_agent(
    agent: MainAgentPort,
    *,
    message: str,
    session_id: str | None,
    use_knowledge: bool,
    context_block: str | None,
    history_snapshot: SessionHistorySnapshot,
    budget_clock: BudgetClock,
    v13_file_content: str | bytes | None = None,
    v13_title: str | None = None,
    v13_text_content: str | None = None,
) -> MainAgentResult:
    return coerce_main_agent_result(agent.pan(
        message,
        session_id=session_id,
        http_use_knowledge=use_knowledge,
        context_snippet=context_block or "",
        history=history_snapshot,
        v13_file_content=v13_file_content,
        v13_title=v13_title,
        v13_text_content=v13_text_content,
        clock=budget_clock,
    ))


def invoke_middle_agent(
    agent: MiddleAgentPort,
    *,
    message: str,
    plan: Any,
    use_knowledge: bool,
    shared_prep: Any | None,
    history_snapshot: SessionHistorySnapshot,
    session_id: str | None,
    v13_text_content: str | None,
    v13_title: str | None,
    v13_file_content: str | bytes | None,
    budget_clock: BudgetClock,
    prior_bundle: Any | None = None,
    current_round: int = 0,
    feedback_gate_result: dict[str, Any] | None = None,
    allowed_fallback_steps: list[dict[str, Any]] | None = None,
) -> MiddleAgentResult:
    return coerce_middle_agent_result(agent.caipan(
        message,
        plan=plan,
        http_use_knowledge=use_knowledge,
        shared_prep=shared_prep,
        history=history_snapshot,
        session_id=session_id or "",
        v13_text_content=v13_text_content,
        v13_title=v13_title,
        v13_file_content=v13_file_content,
        prior_bundle=prior_bundle,
        current_round=current_round,
        feedback_gate_result=feedback_gate_result,
        allowed_fallback_steps=allowed_fallback_steps,
        clock=budget_clock,
    ))


def invoke_answer_agent(
    agent: AnswerAgentPort,
    *,
    message: str,
    context_block: str | None,
    plan: Any,
    bundle: Any,
    budget_clock: BudgetClock,
) -> AnswerAgentResult:
    return coerce_answer_agent_result(agent.huida(
        message,
        context_block=context_block,
        plan=plan,
        bundle=bundle,
        clock=budget_clock,
    ))
