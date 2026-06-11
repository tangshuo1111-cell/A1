"""
PG-only since 2026-05-09（检索走 PG tsvector / hybrid_retrieve）。

middle_agent runtime：MiddleAgent 实体类 + 自有 `MiddleAgentRuntime` agent 实体。

V6 第 8 轮（真 agent / 强 agent）→ 第 9 轮（终验补强）：
- middle 拥有自己的 `MiddleAgentRuntime`（继承 `AgnoAgentRuntime`），
  在子类里以「意图识别 / 局部策略(kb+web) / 主判断 / 失败边界 / 清洗约束兜底」五段方法
  **直接产出** `CailiaoPan / AgnoMaterialBundle` 的核心字段。
- 规则只允许做：
    * `_token_overlap` / `_agno_kb_evidence_tier` 这类相似度算子（输入清洗）
    * 调 `retrieve_service / agno_web_service` 真实拉材料（**执行器**，不是主脑）
    * 数值兜底
  绝不允许"先把 cailiao_pan / bundle 核心结论算完再包装"。
- 第 9 轮起：main 已不再让 `decide_for_agno_chat` 代算，下游 middle 看到的
  `plan.decision.router_source == "main_agent_runtime"` —— middle runtime 完全
  基于 `plan.xiezuo_pan` 这个由 main runtime 直接产出的强约束做自己的主判断。
- 单一主入口：`MiddleAgent.caipan(message, *, plan, http_use_knowledge=False) -> AgnoMaterialBundle`。

V7 第 1 轮新增：「业务型 MCP 调用决策点」由 MiddleAgentRuntime 直接产出。
- `shibie_video_yitu(...)`：从 message 抽取本地 .mp4 路径的"显式信号"算子（输入清洗）；
- `pan_jubu_celue_video(...)`：根据视频意图直接给出 MCP 调用决策
  （`call_video_to_text` / `skip_no_video_yitu` / `skip_path_unsafe`）；
- 当决策为 `call_video_to_text` 时，runtime 通过 `mcp_local.mcp_client.call_mcp_tool(
  "video_to_text", {...})` 真实拉起子进程 MCP server（首条业务型 MCP tool），
  抽出的可入库纯文本 + 最小来源标识透传进 `AgnoMaterialBundle.mcp_video_*` 字段。
- 调用决策权在 MiddleAgentRuntime 自身——**不**让 service / api / route 偷判断；
  AnswerAgent 不新增能力调用主判断权。

V7 第 2 轮新增：把第 1 轮的"可入库纯文本"真接进现有 ingest 链（不平行造系统）。
- 当 `mcp_video_ok=True` 时，runtime 自家在 MCP 调用结果就位的同一帧里调
  `rag.video_ingest.ingest_video_bundle(...)`，把文本写进 PG 知识库；
- 入库 source_id 规范成 `video:<basename>`，与既有 sample.md 等 source_id 显式分流，
  后续问答阶段命中时可立刻识别"这条命中来自 V7 视频链"；
- 入库结果（`ingested / source_id / chunks / error`）一并透传到 bundle V7 字段；
- 入库**仅在 MCP 调用真实成功**且文本非空时触发，对失败路径仍保持结构化失败。

冷启动说明（V7 第 2 轮 风险点 3 的最小处理）：
- 业务型 MCP tool 仍每次以子进程方式拉起，存在冷启动开销；本轮**不**做平台化连接池。
- 在主链中 video_to_text 仅当显式识别到 .mp4 路径意图时才触发（已由
  `pan_jubu_celue_video` 兜住）；常规 V6 主链的吞吐与冷启动开销零相关。
- 后续问答命中走 `retrieve_service`（PG 检索），
  不会重复触发 stdio 子进程；冷启动只发生在"入库那一帧"。
"""

from __future__ import annotations

import logging
from typing import Any

from agents._runtime import AgentPromptPack, AgentRunFrame, AgnoAgentRuntime
from agents.main_agent import AgnoCollaborationPlan, MainAgent
from agents.ports import MiddleAgentPort
from agents.shared.history_context import SessionHistorySnapshot
from application.chat.budget_clock import SLA_BUDGET_MS, BudgetClock
from application.chat.chat_contracts import MaterialGateFacts, MiddleAgentResult
from debug_trace import trace
from schemas import MainDecision
from video import url_fetch as _video_url_fetch

from . import invoke_tail_flow
from .gather_phase import MiddleGatherPhaseMixin
from .judgment_phase import MiddleJudgmentPhaseMixin
from .material_policy import _is_tool_allowed  # noqa: F401 — 兼容旧路径 `runtime._is_tool_allowed`
from .multisource_round import _execute_v17_tool_plan
from .prompt import JIESHE, PROMPT_MOBAN, SHUCHU_GESHI, ZHIDAO
from .schema import AgnoMaterialBundle

logger = logging.getLogger("light_maqa")
fetch_video_text = _video_url_fetch.fetch_video_text  # 兼容旧测试 monkeypatch: runtime.fetch_video_text
# 结构化 trace 真实落点已下沉到 bundle_finalize_flow：
# - v15:tool_blocked
# - v15:plan plan_id=...
# - v15:bundle execution_status=...
# 工具拦截原因同样沿用 `not_allowed_by_plan`，由 gather/bundle finalize 阶段写入。

# ---------------------------------------------------------------------------
# MiddleAgent prompt_pack（prompt 真正进入 runtime frame）
# ---------------------------------------------------------------------------
MIDDLE_PROMPT_PACK: AgentPromptPack = AgentPromptPack(
    jieshe=JIESHE,
    zhidao=ZHIDAO,
    prompt_moban=PROMPT_MOBAN,
    shuchu_geshi=SHUCHU_GESHI,
)


# ---------------------------------------------------------------------------
# MiddleAgentRuntime —— middle 自有 agent runtime 实体
# ---------------------------------------------------------------------------
class MiddleAgentRuntime(
    MiddleJudgmentPhaseMixin,
    MiddleGatherPhaseMixin,
    AgnoAgentRuntime[AgnoMaterialBundle],
):
    """
    middle 自己的 agent runtime 实体。

    五段强 agent 能力面（V6）见 `judgment_phase.MiddleJudgmentPhaseMixin`：
    意图识别 / KB·Web 局部策略 / 主判断 `CailiaoPan` / 失败边界 / 清洗兜底；
    视频 URL·本地 MCP 等委托至 `video_flow`，由 mixin 上的薄方法转发。

    gather 编排见 `gather_phase.MiddleGatherPhaseMixin`；
    invoke 尾段见 `invoke_tail_flow.build_material_bundle_after_gather`。
    """

    def __init__(
        self,
        *,
        mingzi: str = "middle_agent",
        executor=None,
    ) -> None:
        super().__init__(
            mingzi=mingzi,
            prompt_pack=MIDDLE_PROMPT_PACK,
            executor=executor,
        )

    # ---------- 主脑：override invoke_executor（gather + invoke_tail） ----------
    def invoke_executor(self, frame: AgentRunFrame) -> AgnoMaterialBundle:
        # 注入 hook 优先（仅供测试 / 未来 LLM 替换）
        if self._executor is not None:
            return self._executor(frame)

        inputs: dict[str, Any] = dict(frame.inputs)
        message = str(inputs.get("message", ""))
        plan: AgnoCollaborationPlan = inputs["plan"]
        http_use_knowledge = bool(inputs.get("http_use_knowledge", False))
        # V8 第 1 轮：当前会话前文承接对象（与 main 看到的是同一份；新会话默认 None）。
        history: SessionHistorySnapshot | None = inputs.get("history")
        decision: MainDecision = plan.decision
        msg = message.strip()
        # V15 收口：pending store / prepare_web_video / commit 需 session_id（早于网页视频块使用）
        session_id = str(inputs.get("session_id") or "")
        budget_clock = inputs.get("budget_clock")
        if budget_clock is None:
            raise ValueError("MiddleAgentRuntime requires a turn-level budget_clock")
        # 网页视频 pending：由 video_flow.run_early_web_video_flow 写入 _web_video_pending_early 等
        # V8 锚点追问的真实检索实现已下沉到 retrieval_flow，
        # 其中会走 retrieve_knowledge(strategy="source_all")，而不是在本方法里直连旧 helper。
        # V15 legacy 收边：仅有孤立的 legacy knowledge_block / orphan legacy knowledge_block
        # 不得单独维持 sufficient，最终由 gather + finalize 阶段统一降级判断。

        # V15 R1 修正：工具拦截失败记录（在 invoke_executor 生命周期内汇集）
        _v15_blocked_failures: list[dict] = []

        # === gather → trace / V13 / finalize → bundle（invoke_tail_flow）===
        g = self._middle_invoke_gather_phase(
            message=message,
            msg=msg,
            plan=plan,
            shared_prep=inputs.get("shared_prep"),
            http_use_knowledge=http_use_knowledge,
            history=history,
            decision=decision,
            session_id=session_id,
            blocked_failures=_v15_blocked_failures,
            fetch_video_text_fn=fetch_video_text,
            v13_file_content=inputs.get("v13_file_content"),
            budget_clock=budget_clock,
        )
        return invoke_tail_flow.build_material_bundle_after_gather(
            frame=frame,
            message=message,
            inputs=inputs,
            msg=msg,
            session_id=session_id,
            plan=plan,
            decision=decision,
            http_use_knowledge=http_use_knowledge,
            blocked_failures=_v15_blocked_failures,
            g=g,
        )


# ---------------------------------------------------------------------------
# 兼容别名 / 旧入口
# ---------------------------------------------------------------------------
_DEFAULT_MIDDLE_RUNTIME: MiddleAgentRuntime | None = None


def _get_default_middle_runtime() -> MiddleAgentRuntime:
    global _DEFAULT_MIDDLE_RUNTIME
    if _DEFAULT_MIDDLE_RUNTIME is None:
        _DEFAULT_MIDDLE_RUNTIME = MiddleAgentRuntime()
    return _DEFAULT_MIDDLE_RUNTIME


def _middle_runtime_executor(frame: AgentRunFrame) -> AgnoMaterialBundle:
    """兼容入口：走 `MiddleAgentRuntime` 默认实例的内置五段。"""
    rt = _get_default_middle_runtime()
    saved = rt._executor
    rt._executor = None
    try:
        return rt.invoke_executor(frame)
    finally:
        rt._executor = saved


def gather_agno_materials(
    message: str,
    decision: MainDecision,
    *,
    http_use_knowledge: bool,
    collaboration_plan: AgnoCollaborationPlan | None = None,
) -> AgnoMaterialBundle:
    """兼容兜底：旧外部代码 / 旧文档可能仍引用此函数。

    内部转交给 `MiddleAgentRuntime` 默认实例的执行链；如果未提供 collaboration_plan，
    构造一个最小 plan 包裹 decision 仅供下游兼容（runtime 仍以 plan.xiezuo_pan 为强约束）。
    """
    if collaboration_plan is None:
        # 最小兼容：用一个空 xiezuo_pan 兜底（实际 V6 路径上 service 总会传 plan）
        collaboration_plan = MainAgent().pan(
            message,
            session_id=None,
            http_use_knowledge=http_use_knowledge,
            clock=BudgetClock.start(SLA_BUDGET_MS),
        ).plan

    rt = _get_default_middle_runtime()
    outcome = rt.run(
        message=message,
        plan=collaboration_plan,
        http_use_knowledge=http_use_knowledge,
        budget_clock=BudgetClock.start(SLA_BUDGET_MS),
    )
    return outcome.result


# ---------------------------------------------------------------------------
# MiddleAgent 实体（可单独实例化 / 单独调用 / 单独测试）
# ---------------------------------------------------------------------------
def _material_gate_facts_from_bundle(bundle: AgnoMaterialBundle) -> MaterialGateFacts:
    return MaterialGateFacts(
        material_sufficiency=str(getattr(bundle, "material_sufficiency", "sufficient") or "sufficient"),
        material_still_insufficient=bool(getattr(bundle, "material_still_insufficient", False)),
        try_rag_executed=bool(getattr(bundle, "try_rag_executed", False)),
        has_web_evidence=bool((getattr(bundle, "web_block", "") or "").strip()),
        allow_web=bool(getattr(bundle, "allow_web", False)),
    )


class MiddleAgent(MiddleAgentPort):
    """材料裁判 Agent（独立实体，自有 `MiddleAgentRuntime`）。

    单一主入口：`caipan(message, *, plan, http_use_knowledge=False) -> AgnoMaterialBundle`
    主判断核心字段由 `self.runtime`（`MiddleAgentRuntime`）的五段方法直接产出。
    """

    JIESHE: str = JIESHE
    ZHIDAO: str = ZHIDAO
    PROMPT_MOBAN: str = PROMPT_MOBAN
    SHUCHU_GESHI: str = SHUCHU_GESHI
    PROMPT_PACK: AgentPromptPack = MIDDLE_PROMPT_PACK

    def __init__(
        self,
        *,
        mingzi: str = "middle_agent",
        executor=None,
    ) -> None:
        self.mingzi = mingzi
        self.runtime: MiddleAgentRuntime = MiddleAgentRuntime(mingzi=mingzi, executor=executor)

    def caipan(
        self,
        message: str,
        *,
        plan: AgnoCollaborationPlan,
        shared_prep: Any | None = None,
        http_use_knowledge: bool = False,
        history: SessionHistorySnapshot | None = None,
        session_id: str | None = None,
        v13_text_content: str | None = None,
        v13_title: str | None = None,
        v13_file_content: str | bytes | None = None,
        prior_bundle: AgnoMaterialBundle | None = None,
        allowed_fallback_steps: list[dict[str, Any]] | None = None,
        current_round: int = 0,
        feedback_gate_result: dict[str, Any] | None = None,
        clock: BudgetClock,
    ) -> MiddleAgentResult:
        """单一主入口：经自有 `MiddleAgentRuntime` 执行链产出材料主判断对象。

        V8 第 1 轮：新增 `history` 形参（默认 None，保持向后兼容）—— 当 service
        在每轮入口构造好 `SessionHistorySnapshot` 时显式传入；MiddleAgent 自身
        runtime 会在材料判断阶段决定是否要"沿用上一轮视频对象"继续补材，
        从而把"刚才那个视频"这种指代真转成对 video:<basename> 命名空间的检索。

        V13 R2 新增形参：
        - session_id: 当前会话 ID（供 pending store 按 session 存储）
        - v13_text_content: 直接文本内容（prepare_text 场景，可能不同于 message）
        - v13_title: 文本标题（可选）
        - v13_file_content: 上传文件内容（prepare_file 场景）
        """
        if getattr(plan, "job_type", "") in {"multi_source_compare", "tool_audit"} and getattr(plan, "tool_plan", None):
            bundle = _execute_v17_tool_plan(
                message,
                plan,
                prior_bundle=prior_bundle,
                allowed_fallback_steps=allowed_fallback_steps,
                current_round=current_round,
                feedback_gate_result=feedback_gate_result,
            )
            trace(
                f"MiddleAgent.caipan v17_tool_plan task_id={plan.decision.task_id} "
                f"status={bundle.execution_status} briefs={len(bundle.source_briefs)} rounds={bundle.used_rounds}"
            )
            return MiddleAgentResult(
                bundle=bundle,
                material_gate_facts=_material_gate_facts_from_bundle(bundle),
            )
        outcome = self.runtime.run(
            message=message,
            plan=plan,
            shared_prep=shared_prep,
            http_use_knowledge=http_use_knowledge,
            history=history,
            session_id=session_id or "",
            v13_text_content=v13_text_content or "",
            v13_title=v13_title or "",
            v13_file_content=v13_file_content,
            budget_clock=clock,
        )
        bundle = outcome.result
        cp = bundle.cailiao_pan
        trace(
            f"MiddleAgent.caipan frame={outcome.frame.frame_id} "
            f"task_id={plan.decision.task_id} "
            f"gou={cp.gou} bukong={cp.bukong_xinhao} "
            f"que={cp.que_shenme} xia={cp.xia_yi_bu} "
            f"laiyuan={cp.laiyuan_zhu}"
        )
        return MiddleAgentResult(
            bundle=bundle,
            material_gate_facts=_material_gate_facts_from_bundle(bundle),
        )

    arbitrate = caipan
