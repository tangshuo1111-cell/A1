"""
middle_agent 包：材料裁判 Agent 的 runtime 资产入口。

结构（V6 第 6 轮 runtime 化）：
- `prompt.py` ：角色配置 / 系统指令 / 输出格式
- `schema.py` ：判断对象（CailiaoPan / AgnoMaterialBundle）
- `runtime.py`：MiddleAgent 实体类 + V6 材料裁判主入口（caipan / gather_agno_materials …）
- `collect_flow.py` ：旧主链 `collect()` 多路取材（RAG / Tool / MCP），供旧主链 + 旧测试兼容 import

治理台账 G-005（Middle 拆分）列名模块：
- `material_policy.py`：路径/mp4 抽取、trace 路由标签、KB 硬度、`tools_allowed`
- `tool_dispatch.py`：多工具逐步调度（prepare/commit/retrieve + registry 分发）
- `multisource_round.py`：多来源 tool_plan 轮次聚合 → bundle
- `retrieval_flow.py`：KB 检索聚块（V8 前文锚点 / V14 trace）；由 `gather_phase` 委托
- `pending_flow.py`：V13 prepare/commit 生命周期；由 `invoke_tail_flow` 委托
- `bundle_finalize_flow.py`：invoke 末段 trace（至 V12）+ V13 后 V15 收口；由 `invoke_tail_flow` 委托
- `invoke_tail_flow.py`：gather 完成后 trace / V13 / finalize → `AgnoMaterialBundle`；由 `runtime.invoke_executor` 委托
- `gather_phase.py`：invoke gather 阶段（意图→KB/Web→判决→MCP 视频）；以 `MiddleGatherPhaseMixin` 混入 `MiddleAgentRuntime`
- `judgment_phase.py`：五段主判断（意图 / KB·Web 策略 / `CailiaoPan` / 失败边界 / 兜底）+ V8 前文承接 / V11 保存意图；以 `MiddleJudgmentPhaseMixin` 混入 `MiddleAgentRuntime`

模块职责见各文件头注释。

对外只用：
- `MiddleAgent`（推荐入口）
- `collect`、`gather_agno_materials` 等保留函数级别名（旧代码兼容）
"""

from __future__ import annotations

from . import pending_flow as v13_pending_flow  # noqa: F401  historical import alias
from .collect_flow import collect  # noqa: F401
from .prompt import JIESHE, PROMPT_MOBAN, SHUCHU_GESHI, ZHIDAO  # noqa: F401
from .runtime import (  # noqa: F401
    MiddleAgent,
    MiddleAgentRuntime,
    gather_agno_materials,
)
from .schema import AgnoMaterialBundle, CailiaoPan  # noqa: F401

__all__ = [
    "MiddleAgent",
    "MiddleAgentRuntime",
    "CailiaoPan",
    "AgnoMaterialBundle",
    "collect",
    "gather_agno_materials",
    "JIESHE",
    "ZHIDAO",
    "PROMPT_MOBAN",
    "SHUCHU_GESHI",
    "v13_pending_flow",
]
