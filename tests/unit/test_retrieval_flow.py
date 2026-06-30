"""retrieval_flow 出口形态 characterization。"""

from __future__ import annotations

from types import SimpleNamespace

from agents.middle_agent.retrieval_flow import run_kb_retrieval_gather


def _plan(*, tools_allowed: tuple[str, ...] = ("retrieve_knowledge",)) -> SimpleNamespace:
    return SimpleNamespace(
        retrieval_strategy="auto",
        retrieval_filters={},
        tools_allowed=tools_allowed,
    )


def test_run_kb_retrieval_gather_skips_when_try_rag_false() -> None:
    out = run_kb_retrieval_gather(
        try_rag=False,
        msg="hello",
        plan=_plan(),
        v8_history_used=False,
        v8_anchor=None,
        v8_followup_query="",
        blocked_failures=[],
    )
    assert out.knowledge_block is None
    assert out.retrieved_chunks == []
    assert out.v8_history_anchor_status == "none"


def test_run_kb_retrieval_gather_hits(monkeypatch) -> None:
    class Chunk:
        def to_context_line(self) -> str:
            return "chunk-one"

    def fake_retrieve(*_args, **_kwargs):
        return [Chunk()], {"strategy_used": "auto", "hits": 1}

    monkeypatch.setattr(
        "agents.middle_agent.retrieval_flow._retrieve_svc.retrieve_knowledge",
        fake_retrieve,
    )
    out = run_kb_retrieval_gather(
        try_rag=True,
        msg="query",
        plan=_plan(),
        v8_history_used=False,
        v8_anchor=None,
        v8_followup_query="",
        blocked_failures=[],
    )
    assert out.knowledge_block == "chunk-one"
    assert len(out.retrieved_chunks) == 1
    assert out.v14_trace_info == {"strategy_used": "auto", "hits": 1}


def test_run_kb_retrieval_gather_blocked_when_tool_not_allowed() -> None:
    blocked: list[dict] = []
    out = run_kb_retrieval_gather(
        try_rag=True,
        msg="query",
        plan=_plan(tools_allowed=()),
        v8_history_used=False,
        v8_anchor=None,
        v8_followup_query="",
        blocked_failures=blocked,
    )
    assert out.knowledge_block is None
    assert blocked and blocked[0]["reason"] == "not_allowed_by_plan"
