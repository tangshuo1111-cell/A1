"""KI-METRICS-001 回归：FAKE LLM 占位回答应仍显式标注，且能流过未改动的质量门。

背景：旧桩 `测试回答：{text}` 过短无结构，被既有质量门挡在第一步，使 FAKE「验管线连通」跑
被占位文本卡死。修复把桩改成显式标注的结构化回答，让连通跑能真正流过质量门。

本测试**不放宽**质量门，只断言：
1. 桩仍显式标注为测试桩（不冒充真实质量）；
2. 桩不含会触发诚实性 claims 的「知识库/网页/视频」措辞；
3. 桩能流过既有 `evaluate_quality_gate`（complex / fast+complex_candidate 路径）。
"""

from __future__ import annotations

from agents.answer_agent.llm_exec import _fake_answer_stub
from application.chat.quality_gate import evaluate_quality_gate


def test_fake_stub_is_explicitly_labelled() -> None:
    stub = _fake_answer_stub("如何对比方案 A 与方案 B？")
    assert "测试回答" in stub and "FAKE" in stub
    assert "不代表真实回答质量" in stub
    # 不得包含会触发 claims_kb / claims_web / claims_video 的伪造证据措辞
    for forbidden in ("知识库", "网页", "视频"):
        assert forbidden not in stub


def test_fake_stub_flows_through_complex_quality_gate() -> None:
    stub = _fake_answer_stub("请对比两种缓存方案的取舍并给出建议。")
    result = evaluate_quality_gate(
        executor_profile="complex",
        complex_candidate=True,
        answer_text=stub,
        round_index=0,
        complex_reason_codes=("decision_tradeoff", "comparison"),
    )
    assert result.pass_ is True
    assert result.reason_codes == ()


def test_fake_stub_flows_through_fast_complex_candidate_gate() -> None:
    stub = _fake_answer_stub("对比两个方案的优缺点。")
    result = evaluate_quality_gate(
        executor_profile="fast",
        complex_candidate=True,
        answer_text=stub,
        round_index=0,
        complex_reason_codes=("comparison",),
    )
    assert result.pass_ is True
    assert result.upgrade_profile is False
