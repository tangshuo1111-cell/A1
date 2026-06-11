"""Agent result schema — forbidden turn-level fields must not appear in agent extras."""

from __future__ import annotations

from application.chat.chat_contracts import AGENT_FORBIDDEN_EXTRA_KEYS, assert_agent_extra_safe
from agents.answer_agent.runtime import AnswerAgent
from agents.main_agent import MainAgent
from agents.middle_agent import MiddleAgent
from application.chat.budget_clock import BudgetClock


def test_collab_extra_has_no_forbidden_turn_fields() -> None:
    clock = BudgetClock.start()
    main = MainAgent().pan("你好", session_id=None, http_use_knowledge=False, clock=clock)
    mid = MiddleAgent().caipan("你好", plan=main.plan, http_use_knowledge=False, clock=clock)
    extra = AnswerAgent().collab_extra(main.plan, mid.bundle)
    assert not AGENT_FORBIDDEN_EXTRA_KEYS.intersection(extra.keys())
    assert_agent_extra_safe(extra)
