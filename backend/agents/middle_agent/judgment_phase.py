"""台账 G-005「judgment_phase」：Middle 五段主判断 + V8 前文承接 + V11 保存意图。

供 `MiddleJudgmentPhaseMixin` 混入 `MiddleAgentRuntime`，与 `gather_phase` 对称，
避免 `runtime.py` 承载大块主判断实现。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from agents.history_context import PrevVideoRef, SessionHistorySnapshot
from agents.main_agent import AgnoCollaborationPlan
from application.chat.chat_contracts import KbSufficiencyResult
from schemas import MainDecision
from services.capabilities.web import web_orchestration_service as agno_web_service

from . import video_flow
from .collect_flow_eval import _token_overlap
from .material_policy import _agno_kb_evidence_tier
from .schema import CailiaoPan


class MiddleJudgmentPhaseMixin:
    """供 `MiddleAgentRuntime` 多重继承；材料侧意图 / 局部策略 / 主判断 / 失败边界 / 兜底。"""

    # ---------- 1) 意图识别 ----------
    def shibie_yitu(
        self,
        *,
        message: str,
        http_use_knowledge: bool,
        plan: AgnoCollaborationPlan,
    ) -> str:
        """
        识别本轮材料获取意图（runtime 直接产出，**不**走规则函数代算）。

        意图集合：
        - skip_yitu          —— main 已强制 force_skip
        - kb_first_yitu      —— 强信号要走样例知识（http use_knowledge / main 仅 allow_kb）
        - web_explicit_yitu  —— 用户显式"上网查" / 强外部意图
        - hunhe_yitu         —— 同时既要 kb 又要 web（双显式 / 双允许）
        - web_caveat_yitu    —— main 允许 web 但用户未显式 → 由 web 网关二次裁决
        - direct_yitu        —— 直答即可
        """
        if plan.force_skip_evidence:
            return "skip_yitu"
        msg = (message or "").strip()
        explicit_web = agno_web_service.user_requests_web_search(msg)
        if http_use_knowledge and explicit_web:
            return "hunhe_yitu"
        if http_use_knowledge:
            return "kb_first_yitu"
        if explicit_web:
            return "web_explicit_yitu"
        xp = plan.xiezuo_pan
        if xp.allow_kb and xp.allow_web:
            return "hunhe_yitu"
        if xp.allow_kb:
            return "kb_first_yitu"
        if xp.allow_web:
            # main 给了 web 权限但用户未显式 → 仍交给 web 网关二次裁决
            return "web_caveat_yitu"
        return "direct_yitu"

    # ---------- 2.a) 局部策略：是否拉 RAG ----------
    def pan_jubu_celue_kb(
        self,
        *,
        intent: str,
        plan: AgnoCollaborationPlan,
        decision: MainDecision,
    ) -> bool:
        """决定 try_rag —— 主体由 runtime 意图决定，main 的 allow_kb 作为强约束。"""
        if intent == "skip_yitu":
            return False
        if intent == "web_explicit_yitu":
            return False
        # 意图允许 kb；但 main 不允许时 → 收紧
        if not plan.xiezuo_pan.allow_kb:
            return False
        if intent in ("kb_first_yitu", "hunhe_yitu"):
            return True
        # direct_yitu：仅当规则路由强烈建议 + main 仍允许 kb
        return bool(decision.need_rag and decision.answer_channel == "kb")

    # ---------- 2.b) 局部策略：是否补 WEB ----------
    def pan_jubu_celue_web(
        self,
        *,
        intent: str,
        plan: AgnoCollaborationPlan,
        message: str,
        http_use_knowledge: bool,
        knowledge_block: str | None,
    ) -> tuple[bool, str]:
        """决定 (want_web, web_judgment_reason) —— main 的 allow_web 作为强约束。"""
        msg = (message or "").strip()
        explicit_web = agno_web_service.user_requests_web_search(msg)

        if intent == "skip_yitu":
            if explicit_web:
                return True, "middle:force_skip_web_only_explicit"
            return False, "middle:force_skip_no_web"

        if intent == "web_explicit_yitu" or intent == "hunhe_yitu" and explicit_web:
            want, reason = True, "middle:route_web_explicit"
        elif intent in ("hunhe_yitu", "web_caveat_yitu", "kb_first_yitu", "direct_yitu") and (
            agno_web_service.should_run_web_search(
                msg, use_knowledge=http_use_knowledge, knowledge_block=knowledge_block,
            )
        ):
            want, reason = True, "middle:gate_agno_web_service"
        else:
            want, reason = False, "skip"

        # main 不允许 web 且非显式 → 收紧（runtime 自己尊重 main 边界）
        if want and not plan.xiezuo_pan.allow_web and intent != "web_explicit_yitu" and not explicit_web:
            return False, "middle:main_pan_disallow_web"
        return want, reason

    # ---------- 3) 主判断（直接产出 CailiaoPan 核心字段）----------
    def pan_zhuyao_panjue(
        self,
        *,
        intent: str,
        message: str,
        try_rag: bool,
        knowledge_block: str | None,
        web_block: str | None,
    ) -> CailiaoPan:
        """
        **直接** 产出 `CailiaoPan` 的核心字段：gou / bukong_xinhao / laiyuan_zhu /
        use_kb / use_web / que_shenme / xia_yi_bu / kb_qiangdu。

        关键：所有结论由 runtime 自身（intent + 已拉到的 kb/web 文本）直接得出，
        外部规则只负责把 (kb_text, web_text) 拉来 + 提供相似度算子。
        """
        msg = (message or "").strip()
        kb_body = (knowledge_block or "").strip()
        wb_body = (web_block or "").strip()
        kb_nonempty = bool(kb_body)
        kb_tier = _agno_kb_evidence_tier(msg, knowledge_block)
        kb_qiangdu = _token_overlap(msg, kb_body) if kb_body else 0.0
        use_kb_flag = bool(try_rag and kb_nonempty)
        use_web_flag = bool(wb_body)

        # === 主裁决：来源主 / 充空信号 / 是否够 ===
        if intent == "skip_yitu":
            gou = True
            bukong = "ok"
            if not wb_body:  # noqa: SIM108
                laiyuan = "wu"
            else:
                laiyuan = "hunhe" if kb_nonempty else "web"
        elif kb_tier == "weak" and not wb_body:
            gou, bukong, laiyuan = False, "ruo", "kb"
        elif kb_tier == "weak" and wb_body:
            gou, bukong, laiyuan = True, "ruo", "hunhe"
        elif kb_nonempty and wb_body:
            gou, bukong, laiyuan = True, "ok", "hunhe"
        elif kb_nonempty:
            gou, bukong, laiyuan = True, "ok", "kb"
        elif wb_body:
            gou = len(wb_body) > 80
            bukong = "ok" if gou else "ruo"
            laiyuan = "web"
        else:
            # 完全无材料：若本轮根本没打算拉 kb 且意图本就是直答类 → 视为「直答 ok」；否则「空 + 缺」
            if not try_rag and intent in ("direct_yitu", "web_caveat_yitu"):
                gou, bukong, laiyuan = True, "ok", "wu"
            else:
                gou, bukong, laiyuan = False, "que", "wu"

        # === 缺什么 / 下一步 ===
        if intent == "skip_yitu":
            que_shenme, xia_yi_bu = "none", "zhi_da"
        elif bukong == "que":
            que_shenme = "liangzhe"
            # 默认：依据已发生的拉取结果给出建议路径（兜底层会用 main 权限再校正）
            if not wb_body:
                xia_yi_bu = "bu_wang"
            elif not kb_nonempty:
                xia_yi_bu = "wen_yonghu"
            else:
                xia_yi_bu = "shou_kou"
        elif kb_tier == "weak" and not wb_body:
            que_shenme, xia_yi_bu = "web_yinzheng", "bu_wang"
        elif kb_tier == "weak" and wb_body:
            que_shenme, xia_yi_bu = "kb_yangben", "shou_kou"
        elif (not kb_nonempty) and wb_body and len(wb_body) <= 80:
            que_shenme, xia_yi_bu = "web_yinzheng", "shou_kou"
        else:
            que_shenme, xia_yi_bu = "none", "zhi_da"

        return CailiaoPan(
            gou=gou,
            kb_qiangdu=kb_qiangdu,
            bukong_xinhao=bukong,
            laiyuan_zhu=laiyuan,
            use_kb=use_kb_flag,
            use_web=use_web_flag,
            que_shenme=que_shenme,
            xia_yi_bu=xia_yi_bu,
        )

    # ---------- 4) 失败边界 ----------
    def pan_shibai_bianjie(
        self,
        *,
        intent: str,
        cailiao_pan: CailiaoPan,
        try_rag: bool,
        knowledge_block: str | None,
        web_block: str | None,
        http_use_knowledge: bool,
        kb_sufficiency: KbSufficiencyResult | None = None,
    ) -> tuple[bool, str, bool, str]:
        """
        返回 (material_still_insufficient, insufficiency_signal, knowledge_adequate, kb_tier)。

        失败边界：
        - 期望拉 kb / 用户开了 use_knowledge，但 kb + web 都空 → material_insufficient
        - kb 弱 + 无 web → weak_kb_only
        - kb 弱 + 有 web → weak_kb_web_used
        """
        msg_kb_nonempty = bool((knowledge_block or "").strip())
        msg_wb_nonempty = bool((web_block or "").strip())
        if kb_sufficiency is not None:
            knowledge_adequate = kb_sufficiency.adequate
            kb_tier = kb_sufficiency.evidence_tier or "none"
            msg_kb_nonempty = bool(msg_kb_nonempty or kb_sufficiency.hits > 0)
        else:
            if not msg_kb_nonempty:
                kb_tier = _agno_kb_evidence_tier("", knowledge_block)
            else:
                ov = cailiao_pan.kb_qiangdu
                kb_tier = "weak" if ov < 0.08 else "strong"
            knowledge_adequate = msg_kb_nonempty

        material_insufficient = False
        if try_rag and not msg_kb_nonempty and not msg_wb_nonempty:
            material_insufficient = True
        if http_use_knowledge and not msg_kb_nonempty and not msg_wb_nonempty:
            material_insufficient = True

        if material_insufficient:
            signal = "still_empty_after_gather"
        elif kb_sufficiency is not None and not kb_sufficiency.adequate and not msg_wb_nonempty:
            signal = "weak_kb_only" if kb_tier == "weak" else "kb_insufficient"
        elif kb_sufficiency is not None and not kb_sufficiency.adequate and msg_wb_nonempty:
            signal = "weak_kb_web_used" if kb_tier == "weak" else "kb_insufficient"
        elif kb_tier == "weak" and not msg_wb_nonempty:
            signal = "weak_kb_only"
        elif kb_tier == "weak" and msg_wb_nonempty:
            signal = "weak_kb_web_used"
        else:
            signal = "ok"
        return material_insufficient, signal, knowledge_adequate, kb_tier

    # ---------- V8 第 1 轮：承接前文 → 决定是否沿用上一轮锚点 ----------
    def pan_history_followup(
        self,
        *,
        message: str,
        history: SessionHistorySnapshot | None,
        own_mp4_in_message: bool,
    ) -> tuple[PrevVideoRef | None, str]:
        """
        判断本轮 middle 是否要"沿用上一轮视频对象继续补材"。

        承接条件（同时满足才算真承接，避免做成关键词碰撞）：
        1) `history` 非空且 `prev_video` 非空（结构化锚点真存在）；
        2) 本轮 message 看起来在指代前文（"刚才那个视频/上一个/继续说" 等）；
        3) 本轮 message 自己 **没有自带新的 .mp4 路径**（避免覆盖用户新意图）。

        返回 `(anchor, followup_query)`：
        - anchor 为 None 表示不承接前文；
        - 否则 anchor 是上一轮入库锚点，followup_query 是用 anchor.source_id +
          原 message 拼出的检索 query，由调用方传给 RAG 服务真正去命中入库内容。
        """
        if history is None or not history.has_prev_video:
            return None, ""
        if own_mp4_in_message:
            return None, ""
        anchor = history.followup_video_anchor(message)
        if anchor is None:
            return None, ""
        # 用结构化锚点 + 原 message 一起拼检索 query：source_id 是 V7 入库时注入的
        # `video:<basename>` 命名空间，FTS5 会把它当成强权重 token 命中，从而
        # 把"刚才那个视频"这种指代真转成"在 video: 命名空间里检索"的实体行为。
        msg = (message or "").strip()
        followup_query = f"{anchor.source_id} {msg}".strip()
        return anchor, followup_query

    # ---------- V7 第 1 轮：视频意图识别 ----------
    def shibie_video_yitu(self, *, message: str) -> dict[str, Any]:
        """视频 .mp4 显式信号；实现见 `video_flow.shibie_video_yitu`。"""
        return video_flow.shibie_video_yitu(message=message)

    # ---------- V7 第 1 轮：业务型 MCP 调用决策（主链上的真实决策点）----------
    def pan_jubu_celue_video(self, *, video_yitu: dict[str, Any]) -> str:
        """MCP video_to_text 决策；实现见 `video_flow.pan_jubu_celue_video`。"""
        return video_flow.pan_jubu_celue_video(video_yitu=video_yitu)

    # ---------- V11 R1：视频 URL 链（yt-dlp 下字幕 / 云 ASR 兜底 → 入 KB）----------
    def shibie_video_url_yitu(self, *, message: str) -> dict[str, Any]:
        """网页视频 URL 显式信号；实现见 `video_flow.shibie_video_url_yitu`。"""
        return video_flow.shibie_video_url_yitu(message=message)

    def video_url_yitu_from_plan_or_message(
        self,
        *,
        plan: AgnoCollaborationPlan,
        message: str,
    ) -> tuple[dict[str, Any], str]:
        """V11 R7：优先 `plan.video_url`；实现见 `video_flow.video_url_yitu_from_plan_or_message`。"""
        return video_flow.video_url_yitu_from_plan_or_message(plan=plan, message=message)

    def pan_jubu_celue_video_url(self, *, video_url_yitu: dict[str, Any]) -> str:
        """网页视频 fetch 决策；实现见 `video_flow.pan_jubu_celue_video_url`。"""
        return video_flow.pan_jubu_celue_video_url(video_url_yitu=video_url_yitu)

    # V11 R6 保存到知识库的关键词
    _SAVE_TO_KB_KEYWORDS: frozenset[str] = frozenset({
        "保存", "入库", "存到知识库", "保存到知识库", "收藏",
        "存入知识库", "加入知识库", "存入", "入知识库",
        # 禁止使用裸 "save"/"ingest" 子串——易与路径 e2e/not_auto_ingest、英文临时目录名误触发
    })

    def shibie_save_to_kb_yitu(self, *, message: str) -> bool:
        """V11 R6：识别用户是否要把上一轮视频内容保存到知识库。

        关键词匹配，不需要 LLM —— 用户说"保存到知识库"/"入库"就行。
        """
        msg = (message or "").strip().lower()
        if not msg:
            return False
        return any(kw in msg for kw in self._SAVE_TO_KB_KEYWORDS)

    # ---------- 5) 清洗 / 约束 / 兜底 ----------
    def qingxi_yueshu_doudi(
        self,
        *,
        cailiao_pan: CailiaoPan,
        plan: AgnoCollaborationPlan,
        http_use_knowledge: bool,
    ) -> CailiaoPan:
        """规则层兜底：xia_yi_bu 与 main 权限协调（不重判 gou/bukong/laiyuan 这类核心字段）。"""
        xp = plan.xiezuo_pan
        allow_kb_now = bool(xp.allow_kb) if xp else http_use_knowledge
        allow_web_now = bool(xp.allow_web) if xp else True

        new_xia = cailiao_pan.xia_yi_bu
        if cailiao_pan.bukong_xinhao == "que":
            if allow_web_now and cailiao_pan.laiyuan_zhu in ("wu", "kb"):
                new_xia = "bu_wang"
            elif allow_kb_now:
                new_xia = "wen_yonghu"
            else:
                new_xia = "shou_kou"
        elif cailiao_pan.que_shenme == "web_yinzheng" and not allow_web_now:
            new_xia = "shou_kou"

        if new_xia != cailiao_pan.xia_yi_bu:
            return replace(cailiao_pan, xia_yi_bu=new_xia)
        return cailiao_pan
