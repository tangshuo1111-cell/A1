"""产品指标目标线（观测口径，非线上 SLO 门禁）。

集中定义北极星 / Guardrail 的达标线与样本有效性下限，供 analytics 聚合与周报判定共用。
当前数据来自离线沙箱代表题：样本量未到有效区间时只出"样本不足"，不下达标结论，避免小样本误导。
"""

from __future__ import annotations

from dataclasses import dataclass

# 三态状态码（达标 / 未达标 / 样本不足）
STATUS_PASS = "达标"
STATUS_FAIL = "未达标"
STATUS_INSUFFICIENT_SAMPLE = "样本不足"


@dataclass(frozen=True)
class MetricTarget:
    """单条产品指标的目标线与样本有效性下限。

    direction:
      - "min"：value >= target 视为达标（越大越好，如北极星完成率）
      - "max"：value <= target 视为达标（越小越好，如 partial / insufficiency 率）
    sample_key：agg 中作为该指标分母 / 样本量的字段名
    min_sample：样本量低于该值时不下达标结论，标为"样本不足"
    """

    key: str
    label: str
    target: float
    direction: str
    sample_key: str
    min_sample: int
    is_north_star: bool = False


NORTH_STAR_KNOWLEDGE_REUSE = MetricTarget(
    key="knowledge_reuse_rate",
    label="资料二次调用率（北极星1）",
    target=0.40,
    direction="min",
    sample_key="retrieval_turn_count",
    min_sample=30,
    is_north_star=True,
)

NORTH_STAR_COMPLEX_COMPLETE = MetricTarget(
    key="complex_effective_complete_rate",
    label="复杂任务有效完成率（北极星2）",
    target=0.70,
    direction="min",
    sample_key="complex_task_count",
    min_sample=30,
    is_north_star=True,
)

GUARDRAIL_PARTIAL_RATE = MetricTarget(
    key="partial_rate",
    label="Partial（部分交付）率",
    target=0.30,
    direction="max",
    sample_key="turns_total",
    min_sample=30,
)

GUARDRAIL_INSUFFICIENCY_RATE = MetricTarget(
    key="insufficiency_rate",
    label="insufficiency（证据不足）占比",
    target=0.25,
    direction="max",
    sample_key="turns_total",
    min_sample=30,
)

PRODUCT_METRIC_TARGETS: tuple[MetricTarget, ...] = (
    NORTH_STAR_KNOWLEDGE_REUSE,
    NORTH_STAR_COMPLEX_COMPLETE,
    GUARDRAIL_PARTIAL_RATE,
    GUARDRAIL_INSUFFICIENCY_RATE,
)
