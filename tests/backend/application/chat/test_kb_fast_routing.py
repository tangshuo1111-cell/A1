from __future__ import annotations

from types import SimpleNamespace

from application.chat.fast_path_entry import _kb_should_prefer_complex


def test_kb_prefers_complex_for_strong_compare_shape() -> None:
    ingress = SimpleNamespace(
        complex_candidate=True,
        complex_reason_codes=["comparison", "multi_dimension"],
    )
    ranked = [object(), object(), object()]
    assert _kb_should_prefer_complex(
        message="请基于知识库，对比这三条主链并给出取舍。",
        ingress=ingress,
        ranked=ranked,
        evidence_tier="strong",
    ) is True


def test_kb_fast_kept_for_simple_explain_question() -> None:
    ingress = SimpleNamespace(
        complex_candidate=False,
        complex_reason_codes=[],
    )
    ranked = [object(), object(), object()]
    assert _kb_should_prefer_complex(
        message="请基于知识库解释什么是 quality gate。",
        ingress=ingress,
        ranked=ranked,
        evidence_tier="strong",
    ) is False
