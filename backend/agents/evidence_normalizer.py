"""
证据归一化：从 middle 原始采集中剥离元数据块、失败文案、MCP 握手等，
只保留可面向用户引用的正文。调试信息通过返回值 trace 行交给 collection_trace。
"""

from __future__ import annotations

import re

from services.capabilities.knowledge.grounding_service import (
    is_rag_boost_header,
    strip_rag_internal_markers,
)

# MCP 相关来源一律不进用户证据
_MCP_SOURCES = frozenset({"mcp_sim", "mcp_stdio"})

_LOCAL_FAIL_MARKERS = ("[本地文件·失败]", "本地文件·失败")


def _dedupe_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()[:160]).lower()


def _should_drop_raw(text: str, source: str) -> tuple[bool, str]:
    t = (text or "").strip()
    if not t:
        return True, "empty"
    if source in _MCP_SOURCES:
        return True, "mcp_channel"
    if "[MCP·" in t or "MCP·进程内" in t or "MCP·stdio" in t:
        return True, "mcp_handshake_text"
    for m in _LOCAL_FAIL_MARKERS:
        if m in t:
            return True, "local_file_failed_text"
    if source == "rag" and is_rag_boost_header(t):
        return True, "rag_boost_header"
    return False, ""


def _sanitize_tool_file(text: str) -> str:
    t = text.strip()
    if t.startswith("[本地文件]"):
        rest = t.split("\n", 1)
        body = rest[1].strip() if len(rest) > 1 else ""
        return body if body else strip_rag_internal_markers(t)
    return strip_rag_internal_markers(t)


def _sanitize_tool_url(text: str) -> str:
    t = text.strip()
    if t.startswith("[url]"):
        parts = t.split("\n", 1)
        body = parts[1].strip() if len(parts) > 1 else ""
        return body if body else ""
    return t


def sanitize_evidence_text(text: str, source: str) -> str:
    """去掉渠道前缀与内部标记，得到可写入 evidence_list 的正文。"""
    t = (text or "").strip()
    if source == "tool_file":
        t = _sanitize_tool_file(t)
    elif source == "tool_url":
        t = _sanitize_tool_url(t)
    elif source == "rag":
        t = strip_rag_internal_markers(t)
    else:
        t = strip_rag_internal_markers(t)
    return t.strip()


def normalize_evidence_lists(
    chunks: list[str],
    sources: list[str],
) -> tuple[list[str], list[str], list[str]]:
    """
    返回 (clean_evidence, clean_sources, norm_trace_lines)。
    """
    out_e: list[str] = []
    out_s: list[str] = []
    trace: list[str] = []
    seen: set[str] = set()

    for e, s in zip(chunks, sources):  # noqa: B905
        drop, reason = _should_drop_raw(e, s)
        if drop:
            trace.append(f"evidence_drop source={s} reason={reason}")
            continue
        cleaned = sanitize_evidence_text(e, s)
        if not cleaned:
            trace.append(f"evidence_empty_after_sanitize source={s}")
            continue
        dk = _dedupe_key(cleaned)
        if dk in seen:
            trace.append("evidence_dedupe_skip")
            continue
        seen.add(dk)
        out_e.append(cleaned)
        out_s.append(s)

    return out_e, out_s, trace
