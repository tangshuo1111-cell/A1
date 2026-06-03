"""
answer_agent 包：唯一 Final Answer Agent 的 runtime 资产入口。

结构：
- `prompt.py`      ：角色配置 / 系统指令 / 输出格式
- `schema.py`      ：判断对象（HuidaPan）
- `runtime.py`     ：AnswerAgent 实体类 + V6 回答主入口
- `llm_exec.py`    ：内部 LLM 执行器
- `answer_flow.py` ：legacy 模板组装与 helper（仅旧测试 / 旧入口兼容）

默认主链对外只用：
- `AnswerAgent`（推荐入口）
- `pan_huida_agno` 等运行时入口

兼容保留：
- `answer` 仅供旧测试 / 旧入口使用，不作为 `/chat/agno` 默认主链语义锚点
"""

from __future__ import annotations

from .answer_flow import answer  # noqa: F401
from .llm_exec import reset_agent_cache_for_tests, run_basic_qa  # noqa: F401
from .prompt import (  # noqa: F401
    ASSISTANT_INSTRUCTIONS,
    JIESHE,
    PROMPT_MOBAN,
    SHUCHU_GESHI,
    ZHIDAO,
)
from .runtime import (  # noqa: F401
    AnswerAgent,
    AnswerAgentRuntime,
    agno_lane_decision,
    huida_to_executor_hint,
    pan_huida_agno,
    xiezuo_extra_for_service,
)
from .schema import HuidaPan  # noqa: F401

__all__ = [
    "AnswerAgent",
    "AnswerAgentRuntime",
    "HuidaPan",
    "answer",
    "pan_huida_agno",
    "huida_to_executor_hint",
    "xiezuo_extra_for_service",
    "agno_lane_decision",
    "run_basic_qa",
    "reset_agent_cache_for_tests",
    "JIESHE",
    "ZHIDAO",
    "PROMPT_MOBAN",
    "SHUCHU_GESHI",
    "ASSISTANT_INSTRUCTIONS",
]

