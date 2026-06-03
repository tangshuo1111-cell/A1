"""
RAG 检索 query 变体生成（rag 子层）。

为 FTS 生成多条可试查询：原句、去标点、主目标、以及与示例库对齐的别名扩展。
无复杂 query planning；供 workflow.common 与 middle_agent 使用。
"""

from __future__ import annotations

import re

# 与 knowledge_samples/sample.md 中词汇对齐，便于演示命中
_KB_DEMO_ALIASES = (
    "LightMultiAgentQA main_agent middle_agent answer_agent RAG "
    "sample.md knowledge_samples 示例 项目代号 多 Agent"
)

# 命中多个弱提示词、或强提示词时，才追加别名（避免单字泛词就「背题库」式扩展）
_PROJECT_DEMO_HINT_KEYS = (
    "项目",
    "代号",
    "示例",
    "readme",
    "README",
    "知识库",
    "Agent",
    "agent",
    "RAG",
    "rag",
    "sample",
    "轻量",
    "工具层",
    "协作",
    "路由",
    "main_agent",
    "middle_agent",
    "answer_agent",
)

_STRONG_DEMO_MARKERS = (
    "项目代号",
    "sample.md",
    "knowledge_samples",
    "LightMultiAgent",
    "多 Agent",
    "多agent",
)


def _normalize_punct(q: str) -> str:
    s = re.sub(r"[？?！!。．，、,.;:：；]+", " ", q)
    return re.sub(r"\s+", " ", s).strip()


def build_rag_search_queries(clean_query: str, primary_goal: str = "") -> list[str]:
    """
    返回按顺序尝试的检索串列表（去重保序）。
    首项为原始 clean_query，后续为扩展/别名，供 middle 逐项尝试直至有命中。
    """
    q = (clean_query or "").strip()
    out: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        t = (s or "").strip()
        if not t or t in seen:
            return
        seen.add(t)
        out.append(t)

    add(q)
    nq = _normalize_punct(q)
    if nq != q:
        add(nq)

    pg = (primary_goal or "").strip()
    if pg and pg != q and len(pg) >= 3:
        add(pg)
        add(_normalize_punct(pg))

    hits = sum(1 for k in _PROJECT_DEMO_HINT_KEYS if k in q)
    strong = any(m in q for m in _STRONG_DEMO_MARKERS)
    if strong or hits >= 2:
        add(f"{nq} {_KB_DEMO_ALIASES}")

    return out
