"""产品指标目标线三态判定（达标 / 未达标 / 样本不足）单元测试。"""

from __future__ import annotations

from application.analytics.product_metrics import evaluate_targets
from config.metric_targets import (
    GUARDRAIL_PARTIAL_RATE,
    NORTH_STAR_COMPLEX_COMPLETE,
    STATUS_FAIL,
    STATUS_INSUFFICIENT_SAMPLE,
    STATUS_PASS,
)


def _verdict(agg, target):
    """跑 evaluate_targets，取出指定 target 的判定。"""
    out = evaluate_targets(agg, targets=(target,))
    return out[0]


def test_north_star_pass_when_sample_enough_and_above_target() -> None:
    agg = {"complex_effective_complete_rate": 0.72, "complex_task_count": 30}
    v = _verdict(agg, NORTH_STAR_COMPLEX_COMPLETE)
    assert v["status"] == STATUS_PASS
    assert v["is_north_star"] is True
    assert v["sample_n"] == 30


def test_north_star_fail_when_sample_enough_but_below_target() -> None:
    agg = {"complex_effective_complete_rate": 0.55, "complex_task_count": 40}
    v = _verdict(agg, NORTH_STAR_COMPLEX_COMPLETE)
    assert v["status"] == STATUS_FAIL


def test_north_star_insufficient_sample_overrides_high_value() -> None:
    # 复杂子集 < 30：即使比率很高也不下达标结论
    agg = {"complex_effective_complete_rate": 0.95, "complex_task_count": 20}
    v = _verdict(agg, NORTH_STAR_COMPLEX_COMPLETE)
    assert v["status"] == STATUS_INSUFFICIENT_SAMPLE


def test_none_value_is_insufficient_sample() -> None:
    agg = {"complex_effective_complete_rate": None, "complex_task_count": 0}
    v = _verdict(agg, NORTH_STAR_COMPLEX_COMPLETE)
    assert v["status"] == STATUS_INSUFFICIENT_SAMPLE


def test_guardrail_max_direction_pass_and_fail() -> None:
    # partial_rate 越小越好，目标 <= 0.30
    passing = _verdict({"partial_rate": 0.20, "turns_total": 30}, GUARDRAIL_PARTIAL_RATE)
    assert passing["status"] == STATUS_PASS
    failing = _verdict({"partial_rate": 0.45, "turns_total": 30}, GUARDRAIL_PARTIAL_RATE)
    assert failing["status"] == STATUS_FAIL


def test_default_targets_cover_north_star_and_guardrails() -> None:
    agg = {
        "complex_effective_complete_rate": 0.8,
        "complex_task_count": 35,
        "partial_rate": 0.1,
        "insufficiency_rate": 0.1,
        "turns_total": 35,
    }
    verdicts = evaluate_targets(agg)
    assert any(v["is_north_star"] for v in verdicts)
    assert all(v["status"] == STATUS_PASS for v in verdicts)
    assert len(verdicts) >= 3
