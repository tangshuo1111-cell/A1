"""第三轮：V17 tool 调度超限、放行集、失败后继续下一步（伪成功）。"""
from __future__ import annotations

import sys
from dataclasses import replace

import pytest
from tests._support.bootstrap import find_repo_root

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents.middle_agent.tool_dispatch import (  # noqa: E402
    _dispatch_v17_tool,
    _V17ServiceToolResult,
)


@pytest.fixture(autouse=True)
def _silence_tool_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("core.cost_recorder.record_tool_call", lambda *_a, **_k: None)


def test_unknown_tool_is_not_found() -> None:
    res, entry = _dispatch_v17_tool("totally_unknown_tool_xx", {})
    assert res.status == "failed"
    assert res.error_code == "tool_not_found"
    assert "v17" in entry.lower() or entry == "v17.dispatcher"


def test_tool_max_steps_breaks_mid_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    import config.cost_rule as cost_rule
    from agents.middle_agent.tool_dispatch import _execute_v17_steps

    monkeypatch.setattr(cost_rule, "COST", replace(cost_rule.COST, tool_max_steps=2))

    ok = _V17ServiceToolResult(
        tool_name="fetch_web_page",
        status="success",
        text="正文" * 5,
        metadata={"title": "t", "content_hash": "hh"},
    )

    def fake_dispatch(tool_name: str, args: dict) -> tuple:
        return ok, "mock.dispatch"

    monkeypatch.setattr(
        "agents.middle_agent.tool_dispatch._dispatch_v17_tool",
        fake_dispatch,
    )

    steps = [
        {"tool_name": "fetch_web_page", "args": {}, "step_id": "a"},
        {"tool_name": "fetch_web_page", "args": {}, "step_id": "b"},
        {"tool_name": "fetch_web_page", "args": {}, "step_id": "c"},
    ]
    seeds = [
        {"source_task_id": "st0"},
        {"source_task_id": "st1"},
        {"source_task_id": "st2"},
    ]

    _tasks, _briefs, summary, failures, _calls, _tmp = _execute_v17_steps(
        steps=steps,
        source_tasks=seeds,
        allowed=set(),
        disabled=set(),
        round_label="rnd",
    )

    assert summary
    hit_limit = [
        x for x in failures if x.get("tool") == "LIMIT"
    ]
    assert hit_limit


def test_disallowed_then_allowed_recover(monkeypatch: pytest.MonkeyPatch) -> None:
    """第一步不在 allowlist → 失败后下一步仍尝试。"""
    from agents.middle_agent.tool_dispatch import _execute_v17_steps

    ok = _V17ServiceToolResult(
        tool_name="retrieve_knowledge",
        status="success",
        text="chunk-lines " * 4,
        metadata={},
        retrieved_chunk_ids=["c-demo"],
    )

    def fake_dispatch(tool_name: str, args: dict) -> tuple:
        assert tool_name == "retrieve_knowledge"
        return ok, "mock"

    monkeypatch.setattr(
        "agents.middle_agent.tool_dispatch._dispatch_v17_tool",
        fake_dispatch,
    )

    steps = [
        {"tool_name": "fetch_dynamic_page", "args": {}, "step_id": "d0"},
        {"tool_name": "retrieve_knowledge", "args": {"query": "q"}, "step_id": "d1"},
    ]
    seeds = [{"source_task_id": "sx0"}, {"source_task_id": "sx1"}]

    tasks, *_rest = _execute_v17_steps(
        steps=steps,
        source_tasks=seeds,
        allowed={"retrieve_knowledge"},  # 第一步被拒，第二步放行
        disabled=set(),
        round_label="recover",
    )

    assert tasks[0].get("status") == "failed"
    assert tasks[1].get("status") == "succeeded"


def test_second_web_hit_triggers_web_rate_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """第二页抓取撞 web_fetch_max_pages。"""
    import config.cost_rule as cost_rule
    from agents.middle_agent.tool_dispatch import _execute_v17_steps

    monkeypatch.setattr(
        cost_rule,
        "COST",
        replace(cost_rule.COST, web_fetch_max_pages=1),
    )

    ok = _V17ServiceToolResult(
        tool_name="fetch_web_page",
        status="success",
        text="ok",
        metadata={"content_hash": "c1"},
    )

    monkeypatch.setattr(
        "agents.middle_agent.tool_dispatch._dispatch_v17_tool",
        lambda *_a: (ok, "mock"),
    )

    steps = [
        {"tool_name": "fetch_web_page", "args": {}, "step_id": "w0"},
        {"tool_name": "fetch_web_page", "args": {}, "step_id": "w1"},
    ]

    _, _, summary, failures, _, _ = _execute_v17_steps(
        steps=steps,
        source_tasks=[{}, {}],
        allowed=set(),
        disabled=set(),
        round_label="web-cap",
    )

    assert failures
    assert any("web_fetch_max_pages_reached" in str(f.values()) for f in failures)
