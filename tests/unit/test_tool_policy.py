"""工具策略：执行顺序与 web_search 注入可观察。"""

from __future__ import annotations

from schemas import CollectionTask
from tools.policy.execution_order import build_execution_order, wants_list_files
from tools.policy.selection import plan_collection_steps


def test_wants_list_files() -> None:
    assert wants_list_files("列出知识库文件") is True
    assert wants_list_files("什么是 RAG") is False


def test_build_order_rag_first() -> None:
    t = CollectionTask(
        task_id="t",
        search_query="q",
        collection_goal="g",
        available_channels=["rag", "tool"],
        link_urls=["https://a.com"],
        enable_local_file_tools=False,
        middle_collect_priority="rag_first",
    )
    order = build_execution_order(t)
    assert order[0] == "rag"


def test_plan_injects_search_when_enabled() -> None:
    t = CollectionTask(
        task_id="t",
        search_query="q",
        collection_goal="g",
        available_channels=["rag", "tool"],
        link_urls=[],
        enable_local_file_tools=False,
        enable_web_search=True,
    )
    order, notes = plan_collection_steps(t)
    assert "search" in order
    assert any("web_search" in n for n in notes)
