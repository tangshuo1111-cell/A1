"""tool_dispatch：单轮「工具步数」「网页抓取次数」上限（第四轮 B-020 基线）。"""

from __future__ import annotations

import sys
from dataclasses import replace

import pytest
from tests._support.bootstrap import find_repo_root

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import config.cost_rule as cost_mod  # noqa: E402
from agents.middle_agent.tool_dispatch import (  # noqa: E402
    _dispatch_v17_tool,
    _execute_v17_steps,
    _V17ServiceToolResult,
)


def test_tool_step_limit_stops_round(monkeypatch: pytest.MonkeyPatch) -> None:
    """超过 tool_max_steps 时记 LIMIT，不再跑后面的 step。"""
    monkeypatch.setattr(cost_mod, "COST", replace(cost_mod.COST, tool_max_steps=2))
    fake_calls: list[str] = []

    def _fake_dispatch(name: str, args: dict) -> tuple[_V17ServiceToolResult, str]:
        fake_calls.append(name)
        return (
            _V17ServiceToolResult(tool_name=name, status="success", text="ok", metadata={}),
            "stub",
        )

    monkeypatch.setattr("agents.middle_agent.tool_dispatch._dispatch_v17_tool", _fake_dispatch)
    steps = [{"tool_name": "retrieve_knowledge", "args": {"query": "q"}}] * 3
    seeds = [{"source_task_id": f"t{i}", "task_id": f"t{i}"} for i in range(3)]
    _st, _br, _sum, failures, _tc, _tm = _execute_v17_steps(
        steps=steps,
        source_tasks=seeds,
        allowed=set(),
        disabled=set(),
        round_label="unit",
    )
    assert fake_calls == ["retrieve_knowledge", "retrieve_knowledge"]
    lim = [x for x in failures if x.get("tool") == "LIMIT"]
    assert lim and "tool_max_steps" in lim[0].get("reason", "")


def test_web_fetch_page_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """fetch_* 网页类调用次数不能超过 web_fetch_max_pages。"""
    monkeypatch.setattr(
        cost_mod,
        "COST",
        replace(cost_mod.COST, tool_max_steps=20, web_fetch_max_pages=1),
    )
    n_ok = {"c": 0}

    def _dispatch(name: str, args: dict) -> tuple[_V17ServiceToolResult, str]:
        n_ok["c"] += 1
        return (
            _V17ServiceToolResult(tool_name=name, status="success", text="html", metadata={}),
            "stub",
        )

    monkeypatch.setattr("agents.middle_agent.tool_dispatch._dispatch_v17_tool", _dispatch)
    steps = [
        {"tool_name": "fetch_web_page", "args": {"url": "http://a"}},
        {"tool_name": "fetch_web_page", "args": {"url": "http://b"}},
    ]
    seeds = [{"source_task_id": "s0"}, {"source_task_id": "s1"}]
    _execute_v17_steps(
        steps=steps,
        source_tasks=seeds,
        allowed=set(),
        disabled=set(),
        round_label="unit-web",
    )
    assert n_ok["c"] == 1


def test_tool_disabled_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agents.middle_agent.tool_dispatch._dispatch_v17_tool",
        lambda *_a, **_k: (_V17ServiceToolResult(status="failed", error_code="no"), ""),
    )
    steps = [{"tool_name": "retrieve_knowledge", "args": {"query": "x"}}]
    seeds = [{"source_task_id": "only"}]
    _st, _br, _sum, failures, _tc, _tm = _execute_v17_steps(
        steps=steps,
        source_tasks=seeds,
        allowed=set(),
        disabled={"retrieve_knowledge"},
        round_label="d",
    )
    assert failures and failures[0].get("reason") == "tool_disabled"


def test_tool_not_in_allowed_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agents.middle_agent.tool_dispatch._dispatch_v17_tool",
        lambda *_a, **_k: (_V17ServiceToolResult(status="success", text="x"), ""),
    )
    steps = [{"tool_name": "retrieve_knowledge", "args": {}}]
    seeds = [{"source_task_id": "only"}]
    _st, _br, _sum, failures, _tc, _tm = _execute_v17_steps(
        steps=steps,
        source_tasks=seeds,
        allowed={"web_search"},
        disabled=set(),
        round_label="a",
    )
    assert failures and failures[0].get("reason") == "tool_not_allowed"


def test_unknown_tool_name_fails_dispatch() -> None:
    """不认识的 tool 名 → tool_not_found。"""
    res, tag = _dispatch_v17_tool("not_a_real_tool_name_xyz", {})
    assert res.status == "failed"
    assert res.error_code == "tool_not_found"
    assert "v17.dispatcher" in tag
