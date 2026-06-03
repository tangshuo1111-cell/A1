"""
RAG 检索结果清洗与排序辅助。

boost header（ingest 注入的 FTS 辅助块）只服务召回，不应排在正文之前，
也不应进入用户可见证据/回答。
"""

from __future__ import annotations

import re
from typing import Any

# 与 rag.ingest._fts_boost_header 字段对齐，用于识别「纯元数据块」
_BOOST_MARKERS = (
    "[doc_path]",
    "[doc_file]",
    "[doc_title]",
    "[demo_keywords]",
)


def is_rag_boost_header(text: str) -> bool:
    """是否为 ingest 注入的可检索头块（或其主要内容）。"""
    t = (text or "").strip()
    if not t:
        return False
    if not all(m in t for m in _BOOST_MARKERS[:2]):
        return False
    # 头块短且以标记为主
    if len(t) < 400 and "[demo_keywords]" in t:
        return True
    return t.startswith("[doc_path]")


def sort_hits_body_before_boost(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """正文 chunk 在前，boost header 在后（同组内保持原相对顺序）。"""
    body: list[dict[str, Any]] = []
    boost: list[dict[str, Any]] = []
    for r in rows:
        txt = (r.get("text") or r.get("content") or "") if isinstance(r, dict) else ""
        if is_rag_boost_header(str(txt)):
            boost.append(r)
        else:
            body.append(r)
    return body + boost


def demote_boost_preserve_order(
    ranked: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    """在已排序列表上把 boost 头块移到末尾，再截断 top_k。"""
    body = [x for x in ranked if not is_rag_boost_header(str(x.get("text", "") or ""))]
    boost = [x for x in ranked if is_rag_boost_header(str(x.get("text", "") or ""))]
    return (body + boost)[:top_k]


def demote_boost_preserve_order_chunks(
    ranked: list[Any],  # list[RetrievedChunk]
    top_k: int,
) -> list[Any]:
    """list[RetrievedChunk] 版本：把 boost 头块移到末尾，再截断 top_k。

    V12 R2：供 hybrid_retrieve 直接操作 RetrievedChunk，无需转换为 dict。
    """
    body = [c for c in ranked if not is_rag_boost_header(c.text)]
    boost = [c for c in ranked if is_rag_boost_header(c.text)]
    return (body + boost)[:top_k]


def strip_rag_internal_markers(text: str) -> str:
    """从片段中去掉误入的 doc 标记行（兜底，优先在 ingest 侧不进证据）。"""
    s = text or ""
    for m in _BOOST_MARKERS:
        s = s.replace(m, "")
    s = re.sub(r"\[demo_keywords\][^\n]*", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()
