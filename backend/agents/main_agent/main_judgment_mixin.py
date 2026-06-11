"""台账治理第2b轮 — Main 判断阶段 mixin（六段方法，不含 invoke_executor 主链）。

逻辑原样从 `runtime.py` 迁出，便于 `runtime.py` 瘦身与验收台账对齐。
"""

from __future__ import annotations

from dataclasses import replace

import llm.router as _llm_router_mod
from agents.shared.history_context import SessionHistorySnapshot
from llm.router import LlmIntentResult
from schemas import MainDecision
from video.url_fetch import extract_video_url

from .main_fallback_rules import _VALID_INTENTS, _v10_fallback_intent_from_high_confidence_rules
from .schema import AgnoCollaborationPlan, MainXiezuoPan


class MainJudgmentPhaseMixin:
    """Main 六段判断（意图 / 局部策略 / 主判断 / decision / 失败边界 / 清洗兜底）。

    与 ``AgnoAgentRuntime`` 组合：
    ``MainAgentRuntime(MainJudgmentPhaseMixin, AgnoAgentRuntime[...])``。
    """

    # ---------- 1) 意图识别（V10 R1：三段式主判断结构）----------
    def shibie_yitu(
        self,
        *,
        message: str,
        http_use_knowledge: bool,
        has_explicit_web: bool,
        decision_hint: MainDecision | None = None,  # noqa: ARG002 — 第 9 轮起不再使用，仅保留签名兼容
        history: SessionHistorySnapshot | None = None,
        intent_classifier=None,
    ) -> str:
        """
        识别本轮 main 的协作意图，由 runtime 实体 **直接** 产出。

        V10 R1 起结构调整为「三段式主判断」：

        ┌─ 第 1 道：显式强信号优先（命中即 return，不调 LLM）─────────────────┐
        │  - http_use_knowledge=True / has_explicit_web=True                  │
        │  - V8 R1/R2 结构化锚点：history.followup_video_anchor(message)      │
        └──────────────────────────────────────────────────────────────────────┘
        ┌─ 第 2 道：LLM 语义主判断（无显式强信号时）──────────────────────────┐
        │  - 复用 llm.router.classify_intent_with_llm                         │
        │  - 在 MainAgentRuntime 自家 runtime 内调用，不外包给 service        │
        │  - 输出无效 / LLM 不可用 → 自动落到第 3 道                          │
        └──────────────────────────────────────────────────────────────────────┘
        ┌─ 第 3 道：极少量高置信规则兜底（仅 LLM 失败 / 不可用时）─────────────┐
        │  - _asks_knowledge_inventory / _wants_realtime_web_task /           │
        │    _has_sample_file_path —— 三条"硬解剖学要件"规则，                │
        │    都不会把日常问题误判进 KB/web；其余情况保守落 zhijie_yitu。      │
        └──────────────────────────────────────────────────────────────────────┘

        说明：
        - 本方法仍是 MainAgent **自家** runtime 的主判断；
          LLM 只是 runtime 内部使用的"语义判断算子"，不是 service / 规则层
          代算结论再回流——`router_source` 仍写 "main_agent_runtime"，
          V6 R9 边界（spy 拦 legacy.decide）不被破坏。
        - V8 R1/R2 follow-up 锚点仍走第 1 道，**不会**被 LLM 抢走。
        - LLM 来源 / fallback 触发原因等可观测信息写进 runtime 实例属性，
          由 `invoke_executor` 立刻读出并追加到 `routing_explain`，
          不增加任何对外 schema 字段。
        """
        self._last_router_signal = ""
        self._last_explicit_kind = ""
        self._last_video_url = ""
        self._last_llm_intent = ""
        self._last_llm_error = ""
        self._last_fallback_reason = ""

        if http_use_knowledge and has_explicit_web:
            self._last_router_signal = "explicit"
            self._last_explicit_kind = "http_use_kb_and_web"
            return "hunhe_yitu"
        if http_use_knowledge:
            self._last_router_signal = "explicit"
            self._last_explicit_kind = "http_use_kb"
            return "zhishu_yitu"
        if has_explicit_web:
            self._last_router_signal = "explicit"
            self._last_explicit_kind = "explicit_web"
            return "waibu_yitu"
        if history is not None and history.followup_video_anchor(message) is not None:
            self._last_router_signal = "explicit"
            self._last_explicit_kind = "followup_video"
            return "zhishu_yitu"
        video_url = extract_video_url(message)
        if video_url:
            self._last_router_signal = "explicit"
            self._last_explicit_kind = "video_url"
            self._last_video_url = video_url
            return "zhishu_yitu"

        classify = intent_classifier or _llm_router_mod.classify_intent_with_llm
        try:
            llm_out: LlmIntentResult = classify(message)
        except Exception as e:  # noqa: BLE001 — runtime 主路径必须吃住任何异常
            llm_out = LlmIntentResult.unavailable(f"classifier_raised:{type(e).__name__}")

        if llm_out.available and llm_out.intent in _VALID_INTENTS:
            self._last_router_signal = "llm"
            self._last_llm_intent = llm_out.intent
            return llm_out.intent

        if llm_out.error:
            self._last_llm_error = llm_out.error
        elif llm_out.available and llm_out.intent not in _VALID_INTENTS:
            self._last_llm_intent = llm_out.intent or "(empty)"
            self._last_llm_error = "invalid_intent"
        else:
            self._last_llm_error = "unavailable"

        intent, hit = _v10_fallback_intent_from_high_confidence_rules(message)
        if hit == "default_conservative":
            self._last_router_signal = "fallback_default"
        else:
            self._last_router_signal = "fallback_rule"
        self._last_fallback_reason = hit
        return intent

    def pan_jubu_celue(
        self,
        *,
        intent: str,
        http_use_knowledge: bool,
        has_explicit_web: bool,
    ) -> tuple[str, str]:
        if intent == "zhijie_yitu":  # noqa: SIM108
            web_mode = "explicit_only"
        else:
            web_mode = "on_kb_miss_or_hint"

        if intent == "waibu_yitu":
            comp = "external_caveat"
        elif intent in ("zhishu_yitu", "hunhe_yitu"):
            comp = "kb_led"
        else:
            comp = "direct_brief"
        return web_mode, comp

    def pan_zhuyao_panjue(
        self,
        *,
        intent: str,
        http_use_knowledge: bool,
        has_explicit_web: bool,
        comp: str,
        web_mode: str = "explicit_only",
    ) -> MainXiezuoPan:
        renwu_map = {
            "zhijie_yitu": "zhijie",
            "zhishu_yitu": "zhishu",
            "waibu_yitu": "waibu",
            "hunhe_yitu": "hunhe",
        }
        renwu_lei = renwu_map.get(intent, "zhijie")
        allow_kb = bool(intent in ("zhishu_yitu", "hunhe_yitu") or http_use_knowledge)
        allow_web = bool(
            intent in ("waibu_yitu", "hunhe_yitu")
            or has_explicit_web
            or web_mode == "on_kb_miss_or_hint"
        )
        zhengju_need = bool(allow_kb or allow_web or intent != "zhijie_yitu")

        if intent == "waibu_yitu":
            fengxian = 0.88
        elif intent == "hunhe_yitu":
            fengxian = 0.7
        elif intent == "zhishu_yitu":
            fengxian = 0.62
        else:
            fengxian = 0.42

        celue_map = {
            "direct_brief": "duan_da",
            "kb_led": "kb_zhu",
            "external_caveat": "waibu_zhu",
        }
        celue_tag = celue_map.get(comp, "hun_he")

        return MainXiezuoPan(
            renwu_lei=renwu_lei,
            zhengju_need=zhengju_need,
            allow_kb=allow_kb,
            allow_web=allow_web,
            fengxian_yinzi=fengxian,
            celue_tag=celue_tag,
        )

    def panduan_main_decision(
        self,
        *,
        task_id: str,
        intent: str,
        http_use_knowledge: bool,
        has_explicit_web: bool,
    ) -> MainDecision:
        if intent == "zhishu_yitu":
            channel, need_rag, need_external = "kb", True, False
            brief_main = "kb 通道：走样例知识"
        elif intent == "waibu_yitu":
            channel, need_rag, need_external = "external", False, True
            brief_main = "external 通道：走外链 / 网页"
        elif intent == "hunhe_yitu":
            channel, need_rag, need_external = "kb", True, True
            brief_main = "kb + 网页混合"
        else:
            channel, need_rag, need_external = "direct", False, False
            brief_main = "直答：寒暄 / 通识，无需证据"

        explain_parts: list[str] = [
            f"main_agent_runtime 自判：intent={intent}",
        ]
        if http_use_knowledge:
            explain_parts.append("HTTP use_knowledge=true，开样例知识")
        if has_explicit_web:
            explain_parts.append("用户显式上网查")
        explain = "；".join(explain_parts)

        return MainDecision(
            task_id=task_id,
            need_rag=need_rag,
            need_context=False,
            need_external_info=need_external,
            need_tool_local=False,
            middle_agent_instruction="",
            task_status="routed",
            primary_goal="",
            is_compound=False,
            middle_collect_priority="balanced",
            answer_style="general",
            answer_style_hint="",
            router_source="main_agent_runtime",
            llm_error="",
            routing_brief=brief_main,
            routing_explain=explain,
            answer_channel=channel,
        )

    def pan_shibai_bianjie(
        self,
        *,
        intent: str,
        xiezuo_pan: MainXiezuoPan,
        http_use_knowledge: bool,
        has_explicit_web: bool,
    ) -> bool:
        if http_use_knowledge or has_explicit_web:
            return False
        if intent == "zhijie_yitu" and not xiezuo_pan.zhengju_need:  # noqa: SIM103
            return True
        return False

    def qingxi_yueshu_doudi(self, plan: AgnoCollaborationPlan) -> AgnoCollaborationPlan:
        xp = plan.xiezuo_pan
        bounded_fx = max(0.0, min(1.0, float(xp.fengxian_yinzi)))
        if abs(bounded_fx - float(xp.fengxian_yinzi)) > 1e-9:
            new_xp = replace(xp, fengxian_yinzi=bounded_fx)
            return replace(plan, xiezuo_pan=new_xp)
        return plan


__all__ = ["MainJudgmentPhaseMixin"]
