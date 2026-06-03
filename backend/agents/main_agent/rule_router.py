"""
main_agent 规则路由：_rule_baseline / decide / _routing_brief 等纯规则判断逻辑。

本文件为薄门面；检测见 `rule_router_patterns.py`，基线见 `rule_router_baseline.py`，
摘要见 `rule_router_summary.py`。

只负责一件事：根据 TaskInput 产出 MainDecision（规则基线 + 可选 LLM refine）。

V12 R2 边界说明
==============
本路由中以 `_v10_fallback_intent_from_high_confidence_rules` 为入口的 fallback 规则集
（位于 `main_fallback_rules.py`），遵守以下不变量（invariants）：

1. 规则数量上限（MAX_FALLBACK_RULES）：当前 4 条，上限 6 条（V10 主路由 fallback）。
   超过上限说明 fallback 正在膨胀成主路由器，必须先删除再新增。
   V13 prepare/commit fallback 另计（上限 5 条，当前 5 条；见 v13_fallback_* 函数）。

2. 每条规则必须满足「硬解剖学要件」：
   - 必须含极强模板词 / 结构特征（不能是宽泛词表）
   - 宁可漏判，不能误判（conservative over aggressive）

3. fallback 只在 LLM 不可用 / 失败 / 超时时触发，不在 LLM 成功时触发。

4. 新增规则必须：
   - 在代码注释里说明「硬解剖学要件」
   - 在 test_v12r1_rag_main_chain.py 中补对应测试
   - 不能是「大词表匹配」或「宽泛语义猜测」

5. 禁止复活以下旧规则（V6 R9 主动放弃）：
   - _mentions_project_or_repo（单个词匹配，宽泛）
   - _looks_like_general_world_knowledge（语义猜测）
   - _extended_smalltalk（宽泛闲聊）
   - 任何词表超过 20 个词的宽匹配规则
"""

from __future__ import annotations

from debug_trace import trace
from llm.router import maybe_refine_with_llm
from schemas import MainDecision, TaskInput

from . import rule_router_patterns as _pat
from .rule_router_baseline import _rule_baseline
from .rule_router_summary import (
    _clamp_core_fields,
    _default_routing_explain,
    _routing_brief,
)


def decide(task: TaskInput) -> MainDecision:
    """规则基线 + 可选 LLM 精炼。"""
    base = _rule_baseline(task)
    final = maybe_refine_with_llm(task, base)
    final = _clamp_core_fields(final)
    final = _pat._apply_answer_channel_guard(task, base, final)
    explain = (final.routing_explain or "").strip() or _default_routing_explain(final)
    final = final.model_copy(
        update={
            "routing_explain": explain,
            "routing_brief": _routing_brief(final),
        }
    )
    trace(
        f"main_agent.decide task_id={task.task_id} need_rag={final.need_rag} "
        f"need_external={final.need_external_info} need_tool_local={final.need_tool_local} "
        f"need_context={final.need_context} router={final.router_source} "
        f"priority={final.middle_collect_priority} style={final.answer_style}"
    )
    trace(
        f"main_agent.fields task_id={final.task_id} "
        f"primary_goal={final.primary_goal[:100]!r} "
        f"answer_style={final.answer_style} is_compound={final.is_compound} "
        f"middle_collect_priority={final.middle_collect_priority} "
        f"style_hint={final.answer_style_hint[:60]!r}"
    )
    trace(f"main_agent.routing_brief task_id={final.task_id} {final.routing_brief[:220]}")
    trace(
        f"main_agent.core_fields task_id={final.task_id} "
        f"primary_goal={final.primary_goal[:80]!r} is_compound={final.is_compound} "
        f"middle_collect_priority={final.middle_collect_priority} "
        f"answer_style={final.answer_style} router_source={final.router_source}"
    )
    trace(
        f"main_agent.routing_explain task_id={final.task_id} {final.routing_explain[:200]!r}"
    )
    return final
