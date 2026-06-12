"""单渠道执行：`local` / `rag` / `http` / `mcp` / `search` 调用与单步调度 `_run_step`。"""

from __future__ import annotations

from debug_trace import trace
from mcp_local import mcp_client
from schemas import CollectionTask
from services.capabilities.knowledge.retrieve_service import search_kb
from tools import tools as tool_registry
from tools.policy.execution_order import wants_list_files
from tools.search.web_search import format_evidence_line, run_web_search


def _run_local_file_tools(task: CollectionTask) -> tuple[list[str], list[str], bool, list[str]]:
    """失败信息只进 trace，不进 evidence_list（由 collect 写入 collection_trace）。"""
    chunks: list[str] = []
    sources: list[str] = []
    dbg: list[str] = []
    hint_ok = False
    q = task.search_query

    if task.local_path_hints:
        for hint in task.local_path_hints[:5]:
            try:
                out = tool_registry.call("read_text_file", rel_path=hint)
            except Exception as e:  # noqa: BLE001
                out = {"ok": False, "error": str(e)}
            if isinstance(out, dict) and out.get("ok") and (out.get("text") or "").strip():
                p = out.get("path", hint)
                body = str(out["text"])[:8000]
                chunks.append(f"[本地文件] {p}\n{body}")
                sources.append("tool_file")
                hint_ok = True
            else:
                err = (out or {}).get("error", "读取失败") if isinstance(out, dict) else "读取失败"
                dbg.append(f"local_file_fail path={hint} err={str(err)[:160]}")

    if wants_list_files(q):
        try:
            out = tool_registry.call("list_knowledge_sample_files")
        except Exception as e:  # noqa: BLE001
            out = {"ok": False, "error": str(e)}
        if isinstance(out, dict) and out.get("ok"):
            files = out.get("files") or []
            chunks.append("[知识源列表] " + "\n".join(files) if files else "[知识源列表] （空）")
            sources.append("tool_file")
        else:
            err = (out or {}).get("error", "列出失败") if isinstance(out, dict) else "列出失败"
            dbg.append(f"list_knowledge_sample_files_fail err={str(err)[:120]}")

    return chunks, sources, hint_ok, dbg


def _run_http_tools(task: CollectionTask) -> tuple[list[str], list[str], bool, list[str]]:
    chunks: list[str] = []
    sources: list[str] = []
    dbg: list[str] = []
    ok = False
    if "tool" not in task.available_channels or not task.link_urls:
        return chunks, sources, ok, dbg
    for url in task.link_urls[:3]:
        try:
            out = tool_registry.call("fetch_url", url=url)
        except Exception as e:  # noqa: BLE001
            out = {"ok": False, "error": str(e)}
        if isinstance(out, dict) and out.get("ok") and (out.get("text") or "").strip():
            snippet = str(out["text"])[:4000]
            chunks.append(f"[url] {url}\n{snippet}")
            sources.append("tool_url")
            ok = True
            break
        err = (out or {}).get("error", "fetch 失败") if isinstance(out, dict) else "fetch 失败"
        dbg.append(f"fetch_url_fail url={url[:80]} err={str(err)[:120]}")
    return chunks, sources, ok, dbg


def _rag_dedupe_key(h: object) -> tuple[object, ...]:
    """h 现在是 RetrievedChunk；兼容保留 rowid 逻辑退场后用 chunk_id 去重。"""
    if hasattr(h, "chunk_id"):
        return ("chunk_id", h.chunk_id)  # type: ignore[union-attr]
    if isinstance(h, dict):
        rid = h.get("rowid")
        if rid is not None:
            return ("rowid", int(rid))
        t = (h.get("text") or "")[:320]
        return ("text", t)
    return ("obj", id(h))


def _run_rag(
    task: CollectionTask,
    query: str | None = None,
    *,
    top_k: int = 6,
) -> tuple[list[str], list[str], list[str]]:
    """按序尝试 rag_search_queries（或单次 query），合并去重，最多 top_k 条。"""
    sub: list[str] = []
    chunks: list[str] = []
    sources: list[str] = []
    if "rag" not in task.available_channels:
        return chunks, sources, sub

    if query is not None:
        queries = [query.strip()] if query.strip() else []
    else:
        queries = [q.strip() for q in (task.rag_search_queries or []) if (q or "").strip()]
        if not queries:
            queries = [(task.search_query or "").strip()]
        queries = [q for q in queries if q]

    if not queries:
        sub.append("rag_try_skip_empty_queries")
        return chunks, sources, sub

    seen_keys: set[tuple[object, ...]] = set()
    for rq in queries:
        if len(chunks) >= top_k:
            break
        trace("middle_agent -> retrieve_service.search_kb (RAG / retriever)")
        need = max(top_k, 8)
        hits = search_kb(rq, top_k=need)
        sub.append(f"rag_try q={rq[:56]!r} hits={len(hits)}")
        trace(f"middle_agent RAG try q={rq[:40]!r} n={len(hits)}")
        for h in hits:
            key = _rag_dedupe_key(h)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            text = (h.text if hasattr(h, "text") else (h.get("text") or "")).strip()  # type: ignore[union-attr]
            if not text:
                continue
            chunks.append(text)
            sources.append("rag")
            if len(chunks) >= top_k:
                break
    return chunks, sources, sub


def _run_search(task: CollectionTask) -> tuple[list[str], list[str]]:
    """外部 Web 检索（DDG HTML），结果标准化为证据行。"""
    if not task.enable_web_search:
        return [], []
    trace("middle_agent -> web_search.run_web_search")
    recs, code = run_web_search(task.search_query)
    trace(f"middle_agent web_search trace={code} n={len(recs)}")
    lines: list[str] = []
    tags: list[str] = []
    for rec in recs:
        lines.append(format_evidence_line(rec))
        tags.append("web_search")
    return lines, tags


def _run_mcp() -> tuple[list[str], list[str], list[str]]:
    """MCP ping/握手仅供联调，不进入用户可见 evidence。"""
    try:
        res = mcp_client.call_mcp_tool("ping", {})
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "error": str(e), "transport": "error"}
    tr = res.get("transport", "")
    if tr == "mcp_stdio":  # noqa: SIM108
        prefix = "mcp_stdio"
    else:
        prefix = "mcp_sim"
    line = f"{prefix} ping_result={res!s}"[:400]
    return [], [], [f"mcp_diag={line}"]


def _run_step(
    task: CollectionTask,
    step: str,
    *,
    tool_http_ok_holder: list[bool],
    hint_ok_holder: list[bool],
) -> tuple[list[str], list[str], list[str]]:
    # 单测请 patch `agents.middle_agent.collect_flow_execute._run_rag` 等本模块符号
    if step == "local":
        trace("middle_agent -> tools (本地读文件 / 列 knowledge_samples)")
        lc, ls, hint_ok, ld = _run_local_file_tools(task)
        hint_ok_holder[0] = hint_ok_holder[0] or hint_ok
        return lc, ls, ld
    if step == "rag":
        c, s, sub = _run_rag(task)
        return c, s, sub
    if step == "http":
        if task.link_urls:
            trace("middle_agent -> tools.fetch_url (HTTP)")
        hc, hs, ok, hd = _run_http_tools(task)
        tool_http_ok_holder[0] = tool_http_ok_holder[0] or ok
        return hc, hs, hd
    if step == "mcp":
        trace("middle_agent -> mcp (channels 含 mcp)")
        _mc, _ms, mtd = _run_mcp()
        return _mc, _ms, mtd
    if step == "search":
        sc, ss = _run_search(task)
        return sc, ss, []
    return [], [], []
