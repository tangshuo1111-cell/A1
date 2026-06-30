"""collect_flow_execute 出口形态 characterization（tool_registry 打桩）。"""

from __future__ import annotations

import pytest

from agents.middle_agent import collect_flow_execute
from schemas import CollectionTask


def _task(**kw: object) -> CollectionTask:
    defaults: dict = {
        "task_id": "cfe-unit",
        "search_query": "sample query",
        "collection_goal": "unit test",
        "available_channels": ["tool"],
        "link_urls": [],
        "enable_local_file_tools": True,
        "local_path_hints": [],
        "middle_collect_priority": "balanced",
    }
    defaults.update(kw)
    return CollectionTask(**defaults)


def test_run_local_file_tools_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_call(name: str, **kwargs: object) -> dict[str, object]:
        assert name == "read_text_file"
        return {"ok": True, "text": "hello from disk", "path": kwargs.get("rel_path")}

    monkeypatch.setattr(collect_flow_execute.tool_registry, "call", fake_call)
    chunks, sources, hint_ok, dbg = collect_flow_execute._run_local_file_tools(
        _task(local_path_hints=["notes.txt"]),
    )
    assert hint_ok is True
    assert any("hello from disk" in c for c in chunks)
    assert "tool_file" in sources
    assert not dbg


def test_run_local_file_tools_read_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_call(name: str, **_kwargs: object) -> dict[str, object]:
        return {"ok": False, "error": "permission denied"}

    monkeypatch.setattr(collect_flow_execute.tool_registry, "call", fake_call)
    chunks, sources, hint_ok, dbg = collect_flow_execute._run_local_file_tools(
        _task(local_path_hints=["secret.txt"]),
    )
    assert hint_ok is False
    assert not chunks
    assert not sources
    assert dbg and "local_file_fail" in dbg[0]


def test_run_http_tools_fetch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_call(name: str, **kwargs: object) -> dict[str, object]:
        assert name == "fetch_url"
        return {"ok": True, "text": "page body", "url": kwargs.get("url")}

    monkeypatch.setattr(collect_flow_execute.tool_registry, "call", fake_call)
    chunks, sources, ok, dbg = collect_flow_execute._run_http_tools(
        _task(link_urls=["https://example.com/doc"]),
    )
    assert ok is True
    assert any("page body" in c for c in chunks)
    assert "tool_url" in sources
    assert not dbg


def test_run_http_tools_skips_when_no_urls() -> None:
    chunks, sources, ok, dbg = collect_flow_execute._run_http_tools(_task(link_urls=[]))
    assert ok is False
    assert chunks == []
    assert sources == []
    assert dbg == []


def test_run_rag_skips_when_channel_unavailable() -> None:
    chunks, sources, sub = collect_flow_execute._run_rag(_task(available_channels=["tool"]))
    assert chunks == []
    assert sources == []
    assert sub == []


def test_run_rag_skips_empty_queries() -> None:
    chunks, sources, sub = collect_flow_execute._run_rag(
        _task(
            available_channels=["rag"],
            search_query="   ",
            rag_search_queries=[],
        ),
    )
    assert chunks == []
    assert sub == ["rag_try_skip_empty_queries"]


def test_run_rag_dedupes_and_caps_top_k(monkeypatch: pytest.MonkeyPatch) -> None:
    class Hit:
        def __init__(self, chunk_id: str, text: str) -> None:
            self.chunk_id = chunk_id
            self.text = text

    def fake_search_kb(_q: str, *, top_k: int = 6) -> list[Hit]:
        return [
            Hit("c1", "first chunk"),
            Hit("c1", "duplicate chunk"),
            Hit("c2", "second chunk"),
            Hit("c3", "third chunk"),
        ]

    monkeypatch.setattr(collect_flow_execute, "search_kb", fake_search_kb)
    chunks, sources, sub = collect_flow_execute._run_rag(
        _task(available_channels=["rag"], search_query="query"),
        top_k=2,
    )
    assert len(chunks) == 2
    assert chunks == ["first chunk", "second chunk"]
    assert sources == ["rag", "rag"]
    assert sub and "hits=4" in sub[0]


def test_run_rag_accepts_dict_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        collect_flow_execute,
        "search_kb",
        lambda *_a, **_k: [{"text": "legacy row text", "rowid": 7}],
    )
    chunks, sources, _sub = collect_flow_execute._run_rag(
        _task(available_channels=["rag"], search_query="legacy"),
    )
    assert chunks == ["legacy row text"]
    assert sources == ["rag"]


def test_run_mcp_success_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        collect_flow_execute.mcp_client,
        "call_mcp_tool",
        lambda *_a, **_k: {"ok": True, "transport": "mcp_stdio"},
    )
    chunks, sources, dbg = collect_flow_execute._run_mcp()
    assert chunks == []
    assert sources == []
    assert dbg and "mcp_stdio" in dbg[0]


def test_run_mcp_failure_falls_back_to_sim(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise RuntimeError("mcp down")

    monkeypatch.setattr(collect_flow_execute.mcp_client, "call_mcp_tool", boom)
    chunks, sources, dbg = collect_flow_execute._run_mcp()
    assert chunks == []
    assert sources == []
    assert dbg and "mcp_sim" in dbg[0] and "'transport': 'error'" in dbg[0]


def test_run_step_dispatches_and_updates_holders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        collect_flow_execute,
        "_run_local_file_tools",
        lambda _task: (["local"], ["tool_file"], True, []),
    )
    monkeypatch.setattr(
        collect_flow_execute,
        "_run_http_tools",
        lambda _task: (["http"], ["tool_url"], True, []),
    )
    monkeypatch.setattr(
        collect_flow_execute,
        "_run_rag",
        lambda _task: (["rag"], ["rag"], ["rag_try"]),
    )
    monkeypatch.setattr(
        collect_flow_execute,
        "_run_mcp",
        lambda: ([], [], ["mcp_diag=ok"]),
    )
    monkeypatch.setattr(
        collect_flow_execute,
        "_run_search",
        lambda _task: (["search"], ["web_search"]),
    )

    task = _task(available_channels=["rag", "tool", "mcp"], link_urls=["https://x"])
    hint_holder = [False]
    http_holder = [False]

    lc, ls, ld = collect_flow_execute._run_step(
        task, "local", tool_http_ok_holder=http_holder, hint_ok_holder=hint_holder,
    )
    assert lc == ["local"] and hint_holder[0] is True and ld == []

    hc, hs, hd = collect_flow_execute._run_step(
        task, "http", tool_http_ok_holder=http_holder, hint_ok_holder=hint_holder,
    )
    assert hc == ["http"] and http_holder[0] is True and hd == []

    rc, rs, rsub = collect_flow_execute._run_step(
        task, "rag", tool_http_ok_holder=http_holder, hint_ok_holder=hint_holder,
    )
    assert rc == ["rag"] and rs == ["rag"] and rsub == ["rag_try"]

    mc, ms, mdbg = collect_flow_execute._run_step(
        task, "mcp", tool_http_ok_holder=http_holder, hint_ok_holder=hint_holder,
    )
    assert mc == [] and ms == [] and mdbg == ["mcp_diag=ok"]

    sc, ss, sdbg = collect_flow_execute._run_step(
        _task(enable_web_search=True),
        "search",
        tool_http_ok_holder=http_holder,
        hint_ok_holder=hint_holder,
    )
    assert sc == ["search"] and ss == ["web_search"] and sdbg == []


def test_run_step_unknown_returns_empty() -> None:
    chunks, sources, dbg = collect_flow_execute._run_step(
        _task(),
        "unknown",
        tool_http_ok_holder=[False],
        hint_ok_holder=[False],
    )
    assert chunks == [] and sources == [] and dbg == []
