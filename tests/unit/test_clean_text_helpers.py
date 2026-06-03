"""RAG 检索块排序/去标记与回答侧用到的文本清洗辅助（第四轮 B-022 基线）。"""

from __future__ import annotations

import sys

from tests._support.bootstrap import find_repo_root

ROOT = find_repo_root(__file__)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.result_cleaner import (  # noqa: E402
    demote_boost_preserve_order,
    is_rag_boost_header,
    sort_hits_body_before_boost,
    strip_rag_internal_markers,
)


def test_boost_header_detected_when_markers_present() -> None:
    short = "[doc_path] p [doc_file] f.txt [demo_keywords] k:v"
    assert is_rag_boost_header(short)
    plain = "文档正文不包含上述标记混在一起的长文本" * 5
    assert not is_rag_boost_header(plain)


def test_body_chunks_sort_before_boost() -> None:
    rows = [
        {"text": "[doc_path] x [doc_file] y [demo_keywords] z"},
        {"text": "正文 A"},
        {"text": "[doc_path] x2 [doc_file] y2 [demo_keywords] z2"},
        {"text": "正文 B"},
    ]
    out = sort_hits_body_before_boost(rows)
    texts = [(r.get("text") or "") for r in out]
    assert texts[:2] == ["正文 A", "正文 B"]
    assert all("[doc_path]" in t for t in texts[2:])


def test_demote_boost_then_take_top_k() -> None:
    ranked = [{"text": "boost [doc_path] p [doc_file] f [demo_keywords] kw"}, {"text": "正文优先"}]
    # top_k=1 → 必须把 boost 排后才能让正文胜出
    out = demote_boost_preserve_order(ranked, top_k=1)
    assert len(out) == 1
    assert "正文优先" in (out[0].get("text") or "")


def test_strip_internal_markers_removes_doc_tags() -> None:
    messy = "[doc_path] abc [doc_title] t [demo_keywords] kv"
    cleaned = strip_rag_internal_markers(messy)
    assert "[doc_path]" not in cleaned
    assert "[doc_title]" not in cleaned

