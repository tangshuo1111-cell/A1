"""Task-shape complexity signals — single source for complex_candidate (doc §1.2)."""

from __future__ import annotations

import re

from application.chat.chat_contracts import ComplexCandidateSignal

_STRONG_COMPARE = ("对比", "比较", "异同", "优缺点", "适用场景")
_STRONG_DECISION = ("推荐", "取舍", "权衡", "优先级", "排序", "选哪个", "做决策", "帮我做决策", "该不该", "应该怎么选")
_STRONG_MULTI_DIM = ("多个角度", "多个维度", "分情况", "从不同", "三个角度", "四个角度", "五个角度")
_STRONG_DEBATE = ("正反", "支持与反对", "双边论证", "辩证", "支持论据", "反对论据", "支持者", "反对者", "两边")
_STRONG_CROSS_MATERIAL = ("综合判断", "结合多", "跨材料", "多份知识", "多份文档")
_STRONG_DESIGN = ("设计方案", "整改路径", "阶段计划", "路线图")
_STRONG_DIAGNOSTIC = ("可能解释", "验证方法", "原因是什么", "机制层面")

_WEAK_COMPLEX = ("综合", "评估", "分析", "分别", "同时", "并给出")

_SIMPLE_EXPLAIN = ("是什么", "什么意思", "定义", "解释", "含义")


def evaluate_complex_candidate(message: str) -> ComplexCandidateSignal:
    msg = (message or "").strip()
    if not msg:
        return ComplexCandidateSignal()

    triggers: list[str] = []
    codes: list[str] = []

    def _hit(tokens: tuple[str, ...], code: str, tier: str) -> None:
        if any(token in msg for token in tokens):
            triggers.append(f"{tier}:{code}")
            if code not in codes:
                codes.append(code)

    _hit(_STRONG_COMPARE, "comparison", "strong")
    _hit(_STRONG_DECISION, "decision_tradeoff", "strong")
    _hit(_STRONG_MULTI_DIM, "multi_dimension", "strong")
    _hit(_STRONG_DEBATE, "pro_con", "strong")
    _hit(_STRONG_CROSS_MATERIAL, "cross_material", "strong")
    _hit(_STRONG_DESIGN, "solution_design", "strong")
    _hit(_STRONG_DIAGNOSTIC, "diagnostic_reasoning", "strong")
    _hit(_WEAK_COMPLEX, "multi_analysis", "weak")

    if len(re.findall(r"[?？]", msg)) >= 2 and len(msg) > 60:
        triggers.append("weak:multi_question")
        if "multi_question" not in codes:
            codes.append("multi_question")

    is_simple = (
        len(msg) <= 80
        and any(token in msg for token in _SIMPLE_EXPLAIN)
        and not codes
    )
    if is_simple:
        return ComplexCandidateSignal(complex_candidate=False)

    strong = any(t.startswith("strong:") for t in triggers)
    weak = any(t.startswith("weak:") for t in triggers)
    return ComplexCandidateSignal(
        complex_candidate=strong or (weak and len(msg) > 40),
        triggers=tuple(triggers),
        reason_codes=tuple(codes),
    )


# ---------------------------------------------------------------------------
# 意图词汇（单一事实源）— 供链路代码调用的谓词，链路自身不得内联词表。
# 这些词表此前散落在 fast_lane_gate / main_invoke_flow，现统一收口到此。
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# 强复杂信号：出现这些 reason code 时，即便 ingress 判 fast 也应让位给 complex 主链。
_COMPLEX_DEFER_CODES = frozenset({
    "comparison",
    "cross_material",
    "decision_tradeoff",
    "multi_dimension",
    "solution_design",
})

# 显式「读多篇网页/多来源/知识库+网页」措辞。
_MULTI_READ_HINTS = (
    "多来源", "多个来源", "多源", "几个网页", "多个网页",
    "结合知识库和网页", "结合知识库与网页", "结合知识库和网络", "知识库和网页",
)

# 「读/阅读 N 篇/个网页」「前 N 篇」「N 个网页/页面」等数字研读措辞（空格可有可无，全/半角兼容）。
_MULTI_READ_RE = re.compile(
    r"(读|阅读|看)\s*(前\s*)?[0-9一二两三四五]\s*[～~\-到]?\s*[0-9一二两三四五]?\s*(篇|个|页|份)"
    r"|前\s*[0-9一二两三四五]\s*(篇|个|页)"
    r"|[0-9一二两三四五]\s*[～~\-到]?\s*[0-9一二两三四五]?\s*个?\s*网页"
)

# web_url 预备纠偏用：分析诉求动词 / 保存入库动词（原 main_invoke_flow 内联词表，原样迁入）。
_ANALYSIS_VERBS = ("分析", "对比", "比较", "异同", "要点", "综合", "评估", "总结", "概括")
_SAVE_VERBS = ("保存", "入库", "存到", "存起来", "收藏", "存入", "save")


def has_multisource_intent(message: str) -> bool:
    """判断 web/kb fast 候选是否其实是复杂多源题（应让位给 Middle 工具链）。"""
    msg = (message or "").strip()
    if not msg:
        return False
    # 多 URL：典型多源对比
    if len(set(_URL_RE.findall(msg))) >= 2:
        return True
    # 显式多篇阅读 / 知识库+网页结合
    if any(hint in msg for hint in _MULTI_READ_HINTS):
        return True
    if _MULTI_READ_RE.search(msg):
        return True
    # 任务形态强复杂信号
    signal = evaluate_complex_candidate(msg)
    return bool(signal.complex_candidate and set(signal.reason_codes) & _COMPLEX_DEFER_CODES)


def is_analysis_request(message: str) -> bool:
    """消息是否表达「分析/对比/总结要点」这类取证分析诉求。"""
    msg = message or ""
    return any(v in msg for v in _ANALYSIS_VERBS)


def is_save_request(message: str) -> bool:
    """消息是否表达「保存/入库/收藏」这类落库诉求（轻量动词级，区别于 commit 高置信兜底）。"""
    msg = message or ""
    return any(v in msg for v in _SAVE_VERBS)
