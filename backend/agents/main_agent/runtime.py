"""
main_agent runtime：MainAgent 实体类 + 自有 `MainAgentRuntime` agent 实体。

V6 第 8 轮（真 agent / 强 agent）→ 第 9 轮（终验补强）：
- main 自己拥有 `MainAgentRuntime`（继承 `AgnoAgentRuntime`），在子类里以
  「意图识别 / 局部策略 / 主判断 / 失败边界 / 清洗约束兜底」五段方法 **直接产出**
  `MainXiezuoPan / AgnoCollaborationPlan` 的核心字段。
- 第 9 轮新增：**`MainDecision` 也由 runtime 自产** —— `panduan_main_decision(...)`
  根据自家 `shibie_yitu` 的意图直接组 `MainDecision`（含 `answer_channel / need_rag /
  need_external_info`），并把 `router_source` 标为 `"main_agent_runtime"`，
  以此向下游证明"协作主路由由 main 自己的 runtime 实体直接产出"。
- Python 规则只允许做：
    * 输入清洗（`agno_web_service.user_requests_web_search` 这种"显式信号"算子）
    * `dispatch_task` 仅用于发 task_id（ID 算子，不是判断）
    * 数值约束（fengxian_yinzi 截断到 [0,1]）
    * 兜底（intent 不明时回退到 zhijie_yitu 直答）
  绝不允许"先把 xiezuo_pan / decision 核心结论算完再包装"。
- 单一主入口：`MainAgent.pan(message, ...) -> AgnoCollaborationPlan`。

台账治理第2b轮：判断六段见 `main_judgment_mixin.py`，主链见 `main_invoke_flow.py`，
V10 fallback 规则见 `main_fallback_rules.py`。
"""

from __future__ import annotations

from agents._runtime import AgentPromptPack, AgentRunFrame, AgnoAgentRuntime
from agents.shared.history_context import SessionHistorySnapshot
from agents.ports import MainAgentPort
from application.chat.budget_clock import BudgetClock
from application.chat.chat_contracts import MainAgentResult
from debug_trace import trace
from entry.task_dispatcher import dispatch_task
from llm.router import classify_intent_with_llm  # noqa: F401 — 测试 monkeypatch 锚点
from schemas import MainDecision

from .main_fallback_rules import (
    _VALID_INTENTS,  # noqa: F401 — 测试 / 外部兼容导出
    _v10_fallback_intent_from_high_confidence_rules,  # noqa: F401
)
from .main_invoke_flow import run_main_invoke_executor
from .main_judgment_mixin import MainJudgmentPhaseMixin
from .prompt import JIESHE, PROMPT_MOBAN, SHUCHU_GESHI, ZHIDAO
from .schema import AgnoCollaborationPlan, MainXiezuoPan


MAIN_PROMPT_PACK: AgentPromptPack = AgentPromptPack(
    jieshe=JIESHE,
    zhidao=ZHIDAO,
    prompt_moban=PROMPT_MOBAN,
    shuchu_geshi=SHUCHU_GESHI,
)


class MainAgentRuntime(MainJudgmentPhaseMixin, AgnoAgentRuntime[AgnoCollaborationPlan]):
    """
    main 自己的 agent runtime 实体。

    强 agent 六段能力面（每一段都可被外部单独调用、单独断言）：
    1) `shibie_yitu(...)` —— 意图识别（zhijie_yitu / zhishu_yitu /
       waibu_yitu / hunhe_yitu）
    2) `pan_jubu_celue(...)`         —— 局部策略（web_supplement_mode + answer_composition）
    3) `pan_zhuyao_panjue(...)`      —— **主判断核心字段**（直接产出 MainXiezuoPan）
    4) `panduan_main_decision(...)`  —— **协作主路由**（直接产出 MainDecision，含
       answer_channel / need_rag / need_external_info；**不**调 `decide_for_agno_chat` 规则函数）
    5) `pan_shibai_bianjie(...)`     —— 失败边界 / 保守收口（force_skip_evidence）
    6) `qingxi_yueshu_doudi(...)`    —— 清洗 / 约束 / 兜底（数值截断 / 字段兜底）
    """

    def __init__(
        self,
        *,
        mingzi: str = "main_agent",
        executor=None,
    ) -> None:
        super().__init__(
            mingzi=mingzi,
            prompt_pack=MAIN_PROMPT_PACK,
            executor=executor,
        )
        self._last_router_signal: str = ""
        self._last_explicit_kind: str = ""
        self._last_video_url: str = ""
        self._last_llm_intent: str = ""
        self._last_llm_error: str = ""
        self._last_fallback_reason: str = ""

    def invoke_executor(self, frame: AgentRunFrame) -> AgnoCollaborationPlan:
        if self._executor is not None:
            return self._executor(frame)
        return run_main_invoke_executor(self, frame)


_DEFAULT_MAIN_RUNTIME: MainAgentRuntime | None = None


def _get_default_main_runtime() -> MainAgentRuntime:
    global _DEFAULT_MAIN_RUNTIME
    if _DEFAULT_MAIN_RUNTIME is None:
        _DEFAULT_MAIN_RUNTIME = MainAgentRuntime()
    return _DEFAULT_MAIN_RUNTIME


def _main_runtime_executor(frame: AgentRunFrame) -> AgnoCollaborationPlan:
    rt = _get_default_main_runtime()
    saved = rt._executor
    rt._executor = None
    try:
        return rt.invoke_executor(frame)
    finally:
        rt._executor = saved


def build_main_xiezuo_pan(
    d: MainDecision,
    *,
    explicit_web: bool,
    http_use_knowledge: bool,
    web_supplement_mode: str,
    answer_composition: str,
) -> MainXiezuoPan:
    """
    [兼容兜底] 旧文档/旧外部代码可能仍引用此函数。

    内部转交给 `MainAgentRuntime` 的主判断方法（避免 runtime 与该函数判出不同核心字段）。

    第 9 轮起 `shibie_yitu` 不再依赖 `decision_hint`，所以这里按 (`d.answer_channel`,
    `http_use_knowledge`, `explicit_web`) 反推一手意图给 runtime；这是**兼容兜底**专用，
    runtime 主路径不走这条函数。
    """
    ch = (d.answer_channel or "").strip()
    eff_use_kb = http_use_knowledge or ch in ("kb", "mixed")
    eff_explicit_web = explicit_web or ch in ("external", "mixed")
    rt = _get_default_main_runtime()
    intent = rt.shibie_yitu(
        message="",
        http_use_knowledge=eff_use_kb,
        has_explicit_web=eff_explicit_web,
    )
    return rt.pan_zhuyao_panjue(
        intent=intent,
        http_use_knowledge=http_use_knowledge,
        has_explicit_web=explicit_web,
        comp=answer_composition,
        web_mode=web_supplement_mode,
    )


def build_agno_collaboration_plan(
    message: str,
    *,
    session_id: str | None,
    http_use_knowledge: bool,
    context_snippet: str = "",
) -> AgnoCollaborationPlan:
    """兼容兜底：旧外部代码引用 → 走 `MainAgentRuntime` 默认实例的执行链。"""
    rt = _get_default_main_runtime()
    outcome = rt.run(
        message=message,
        session_id=session_id,
        http_use_knowledge=http_use_knowledge,
        context_snippet=context_snippet,
    )
    return outcome.result


class MainAgent(MainAgentPort):
    """协作总判断 Agent（独立实体，自有 `MainAgentRuntime`）。

    六条主权边界（写死为约束）：
    1) 先判断本轮问题该怎么被处理（任务性质、协作方向）
    2) 判断是否需要事实型证据
    3) 判断是否允许走样例知识 / 是否允许网页补充
    4) 给出风险等级（保守 vs 直接）
    5) 不替 middle 裁决材料是否充足
    6) 不替 answer 决定最终对外怎么说

    单一主入口：`pan(message, ...) -> AgnoCollaborationPlan`
    主判断核心字段由 `self.runtime`（`MainAgentRuntime`）的五段方法直接产出。
    """

    JIESHE: str = JIESHE
    ZHIDAO: str = ZHIDAO
    PROMPT_MOBAN: str = PROMPT_MOBAN
    SHUCHU_GESHI: str = SHUCHU_GESHI
    PROMPT_PACK: AgentPromptPack = MAIN_PROMPT_PACK

    def __init__(
        self,
        *,
        mingzi: str = "main_agent",
        executor=None,
    ) -> None:
        self.mingzi = mingzi
        self.runtime: MainAgentRuntime = MainAgentRuntime(mingzi=mingzi, executor=executor)

    def pan(
        self,
        message: str,
        *,
        session_id: str | None = None,
        http_use_knowledge: bool = False,
        context_snippet: str = "",
        history: SessionHistorySnapshot | None = None,
        intent_classifier=None,
        v13_intent_classifier=None,
        v13_file_content: str | bytes | None = None,
        v13_title: str | None = None,
        v13_text_content: str | None = None,
        clock: BudgetClock,
    ) -> MainAgentResult:
        """单一主入口：经自有 `MainAgentRuntime` 执行链产出协作主判断对象。"""
        outcome = self.runtime.run(
            message=message,
            session_id=session_id,
            http_use_knowledge=http_use_knowledge,
            context_snippet=context_snippet,
            history=history,
            intent_classifier=intent_classifier,
            v13_intent_classifier=v13_intent_classifier,
            v13_file_content=v13_file_content,
            v13_title=v13_title,
            v13_text_content=v13_text_content,
            budget_clock=clock,
        )
        plan = outcome.result
        trace(
            f"MainAgent.pan frame={outcome.frame.frame_id} "
            f"task_id={plan.decision.task_id} "
            f"renwu={plan.xiezuo_pan.renwu_lei} "
            f"allow_kb={plan.xiezuo_pan.allow_kb} "
            f"allow_web={plan.xiezuo_pan.allow_web} "
            f"force_skip={plan.force_skip_evidence}"
        )
        return MainAgentResult(plan=plan)

    plan = pan
