"""产品指标 v1 聚合逻辑单元测试。"""

from __future__ import annotations

from application.analytics.product_metrics import aggregate_turn_rows, is_effective_complete


def _row(**kwargs):
    extra = dict(kwargs.pop("extra", {}))
    return {"task_status": kwargs.get("task_status", "succeeded"), "extra": extra}


def test_effective_complete_excludes_partial_and_insufficiency() -> None:
    assert is_effective_complete(
        {"insufficient_evidence": False, "quality_gate_passed": True},
        {"task_status": "partial"},
    ) is False
    assert is_effective_complete(
        {"insufficient_evidence": True, "quality_gate_passed": True},
        {"task_status": "succeeded"},
    ) is False


def test_aggregate_sample_and_top3() -> None:
    rows = [
        _row(
            task_status="succeeded",
            extra={
                "is_complex_task": True,
                "quality_gate_passed": True,
                "insufficient_evidence": False,
                "failure_reason_code": "success",
                "v15_retrieved_chunks_count": 2,
            },
        ),
        _row(
            task_status="partial",
            extra={
                "is_complex_task": True,
                "insufficient_evidence": True,
                "quality_gate_passed": False,
                "failure_reason_code": "insufficiency",
            },
        ),
        _row(
            task_status="partial",
            extra={
                "is_complex_task": False,
                "failure_reason_code": "timeout_partial",
            },
        ),
    ]
    stats = aggregate_turn_rows(rows)
    assert stats["turns_total"] == 3
    assert stats["eval_item_count"] == 3
    assert stats["complex_task_count"] == 2
    assert stats["complex_effective_complete_rate"] == 0.5
    assert stats["partial_rate"] == 2 / 3
    assert len(stats["failure_top3"]) >= 1
    assert stats["failure_top3"][0]["code"] in {"insufficiency", "timeout_partial"}
