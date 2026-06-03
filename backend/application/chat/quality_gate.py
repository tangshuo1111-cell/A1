"""Rule-based quality gate — delivery / upgrade only; no lane changes or retrieval."""

from __future__ import annotations

from application.chat.chat_contracts import (
    ExecutorProfile,
    KbSufficiencyResult,
    QualityGateResult,
)

_COMPARISON_CODES = frozenset({"comparison", "pro_con", "cross_material"})
_DEEP_COMPLEX_CODES = frozenset({"decision_tradeoff", "multi_dimension", "solution_design", "multi_analysis", "cross_material", "pro_con"})
_COMPARISON_MARKERS = ("相比", "对比", "优于", "劣于", "异同", "区别", "优缺点", "一方面", "另一方面")
_STRUCTURE_MARKERS = ("1.", "1、", "一、", "首先", "其次", "最后", "总结", "##", "**")
_TRUNCATION_MARKERS = ("[truncated]",)
_DECISION_MARKERS = ("建议", "推荐", "优先", "取舍", "权衡", "最终建议", "结论")
_CASE_MARKERS = ("如果", "若", "情况一", "情况二", "情况三", "场景一", "场景二", "场景三", "分情况")
_INCOMPLETE_TAIL_MARKERS = ("若", "如果", "但", "并且", "同时", "以及", "因此", "所以", "则", "而")
_COMPLETE_ENDING_MARKERS = ("。", "！", "？", ".", "”", "\"")
_SOFT_LIMITATION_MARKERS = (
    "首响预算不足",
    "parallel_budget_zero",
    "本轮按直答快路径处理",
    "未要求事实性证据",
)


def evaluate_quality_gate(
    *,
    executor_profile: ExecutorProfile,
    complex_candidate: bool,
    answer_text: str,
    kb_sufficiency: KbSufficiencyResult | None = None,
    limitations: list[str] | None = None,
    lane: str = "general",
    round_index: int = 0,
    complex_reason_codes: tuple[str, ...] = (),
) -> QualityGateResult:
    text = (answer_text or "").strip()
    lims = list(limitations or [])
    reasons: list[str] = []

    if not text:
        reasons.append("answer_empty")
    elif complex_candidate and len(text) < 80 or not complex_candidate and len(text) < 40:
        reasons.append("answer_too_shallow")

    if any(marker in text for marker in _TRUNCATION_MARKERS):
        reasons.append("answer_truncated")
    if "截断" in text and any(marker in text for marker in ("内容截断", "已截断", "被截断")):
        reasons.append("answer_truncated")
    if text.endswith("…") or text.endswith("..."):
        reasons.append("answer_truncated")

    if _has_blocking_limitations(lims):
        reasons.append("limitations_present")

    kb_in_scope = lane == "kb" or kb_sufficiency is not None
    if (
        kb_in_scope
        and kb_sufficiency is not None
        and not kb_sufficiency.adequate
        and (
            complex_candidate
            or executor_profile == "complex"
            or kb_sufficiency.level in {"none", "insufficient"}
        )
    ):
        reasons.append("kb_insufficient")

    task_codes = set(complex_reason_codes)
    if complex_candidate and executor_profile == "fast":
        has_case_analysis = _has_case_analysis(text)
        has_decision_signal = _has_decision_signal(text)
        if task_codes & _COMPARISON_CODES and not _answer_performs_comparison(text):
            reasons.append("comparison_not_performed")
        if not _has_structure(text) and len(text) < 200:
            reasons.append("structure_not_satisfied")
        if task_codes & _DEEP_COMPLEX_CODES:
            # Length is only a proxy for depth. If the answer already provides
            # case analysis plus a concrete recommendation, do not fail on
            # length alone.
            if len(text) < 180 and not (has_case_analysis and has_decision_signal):
                reasons.append("complex_answer_not_deep_enough")
            strong_reasoning_combo = len(task_codes & {"decision_tradeoff", "multi_dimension", "multi_analysis"}) >= 2
            if strong_reasoning_combo:
                reasons.append("deep_complex_requires_agent")
            if strong_reasoning_combo and len(text) < 220 and not (
                has_case_analysis and has_decision_signal and _has_complete_ending(text)
            ):
                reasons.append("complex_answer_not_deep_enough")
            if ("decision_tradeoff" in task_codes or "multi_dimension" in task_codes) and not has_case_analysis:
                reasons.append("case_analysis_missing")
            if "decision_tradeoff" in task_codes and not has_decision_signal:
                reasons.append("decision_not_made")
            if strong_reasoning_combo and _looks_incomplete_tail(text):
                reasons.append("answer_tail_incomplete")

    reasons = list(dict.fromkeys(reasons))

    if executor_profile == "complex" and round_index == 0 and reasons:
        return QualityGateResult(
            pass_=False,
            need_second_round=True,
            need_more_material="kb_insufficient" in reasons,
            reason_codes=tuple(reasons),
        )

    if executor_profile == "fast" and complex_candidate and reasons:
        return QualityGateResult(
            pass_=False,
            upgrade_profile=True,
            need_more_material="kb_insufficient" in reasons,
            reason_codes=tuple(reasons),
        )

    if executor_profile == "fast" and reasons and ("kb_insufficient" in reasons or "answer_empty" in reasons):
        return QualityGateResult(
            pass_=False,
            upgrade_profile=True,
            need_more_material="kb_insufficient" in reasons,
            reason_codes=tuple(reasons),
        )

    if executor_profile == "complex" and reasons:
        return QualityGateResult(
            pass_=False,
            need_second_round=True,
            need_more_material="kb_insufficient" in reasons,
            reason_codes=tuple(reasons),
        )

    return QualityGateResult(pass_=True, reason_codes=())


def _has_structure(text: str) -> bool:
    return any(marker in text for marker in _STRUCTURE_MARKERS) or text.count("\n") >= 2


def _answer_performs_comparison(text: str) -> bool:
    return any(marker in text for marker in _COMPARISON_MARKERS) or (" vs " in text.lower())


def _has_decision_signal(text: str) -> bool:
    return any(marker in text for marker in _DECISION_MARKERS)


def _has_case_analysis(text: str) -> bool:
    return any(marker in text for marker in _CASE_MARKERS) and _has_structure(text)


def _looks_incomplete_tail(text: str) -> bool:
    stripped = (text or "").rstrip()
    if not stripped:
        return True
    return bool(stripped.endswith(_INCOMPLETE_TAIL_MARKERS))


def _has_complete_ending(text: str) -> bool:
    return (text or "").rstrip().endswith(_COMPLETE_ENDING_MARKERS)


def _has_blocking_limitations(limitations: list[str]) -> bool:
    if not limitations:
        return False
    for limitation in limitations:
        normalized = str(limitation or "").strip()
        if not normalized:
            continue
        if any(marker in normalized for marker in _SOFT_LIMITATION_MARKERS):
            continue
        return True
    return False
