"""
answer_agent runtime：AnswerAgent 实体类 + 自有 `AnswerAgentRuntime` agent 实体。

- answer 拥有自己的 `AnswerAgentRuntime`（继承 `AgnoAgentRuntime`），
  以「意图识别 / 局部策略 / 主判断 / 失败边界 / 清洗约束兜底」五段方法
  **直接产出** `HuidaPan` 的核心字段（da_fengshi / jiegou_mode / baoshou_level /
  lane / primary_path）。
- `_AgnoLlmZhixingQi` 是 answer **内部** 执行器，仅在 `huida(...)` 阶段把 runtime 产出的
  `HuidaPan` + 各层 hint 合成最终文本，**不**承担主判断；唯一 Final Answer 主体身份。
- 上游 `plan.decision` 由 main runtime 自产（`router_source="main_agent_runtime"`），
  `plan.xiezuo_pan / bundle.cailiao_pan` 也由各自 runtime 直产；answer runtime 在此基础上
  自己做"对外说什么"的主判断，链路上没有任何"规则函数代算 → runtime 包"的回路。
- 单一主入口（只有这两口）：
    * `pan(plan, bundle) -> HuidaPan`
    * `huida(message, *, context_block, plan, bundle) -> (text, HuidaPan)`

拆分落点：判断段见 `answer_judgment_mixin.py`，
``hint`` / ``extra`` / 辅助见 `answer_bundle_extra.py`。
"""

from __future__ import annotations

from typing import Any

from agents._runtime import AgentPromptPack, AgentRunFrame, AgnoAgentRuntime
from agents.main_agent import AgnoCollaborationPlan
from agents.middle_agent import AgnoMaterialBundle
from agents.ports import AnswerAgentPort
from application.chat.budget_clock import BudgetClock
from application.chat.chat_contracts import AnswerAgentResult, assert_agent_extra_safe
from debug_trace import trace

from .answer_bundle_extra import (
    _suggestion_for_video_url_error,  # noqa: F401 — 单测从此模块导入
    detect_v11_video_url_failure,
    huida_to_executor_hint,
    xiezuo_extra_for_service,
)
from .answer_judgment_mixin import AnswerJudgmentPhaseMixin
from .llm_exec import _AgnoLlmZhixingQi
from .prompt import JIESHE, PROMPT_MOBAN, SHUCHU_GESHI, ZHIDAO
from .schema import HuidaPan

_detect_v11_video_url_failure = detect_v11_video_url_failure

ANSWER_PROMPT_PACK: AgentPromptPack = AgentPromptPack(
    jieshe=JIESHE,
    zhidao=ZHIDAO,
    prompt_moban=PROMPT_MOBAN,
    shuchu_geshi=SHUCHU_GESHI,
)


class AnswerAgentRuntime(AnswerJudgmentPhaseMixin, AgnoAgentRuntime[HuidaPan]):
    """
    answer 自己的 agent runtime 实体。

    五段强 agent 能力面：
    1) `shibie_yitu(...)`            —— 意图识别（zhi_da_yitu / fenkai_yitu / baoshou_yitu）
    2) `pan_jubu_celue(...)`         —— 局部策略（jiegou_mode：short / qa / sections）
    3) `pan_zhuyao_panjue(...)`      —— **主判断核心字段**（直接产出 HuidaPan）
    4) `pan_shibai_bianjie(...)`     —— 失败边界（baoshou_level 抬升）
    5) `qingxi_yueshu_doudi(...)`    —— 清洗 / 数值兜底
    """

    def __init__(
        self,
        *,
        mingzi: str = "answer_agent",
        executor=None,
    ) -> None:
        super().__init__(
            mingzi=mingzi,
            prompt_pack=ANSWER_PROMPT_PACK,
            executor=executor,
        )

    def invoke_executor(self, frame: AgentRunFrame) -> HuidaPan:
        if self._executor is not None:
            return self._executor(frame)

        inputs: dict[str, Any] = dict(frame.inputs)
        plan: AgnoCollaborationPlan = inputs["plan"]
        bundle: AgnoMaterialBundle = inputs["bundle"]

        intent = self.shibie_yitu(plan=plan, bundle=bundle)
        hp = self.pan_zhuyao_panjue(intent=intent, plan=plan, bundle=bundle)
        hp = self.pan_shibai_bianjie(hp=hp, plan=plan, bundle=bundle)
        hp = self.qingxi_yueshu_doudi(hp)

        trace(
            f"AnswerAgentRuntime exec frame={frame.frame_id} intent={intent} "
            f"dafengshi={hp.da_fengshi} jiegou={hp.jiegou_mode} "
            f"lane={hp.lane} role_sig={frame.role_signature}"
        )
        return hp


_DEFAULT_ANSWER_RUNTIME: AnswerAgentRuntime | None = None


def _get_default_answer_runtime() -> AnswerAgentRuntime:
    global _DEFAULT_ANSWER_RUNTIME
    if _DEFAULT_ANSWER_RUNTIME is None:
        _DEFAULT_ANSWER_RUNTIME = AnswerAgentRuntime()
    return _DEFAULT_ANSWER_RUNTIME


def _answer_runtime_executor(frame: AgentRunFrame) -> HuidaPan:
    rt = _get_default_answer_runtime()
    saved = rt._executor
    rt._executor = None
    try:
        return rt.invoke_executor(frame)
    finally:
        rt._executor = saved


def agno_lane_decision(
    plan: AgnoCollaborationPlan,
    bundle: AgnoMaterialBundle,
) -> tuple[str, str]:
    return _get_default_answer_runtime()._sign_lane(plan, bundle)


def pan_huida_agno(
    plan: AgnoCollaborationPlan,
    bundle: AgnoMaterialBundle,
) -> HuidaPan:
    rt = _get_default_answer_runtime()
    outcome = rt.run(plan=plan, bundle=bundle)
    return outcome.result


class AnswerAgent(AnswerAgentPort):
    """唯一 Final Answer Agent（独立实体，自有 `AnswerAgentRuntime`）。

    主入口（仅这两口）：
    - `pan(plan, bundle) -> HuidaPan`：经 `AnswerAgentRuntime` 五段执行链产出
    - `huida(message, *, context_block, plan, bundle) -> tuple[str, HuidaPan]`：
        先 pan，再统一调用 **内部执行器**（`_AgnoLlmZhixingQi`）生成最终文本

    `xiezuo_extra(plan, bundle) -> dict`：暴露 v6_* 维度给 service 透传（service 不再代写）。
    """

    JIESHE: str = JIESHE
    ZHIDAO: str = ZHIDAO
    PROMPT_MOBAN: str = PROMPT_MOBAN
    SHUCHU_GESHI: str = SHUCHU_GESHI
    PROMPT_PACK: AgentPromptPack = ANSWER_PROMPT_PACK

    def __init__(
        self,
        *,
        mingzi: str = "answer_agent",
        zhixing: object | None = None,
        executor=None,
    ) -> None:
        self.mingzi = mingzi
        self.zhixing = zhixing or _AgnoLlmZhixingQi()
        self.runtime: AnswerAgentRuntime = AnswerAgentRuntime(
            mingzi=mingzi, executor=executor,
        )

    def pan(
        self,
        plan: AgnoCollaborationPlan,
        bundle: AgnoMaterialBundle,
    ) -> HuidaPan:
        outcome = self.runtime.run(plan=plan, bundle=bundle)
        hp = outcome.result
        trace(
            f"AnswerAgent.pan frame={outcome.frame.frame_id} "
            f"task_id={plan.decision.task_id} "
            f"dafengshi={hp.da_fengshi} jiegou={hp.jiegou_mode} "
            f"baoshou={hp.baoshou_level} lane={hp.lane} "
            f"primary_path={hp.primary_path}"
        )
        return hp

    judge = pan

    def review_multisource(
        self,
        user_message: str,
        *,
        plan: AgnoCollaborationPlan,
        bundle: AgnoMaterialBundle,
        current_round: int = 0,
    ) -> dict[str, Any]:
        feedback_request = self.runtime.build_feedback_request(
            plan=plan,
            bundle=bundle,
            current_round=current_round,
        )
        critic = dict(getattr(bundle, "critic_check", {}) or {})
        comparison = dict(getattr(bundle, "comparison_matrix", {}) or {})
        unsupported = {
            str(item.get("claim", ""))
            for item in list(critic.get("unsupported_claims") or [])
        }
        common_points = [
            point
            for point in list(comparison.get("common_points") or [])
            if point not in unsupported
        ][:3]
        diff_points = [
            item.get("point", "")
            for item in list(comparison.get("different_points") or [])[:3]
            if item.get("point")
        ]
        evidence_bits = []
        for link in list(comparison.get("evidence_links") or [])[:4]:
            excerpt = str(link.get("text_excerpt", "") or "").strip()
            if excerpt:
                evidence_bits.append(excerpt[:160])
        weak_note = []
        if critic.get("unsupported_claims"):
            weak_note.append("已排除缺少证据支撑的结论。")
        if critic.get("weak_evidence_claims"):
            weak_note.append("保留的比较结论里仍有弱证据部分。")
        limitations = list(
            dict.fromkeys(
                list(getattr(bundle, "answer_limitations", []) or [])
                + list(critic.get("limitations") or []),
            ),
        )
        feedback_result = dict(getattr(bundle, "feedback_gate_result", {}) or {})

        final_lines = []
        if feedback_request and current_round == 0 and not feedback_result:
            final_lines.append("当前材料还不够稳妥，我需要先补抓允许范围内的来源证据。")
        else:
            final_lines.append("基于当前多来源材料，我先给出受证据约束的比较结论。")
            if common_points:
                final_lines.append("共同点：" + "；".join(common_points))
            if diff_points:
                final_lines.append("差异点：" + "；".join(diff_points))
            if weak_note:
                final_lines.append("证据说明：" + " ".join(weak_note))
            if feedback_result:
                if feedback_result.get("allowed"):
                    final_lines.append("本轮已使用受控补救材料完成补强。")
                else:
                    final_lines.append("补救请求未获允许，因此结论保持保守。")
            if limitations:
                final_lines.append("局限：" + "；".join(limitations[:3]))

        return {
            "feedback_request": feedback_request,
            "final_answer": "\n".join(final_lines).strip(),
            "source_brief_summary": [
                {
                    "source_brief_id": brief.get("source_brief_id", ""),
                    "title": brief.get("title", ""),
                    "angle": brief.get("angle", ""),
                    "key_points": list(brief.get("key_points") or [])[:3],
                }
                for brief in list(getattr(bundle, "source_briefs", []) or [])
            ],
            "comparison_summary": {
                "summary": comparison.get("summary", ""),
                "common_points": common_points,
                "different_points": diff_points,
                "conflicts": list(comparison.get("conflicts") or []),
            },
            "evidence_summary": evidence_bits,
            "unsupported_or_weak_evidence_note": " ".join(weak_note).strip(),
            "used_context": list(getattr(bundle, "used_context", []) or []),
            "used_rounds": list(getattr(bundle, "used_rounds", []) or [current_round]),
            "final_answer_based_on_round": (
                getattr(bundle, "final_answer_based_on_round", "round_0") or "round_0"
            ),
            "limitations": limitations,
            "feedback_result": feedback_result or {"allowed": None, "reason": "not_called"},
        }

    def huida(
        self,
        user_message: str,
        *,
        context_block: str | None,
        plan: AgnoCollaborationPlan,
        bundle: AgnoMaterialBundle,
        clock: BudgetClock,
    ) -> AnswerAgentResult:
        hp = self.pan(plan, bundle)
        v11_failure = detect_v11_video_url_failure(bundle, plan)
        if v11_failure is not None:
            return AnswerAgentResult(
                answer_text=v11_failure,
                huida_pan=hp,
                agent_extra=self.collab_extra(plan, bundle),
            )

        answer_mode = getattr(plan, "answer_mode", "direct") or "direct"

        if answer_mode == "source_brief_summary":
            review = self.review_multisource(
                user_message,
                plan=plan,
                bundle=bundle,
                current_round=max(list(getattr(bundle, "used_rounds", []) or [0])),
            )
            return AnswerAgentResult(
                answer_text=str(review.get("final_answer", "")).strip(),
                huida_pan=hp,
                agent_extra=self.collab_extra(plan, bundle),
            )

        if answer_mode == "direct":
            hint = huida_to_executor_hint(
                hp,
                plan.xiezuo_pan,
                bundle.cailiao_pan,
                plan,
                bundle,
            )
            text = self.zhixing.shengcheng(  # type: ignore[attr-defined]
                user_message,
                context_block=context_block,
                knowledge_block=None,  # direct 模式
                web_search_block=None,
                executor_hint=hint,
            )
            return AnswerAgentResult(
                answer_text=text,
                huida_pan=hp,
                agent_extra=self.collab_extra(plan, bundle),
            )

        if answer_mode == "commit_result":
            if bundle.commit_results:
                _cr_list = bundle.commit_results
                _ok_list = [r for r in _cr_list if r.get("status") == "committed"]
                _fail_list = [r for r in _cr_list if r.get("status") == "failed"]
                if _ok_list:
                    _titles = "、".join(
                        r.get("title") or r.get("source_id", "未知") for r in _ok_list
                    )
                    _chunks = sum(r.get("chunks", 0) for r in _ok_list)
                    return AnswerAgentResult(
                        answer_text=(
                            f"已将资料「{_titles}」保存到知识库（共 {_chunks} 段）。\n\n"
                            "以后可以直接问我关于这些资料的问题，我会从知识库中检索作答。"
                        ),
                        huida_pan=hp,
                        agent_extra=self.collab_extra(plan, bundle),
                    )
                if _fail_list:
                    _err = _fail_list[0].get("error_code") or "未知错误"
                    return AnswerAgentResult(
                        answer_text=f"保存资料时失败（原因：{_err}），请稍后重试。",
                        huida_pan=hp,
                        agent_extra=self.collab_extra(plan, bundle),
                    )
            return AnswerAgentResult(
                answer_text=(
                    "本轮未产生可确认的入库结果（commit_results 为空）。"
                    "请确认已先准备资料并选择保存。"
                ),
                huida_pan=hp,
                agent_extra=self.collab_extra(plan, bundle),
            )

        _ms = getattr(bundle, "material_sufficiency", "") or ""
        if _ms in ("no_match", "insufficient") and answer_mode == "conservative":
            return AnswerAgentResult(
                answer_text=(
                    "抱歉，当前知识库中未找到相关内容，无法为您提供准确答案。"
                    "您可以先将相关资料保存到知识库，再重新提问。"
                ),
                huida_pan=hp,
                agent_extra=self.collab_extra(plan, bundle),
            )

        # legacy-only 说明：
        # `bundle.knowledge_block` 不再是默认主证据主路径；当前只允许：
        # 1) retrieved_chunks / temporary_materials 等 bundle-bound 材料
        # 2) conservative 时的失败摘要
        # 直接把 `bundle.knowledge_block` 当作默认答案依据，属于 legacy fallback 口径。
        kb_for_answer: str | None = None
        if answer_mode == "conservative":
            _fail_list = getattr(bundle, "failures", None) or []
            kb_for_answer = (
                "\n".join(
                    f"[{fb.get('tool', '?')}] {fb.get('reason', '')}"
                    for fb in _fail_list
                    if isinstance(fb, dict)
                )
                or None
            )
        elif answer_mode == "knowledge_grounded":
            if bundle.retrieved_chunks:
                from services.capabilities.knowledge.grounding_service import (
                    chunks_to_compact_prompt_block,
                )

                kb_for_answer = chunks_to_compact_prompt_block(
                    list(bundle.retrieved_chunks),
                    max_chunks=2,
                    max_chars=900,
                )
            elif (bundle.web_block or "").strip():
                kb_for_answer = None
            else:
                return AnswerAgentResult(
                    answer_text=(
                        "当前未从知识库检索到可用片段，也未获得可用的外部网页证据，"
                        "无法基于材料作答。请补充资料或调整提问。"
                    ),
                    huida_pan=hp,
                    agent_extra=self.collab_extra(plan, bundle),
                )
        elif answer_mode == "temporary_material":
            if bundle.temporary_materials:
                kb_for_answer = "\n\n---\n\n".join(bundle.temporary_materials)
            else:
                return AnswerAgentResult(
                    answer_text="本轮没有可用的待保存临时材料（temporary_materials 为空）。",
                    huida_pan=hp,
                    agent_extra=self.collab_extra(plan, bundle),
                )
        else:
            kb_for_answer = None

        hint = huida_to_executor_hint(
            hp,
            plan.xiezuo_pan,
            bundle.cailiao_pan,
            plan,
            bundle,
            compact=(answer_mode == "knowledge_grounded"),
        )
        text = self.zhixing.shengcheng(  # type: ignore[attr-defined]
            user_message,
            context_block=context_block,
            knowledge_block=kb_for_answer,
            web_search_block=bundle.web_block,
            executor_hint=hint,
        )
        return AnswerAgentResult(
            answer_text=text,
            huida_pan=hp,
            agent_extra=self.collab_extra(plan, bundle),
        )

    def collab_extra(
        self,
        plan: AgnoCollaborationPlan,
        bundle: AgnoMaterialBundle,
    ) -> dict:
        return assert_agent_extra_safe(xiezuo_extra_for_service(plan, bundle))

    def xiezuo_extra(
        self,
        plan: AgnoCollaborationPlan,
        bundle: AgnoMaterialBundle,
    ) -> dict:
        return self.collab_extra(plan, bundle)

    respond = huida
