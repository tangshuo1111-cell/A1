"""Agent port contracts — orchestration calls agents only through these shapes (Round 4)."""

from __future__ import annotations

from typing import Any, Protocol

from agents.shared.history_context import SessionHistorySnapshot
from application.chat.budget_clock import BudgetClock
from application.chat.chat_contracts import AnswerAgentResult, MainAgentResult, MiddleAgentResult


class MainAgentPort(Protocol):
    def pan(
        self,
        message: str,
        *,
        session_id: str | None = None,
        http_use_knowledge: bool = False,
        context_snippet: str = "",
        history: SessionHistorySnapshot | None = None,
        intent_classifier: Any | None = None,
        v13_intent_classifier: Any | None = None,
        v13_file_content: str | bytes | None = None,
        v13_title: str | None = None,
        v13_text_content: str | None = None,
        clock: BudgetClock,
    ) -> MainAgentResult: ...


class MiddleAgentPort(Protocol):
    def caipan(
        self,
        message: str,
        *,
        plan: Any,
        shared_prep: Any | None = None,
        http_use_knowledge: bool = False,
        history: SessionHistorySnapshot | None = None,
        session_id: str | None = None,
        v13_text_content: str | None = None,
        v13_title: str | None = None,
        v13_file_content: str | bytes | None = None,
        prior_bundle: Any | None = None,
        allowed_fallback_steps: list[dict[str, Any]] | None = None,
        current_round: int = 0,
        feedback_gate_result: dict[str, Any] | None = None,
        clock: BudgetClock,
    ) -> MiddleAgentResult: ...


class AnswerAgentPort(Protocol):
    def huida(
        self,
        user_message: str,
        *,
        context_block: str | None,
        plan: Any,
        bundle: Any,
        clock: BudgetClock,
    ) -> AnswerAgentResult: ...

    def collab_extra(self, plan: Any, bundle: Any) -> dict[str, Any]: ...
