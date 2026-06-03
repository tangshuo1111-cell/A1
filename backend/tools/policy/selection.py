"""
工具选择策略：在基础执行顺序上注入外部检索等步骤（policy 层）。

输出 (order, trace_lines) 供 middle_agent 写入 collection_trace，便于 observability。
不直接调用工具，只决定顺序；具体执行仍在 middle_agent._run_step。

与 tools.policy.execution_order、schemas.CollectionTask、LangGraph collect 节点协作。
"""

from __future__ import annotations

from schemas import CollectionTask
from tools.policy.execution_order import build_execution_order


def _inject_search_step(order: list[str]) -> list[str]:
    if "search" in order:
        return order
    out: list[str] = []
    inserted = False
    for step in order:
        if step == "http" and not inserted:
            out.append("search")
            inserted = True
        out.append(step)
    if not inserted:
        if "rag" in out:
            i = out.index("rag") + 1
            out.insert(i, "search")
        else:
            out.insert(0, "search")
    return out


def plan_collection_steps(task: CollectionTask) -> tuple[list[str], list[str]]:
    """
    返回 (执行步骤列表, 策略说明轨迹)。
    """
    base = build_execution_order(task)
    notes: list[str] = [f"tool_policy: base={base!r}"]
    order = list(base)
    if task.enable_web_search:
        order = _inject_search_step(order)
        notes.append("tool_policy: web_search enabled -> order adjusted")
    return order, notes
