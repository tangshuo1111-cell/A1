"""
工具 / 资料收集策略：执行顺序计算（policy 子层）。

依据 CollectionTask 的渠道与 middle_collect_priority 决定 local / rag / http / mcp 顺序；
供 middle_agent.collect 阶段使用（单一真相，避免散落 if/else）。

输入：CollectionTask；输出：步骤名列表（与 _run_step 约定一致）。
"""

from __future__ import annotations

from schemas import CollectionTask


def wants_list_files(q: str) -> bool:
    keys = ("列表", "有哪些", "列出", "list files", "知识库列表", "列出文件", "列出知识库")
    low = q.lower()
    return any(k in q for k in keys) or "list files" in low


def build_execution_order(task: CollectionTask) -> list[str]:
    ch = set(task.available_channels)
    local_eligible = task.enable_local_file_tools and (
        bool(task.local_path_hints) or wants_list_files(task.search_query)
    )
    http_eligible = "tool" in ch and bool(task.link_urls)
    rag_eligible = "rag" in ch
    mcp_eligible = "mcp" in ch

    prio = task.middle_collect_priority or "balanced"
    parts: list[str] = []

    def append_unique(name: str) -> None:
        if name not in parts:
            parts.append(name)

    if prio == "http_first":
        if http_eligible:
            append_unique("http")
        if rag_eligible:
            append_unique("rag")
        if local_eligible:
            append_unique("local")
    elif prio == "rag_first":
        if rag_eligible:
            append_unique("rag")
        if local_eligible:
            append_unique("local")
        if http_eligible:
            append_unique("http")
    elif prio == "local_first":
        if local_eligible:
            append_unique("local")
        if rag_eligible:
            append_unique("rag")
        if http_eligible:
            append_unique("http")
    else:
        if local_eligible:
            append_unique("local")
        if rag_eligible:
            append_unique("rag")
        if http_eligible:
            append_unique("http")

    if mcp_eligible:
        append_unique("mcp")
    return parts
