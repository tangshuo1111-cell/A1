"""
main_agent 包：协作总判断 Agent 的 runtime 资产入口。

结构：
- `prompt.py`          ：角色配置 / 系统指令 / 输出格式
- `schema.py`          ：判断对象（MainXiezuoPan / AgnoCollaborationPlan）
- `runtime.py`         ：MainAgent 实体类 + V6 协作主入口
- `rule_router.py`     ：规则路由（_rule_baseline / decide / _routing_brief）
- `main_fallback_rules.py`：v13 fallback 规则

对外只用：
- `MainAgent`（推荐入口）
- `decide`、`build_agno_collaboration_plan` 等保留函数级别名（旧代码兼容）
"""

from __future__ import annotations

from .prompt import JIESHE, PROMPT_MOBAN, SHUCHU_GESHI, ZHIDAO  # noqa: F401
from .rule_router import decide  # noqa: F401
from .runtime import (  # noqa: F401
    MainAgent,
    MainAgentRuntime,
    build_agno_collaboration_plan,
    build_main_xiezuo_pan,
)
from .schema import AgnoCollaborationPlan, MainXiezuoPan  # noqa: F401

__all__ = [
    "MainAgent",
    "MainAgentRuntime",
    "MainXiezuoPan",
    "AgnoCollaborationPlan",
    "decide",
    "build_main_xiezuo_pan",
    "build_agno_collaboration_plan",
    "JIESHE",
    "ZHIDAO",
    "PROMPT_MOBAN",
    "SHUCHU_GESHI",
]

