"""Smoke：成本上限触发时 LLM 路由路径应拒绝继续计费调用（不发起真实 API）。"""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime

import pytest
from tests._support.bootstrap import find_repo_root

REPO_ROOT = find_repo_root(__file__)
for p in (str(REPO_ROOT),):
    if p not in sys.path:
        sys.path.insert(0, p)

from config.settings import settings  # noqa: E402
from llm.router import classify_intent_with_llm, maybe_refine_with_llm  # noqa: E402
from schemas import MainDecision, TaskInput  # noqa: E402


def _reload_cost_rule() -> None:
    import config.cost_rule as cr

    importlib.reload(cr)


@pytest.fixture
def _enable_router_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_LLM_ROUTER", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-cost-gate")
    monkeypatch.setattr(settings, "use_llm_router", True, raising=False)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-cost-gate", raising=False)


def test_classify_intent_blocked_when_cost_budget_zero(
    monkeypatch: pytest.MonkeyPatch, _enable_router_llm: None
) -> None:
    monkeypatch.setenv("MAX_ESTIMATED_COST_USD", "0")
    _reload_cost_rule()
    try:
        r = classify_intent_with_llm("知识库里有哪些主题？")
        assert r.available is False
        assert "cost_limit" in (r.error or "").lower()
    finally:
        monkeypatch.delenv("MAX_ESTIMATED_COST_USD", raising=False)
        _reload_cost_rule()


def test_maybe_refine_returns_cost_limit_without_openai_call(
    monkeypatch: pytest.MonkeyPatch, _enable_router_llm: None
) -> None:
    monkeypatch.setenv("MAX_ESTIMATED_COST_USD", "0")
    _reload_cost_rule()
    try:
        task = TaskInput(
            task_id="cost-t1",
            user_query="hello",
            clean_query="hello",
            created_at=datetime.now(UTC),
        )
        base = MainDecision(task_id=task.task_id, need_rag=False, answer_channel="direct")
        out = maybe_refine_with_llm(task, base)
        assert out.llm_error == "cost_limit_reached"
        assert out.router_source == "rules"
    finally:
        monkeypatch.delenv("MAX_ESTIMATED_COST_USD", raising=False)
        _reload_cost_rule()
