"""第三轮：retrieve_knowledge 三路策略（stub 下层实现，不接真实 PG）。"""
from __future__ import annotations

import sys

import pytest
from tests._support.bootstrap import find_repo_root

REPO_ROOT = find_repo_root(__file__)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import rag.retrieve_knowledge_core as rkc  # noqa: E402
from rag.retrieve_knowledge import retrieve_knowledge  # noqa: E402
from rag.schema import RetrievedChunk  # noqa: E402


def _chunk_kw(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        source_id="src_kw",
        chunk_id="src_kw::chunk::1",
        text=text,
        score_raw=3.1,
        score_normalized=1.0,
        score_keyword=1.0,
        score_semantic=0.0,
        combined_score=1.0,
        retrieval_strategy="keyword",
    )


def _chunk_hybrid(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        source_id="src_hybrid",
        chunk_id="src_hybrid::chunk::1",
        text=text,
        score_raw=0.92,
        score_normalized=0.92,
        score_keyword=0.8,
        score_semantic=0.95,
        combined_score=0.88,
        retrieval_strategy="hybrid",
    )


def _chunk_scored_json(text: str) -> RetrievedChunk:
    return RetrievedChunk(
        source_id="benchmark:agent-eval-2026-05-26-a:scored-json",
        chunk_id="benchmark:agent-eval-2026-05-26-a:scored-json::chunk::1",
        text=text,
        score_raw=0.98,
        score_normalized=0.98,
        score_keyword=0.95,
        score_semantic=0.96,
        combined_score=0.955,
        retrieval_strategy="hybrid",
    )


def test_keyword_path_uses_keyword_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rkc, "_do_keyword", lambda *_a, **_k: [_chunk_kw("foo bar")])

    chunks, ti = retrieve_knowledge("hello", strategy="keyword", top_k=3)

    assert len(chunks) == 1
    assert ti["strategy_used"].startswith("keyword")
    assert not ti["no_match"]


def test_semantic_path_when_embedding_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    def _do_semantic(q: str, top_k: int) -> list[RetrievedChunk]:
        assert q
        c = RetrievedChunk(
            source_id="s",
            chunk_id="s::1",
            text="semantic-hit",
            score_raw=0.9,
            score_normalized=0.9,
            score_keyword=0.2,
            score_semantic=0.95,
            combined_score=0.95,
            retrieval_strategy="semantic",
        )
        return rkc._finalize_semantic_scores([c])

    monkeypatch.setattr(rkc, "_do_semantic", _do_semantic)

    chunks, ti = retrieve_knowledge(
        "v14-r2-demo",
        strategy="semantic",
        top_k=2,
        embedding_enabled=True,
    )

    assert ti["strategy_used"] == "semantic"
    assert chunks and chunks[0].text == "semantic-hit"


def test_semantic_degrades_keyword_when_embeddings_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rkc,
        "_do_keyword",
        lambda *_a, **_k: [_chunk_kw("degraded-keyword")],
    )

    chunks, ti = retrieve_knowledge(
        "x",
        strategy="semantic",
        embedding_enabled=False,
        top_k=4,
    )

    assert chunks
    assert "embedding_disabled" in ti["strategy_used"]


def test_hybrid_degrades_keyword_when_embeddings_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rkc,
        "_do_keyword",
        lambda *_a, **_k: [_chunk_kw("only-keyword-branch")],
    )

    chunks, ti = retrieve_knowledge(
        "y",
        strategy="hybrid",
        embedding_enabled=False,
        top_k=4,
    )

    assert chunks
    assert ti["strategy_used"].startswith("keyword")


def test_hybrid_keeps_strategy_tag_when_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rkc, "_do_hybrid", lambda *_a, **_k: [_chunk_hybrid("mix")])

    chunks, ti = retrieve_knowledge(
        "z",
        strategy="hybrid",
        embedding_enabled=True,
        top_k=2,
    )

    assert ti["strategy_used"] == "hybrid"
    assert chunks[0].combined_score > 0


def test_default_source_policy_excludes_benchmark_scored_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rkc,
        "_do_hybrid",
        lambda *_a, **_k: [_chunk_scored_json("json"), _chunk_hybrid("good-doc")],
    )

    chunks, ti = retrieve_knowledge(
        "complex candidate 为什么不稳定进入 Agent",
        strategy="hybrid",
        embedding_enabled=True,
        top_k=4,
    )

    assert len(chunks) == 1
    assert chunks[0].source_id == "src_hybrid"
    assert ti["default_source_policy"] == "exclude_benchmark_scored_json"


def test_source_id_filter_can_override_default_source_exclusion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rkc,
        "_do_hybrid",
        lambda *_a, **_k: [_chunk_scored_json("json"), _chunk_hybrid("good-doc")],
    )

    chunks, _ti = retrieve_knowledge(
        "complex candidate 为什么不稳定进入 Agent",
        strategy="hybrid",
        embedding_enabled=True,
        top_k=4,
        filters={"source_id": "benchmark:agent-eval-2026-05-26-a:scored-json"},
    )

    assert len(chunks) == 1
    assert chunks[0].source_id == "benchmark:agent-eval-2026-05-26-a:scored-json"
