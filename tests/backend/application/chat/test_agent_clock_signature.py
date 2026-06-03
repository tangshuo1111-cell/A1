"""S11 — Agent clock parameter required on orchestration entrypoints (§6.7 A4 / T3)."""
from __future__ import annotations

import inspect

from agents.answer_agent import AnswerAgent
from agents.main_agent import MainAgent
from agents.middle_agent import MiddleAgent
from application.chat.budget_clock import BudgetClock


def _assert_clock_required(method) -> None:
    sig = inspect.signature(method)
    assert "clock" in sig.parameters
    param = sig.parameters["clock"]
    assert param.default is inspect.Parameter.empty
    assert param.annotation in (BudgetClock, "BudgetClock")


def test_agent_clock_signature_required() -> None:
    _assert_clock_required(MainAgent.pan)
    _assert_clock_required(MiddleAgent.caipan)
    _assert_clock_required(AnswerAgent.huida)
