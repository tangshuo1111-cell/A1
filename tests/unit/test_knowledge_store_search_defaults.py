from __future__ import annotations

import sys

from tests._support.bootstrap import find_repo_root

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_knowledge_store_search_requests_auto_by_default(monkeypatch) -> None:
    from storage import knowledge_store

    recorded: dict[str, object] = {}

    def _fake_retrieve(query: str, *, top_k: int = 5, strategy: str = "auto", **_: object):
        recorded["query"] = query
        recorded["top_k"] = top_k
        recorded["strategy"] = strategy
        return [], {
            "strategy_requested": strategy,
            "strategy_used": "auto:keyword",
            "auto_reason": "test",
            "no_match": True,
        }

    monkeypatch.setattr("rag.retrieve_knowledge.retrieve_knowledge", _fake_retrieve)

    chunks = knowledge_store.search("kb search facade default", top_k=7)

    assert chunks == []
    assert recorded["query"] == "kb search facade default"
    assert recorded["top_k"] == 7
    assert recorded["strategy"] == "auto"
