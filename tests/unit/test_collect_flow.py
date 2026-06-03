"""第三轮：`collect_flow` 单源成功/失败、多源合并、异常透出（全盘 mock KB）。"""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest
from tests._support.bootstrap import find_repo_root

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents import middle_agent  # noqa: E402
from schemas import CollectionTask  # noqa: E402


def _coll(**kw: object) -> CollectionTask:
    defaults: dict = {
        "task_id": "cf-unit",
        "search_query": "noop-query",
        "collection_goal": "noop goal",
        "available_channels": ["rag", "tool", "mcp"],
        "link_urls": [],
        "rag_search_queries": ["noop-query"],
        "enable_local_file_tools": False,
        "middle_collect_priority": "balanced",
    }
    defaults.update(kw)
    return CollectionTask(**defaults)


@pytest.fixture(autouse=True)
def _stub_kb_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agents.middle_agent.collect_flow.count_kb_chunks",
        lambda: 0,
    )


def test_single_source_success_rag_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_rag(task, query=None, top_k=6):
        return (["snippet-one"], ["rag"], ["mock_rag"])

    monkeypatch.setattr(
        "agents.middle_agent.collect_flow.plan_collection_steps",
        lambda t: (["rag"], []),
    )
    task = _coll(available_channels=["rag"])

    with patch("agents.middle_agent.collect_flow_execute._run_rag", fake_rag):
        pack = middle_agent.collect(task)

    assert "snippet-one" in (pack.evidence_list or [])
    assert "rag" in pack.source_list


def test_single_source_rag_miss_insufficient(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_rag_empty(task, query=None, top_k=6):
        return ([], [], ["mock_empty"])

    monkeypatch.setattr(
        "agents.middle_agent.collect_flow.plan_collection_steps",
        lambda t: (["rag"], []),
    )
    task = _coll(search_query="no hits xyz", rag_search_queries=[])

    with patch("agents.middle_agent.collect_flow_execute._run_rag", fake_rag_empty):
        pack = middle_agent.collect(task)

    assert not pack.evidence_list or not pack.completeness_ok


def test_multi_source_merges_rag_and_local(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_rag(task, query=None, top_k=6):
        return (["from rag"], ["rag"], [])

    def fake_local(*_a, **_k):
        return (["from file"], ["tool_file"], True, [])

    monkeypatch.setattr(
        "agents.middle_agent.collect_flow.plan_collection_steps",
        lambda t: (["rag", "local"], []),
    )
    task = _coll(
        enable_local_file_tools=True,
        local_path_hints=["knowledge_samples/sample.md"],
    )

    with (
        patch("agents.middle_agent.collect_flow_execute._run_rag", fake_rag),
        patch(
            "agents.middle_agent.collect_flow_execute._run_local_file_tools",
            fake_local,
        ),
    ):
        pack = middle_agent.collect(task)

    assert "rag" in pack.source_list
    assert "tool_file" in pack.source_list


def test_rag_raises_timeout_surfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise TimeoutError("simulated_upstream_timeout")

    monkeypatch.setattr(
        "agents.middle_agent.collect_flow.plan_collection_steps",
        lambda t: (["rag"], []),
    )

    with patch(
        "agents.middle_agent.collect_flow_execute._run_rag",
        boom,
    ), pytest.raises(
        TimeoutError,
        match="simulated_upstream_timeout",
    ):
        middle_agent.collect(_coll())
