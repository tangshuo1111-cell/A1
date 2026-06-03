"""路由摘要字段：字段收口、默认 routing_explain、routing_brief 可读摘要。"""

from __future__ import annotations

from schemas import MainDecision

from .rule_router_patterns import _ALLOWED_PRIORITY, _ALLOWED_STYLE


def _clamp_core_fields(d: MainDecision) -> MainDecision:
    """收口主判断字段，避免异常值导致 middle/answer 行为漂移。"""
    p = d.middle_collect_priority if d.middle_collect_priority in _ALLOWED_PRIORITY else "balanced"
    s = d.answer_style if d.answer_style in _ALLOWED_STYLE else "general"
    if p == d.middle_collect_priority and s == d.answer_style:
        return d
    return d.model_copy(update={"middle_collect_priority": p, "answer_style": s})


def _default_routing_explain(d: MainDecision) -> str:
    """当 LLM 未写 routing_explain 时，用 router_source 生成稳定说明（V4）。"""
    rs = (d.router_source or "rules").lower()
    if rs == "rules":
        return (
            "本轮由规则引擎根据关键词、是否含链接、是否追问与会话摘要是否命中，"
            "决定 need_rag / need_tool_local / need_external 及资料优先级与回答风格。"
        )
    if rs == "llm":
        return (
            "本轮由 LLM 路由器输出主目标、是否复合问、各 need_* 标志与 middle_collect_priority；"
            "无 Key 或失败时会回退规则。"
        )
    if rs in ("hybrid", "mixed"):
        return (
            "混合路由（mixed）：寒暄等硬规则锁定「关检索」；"
            "primary_goal / answer_style 等可由 LLM 微调。"
        )
    return "路由来源未识别，请检查 router_source 字段。"


def _routing_brief(d: MainDecision) -> str:
    """主判断可读摘要（增强真实感：一眼看懂本轮路由）。"""
    g = (d.primary_goal or "").replace("\n", " ")[:100]
    ah = (d.answer_style_hint or "").replace("\n", " ")
    ah_disp = (f"{ah[:48]!r}" + ("…" if len(ah) > 48 else "")) if ah else "（无）"
    rs = "mixed" if d.router_source == "hybrid" else d.router_source
    flags = (
        f"需RAG={d.need_rag} 需上下文={d.need_context} "
        f"需外链={d.need_external_info} 需本地读={d.need_tool_local}"
    )
    return (
        f"主目标={g!r} | 复合问题={d.is_compound} | {flags} | "
        f"资料优先={d.middle_collect_priority} 回答侧重={d.answer_style} | "
        f"风格提示={ah_disp} | 路由源={rs}"
    )
