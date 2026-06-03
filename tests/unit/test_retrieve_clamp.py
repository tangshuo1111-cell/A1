"""rag.retrieve_knowledge：top_k clamp 到 COST.rag_max_top_k。"""

from __future__ import annotations

import importlib
import sys

import pytest
from tests._support.bootstrap import find_repo_root

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _reload_cost_rule() -> None:
    import config.cost_rule as cr

    importlib.reload(cr)


@pytest.fixture(autouse=True)
def _restore_rag_top_k(monkeypatch: pytest.MonkeyPatch) -> None:
    yield
    monkeypatch.delenv("RAG_MAX_TOP_K", raising=False)
    _reload_cost_rule()


def test_trace_top_k_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_MAX_TOP_K", "4")
    _reload_cost_rule()
    from rag.retrieve_knowledge import retrieve_knowledge

    _chunks, trace = retrieve_knowledge("noop-query", top_k=99, strategy="keyword")
    assert trace["top_k"] == 4
    assert len(_chunks) <= 4


def test_zero_rag_max_top_k_clamps_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_MAX_TOP_K", "0")
    _reload_cost_rule()
    from rag.retrieve_knowledge import retrieve_knowledge

    _chunks, trace = retrieve_knowledge("x", top_k=10, strategy="keyword")
    assert trace["top_k"] == 0


def test_requested_smaller_than_cap_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_MAX_TOP_K", "50")
    _reload_cost_rule()
    from rag.retrieve_knowledge import retrieve_knowledge

    _chunks, trace = retrieve_knowledge("y", top_k=3, strategy="keyword")
    assert trace["top_k"] == 3
