"""台账治理第2b轮 — Answer 判断阶段 mixin（五段 + feedback_request，不含 huida 主链）。"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from agents.main_agent import AgnoCollaborationPlan, MainXiezuoPan
from agents.middle_agent import AgnoMaterialBundle
from application.chat.path_labels import resolve_complex_primary_path

from .schema import HuidaPan

_LANE_AGNO_BASIC = "agno_basic"


class AnswerJudgmentPhaseMixin:
    """Answer 五段判断；与 ``AgnoAgentRuntime`` 组合使用。"""

    def shibie_yitu(
        self,
        *,
        plan: AgnoCollaborationPlan,
        bundle: AgnoMaterialBundle,
    ) -> str:
        cp = bundle.cailiao_pan
        if plan.force_skip_evidence:
            return "zhi_da_yitu"
        if cp.bukong_xinhao == "que":
            return "fenkai_yitu"
        if cp.bukong_xinhao == "ruo":
            return "baoshou_yitu"
        return "zhi_da_yitu"

    def pan_jubu_celue(self, *, intent: str) -> tuple[str, str]:
        if intent == "fenkai_yitu":
            return "fenkai", "qa"
        if intent == "baoshou_yitu":
            return "baoshou", "sections"
        return "zhijie", "short"

    def pan_zhuyao_panjue(
        self,
        *,
        intent: str,
        plan: AgnoCollaborationPlan,
        bundle: AgnoMaterialBundle,
    ) -> HuidaPan:
        xp: MainXiezuoPan = plan.xiezuo_pan
        da_fengshi, jiegou_mode = self.pan_jubu_celue(intent=intent)

        bs = float(xp.fengxian_yinzi)
        if da_fengshi == "baoshou":
            bs = max(bs, 0.78)
        elif da_fengshi == "fenkai":
            bs = max(bs, 0.7)

        lane, primary_path = self._sign_lane(plan, bundle)

        return HuidaPan(
            da_fengshi=da_fengshi,
            jiegou_mode=jiegou_mode,
            baoshou_level=round(min(1.0, max(0.0, bs)), 3),
            lane=lane,
            primary_path=primary_path,
        )

    def _sign_lane(
        self,
        plan: AgnoCollaborationPlan,
        bundle: AgnoMaterialBundle,
    ) -> tuple[str, str]:
        lane = resolve_complex_primary_path(bundle)
        return lane, lane

    def pan_shibai_bianjie(
        self,
        *,
        hp: HuidaPan,
        plan: AgnoCollaborationPlan,
        bundle: AgnoMaterialBundle,
    ) -> HuidaPan:
        bs = float(hp.baoshou_level)
        da_fengshi = hp.da_fengshi
        if bundle.material_still_insufficient and hp.da_fengshi == "zhijie":
            bs = max(bs, 0.65)
        if bundle.kb_evidence_tier == "weak":
            bs = max(bs, 0.6)
        if bundle.v8_history_used and bundle.v8_history_anchor_stale:
            bs = max(bs, 0.85)
            da_fengshi = "baoshou"
        elif bundle.v8_history_used and bundle.material_still_insufficient:
            bs = max(bs, 0.7)
        _trace_text = "\n".join(getattr(bundle, "trace", []) or [])
        if "v14:middle:" in _trace_text and "no_match=True" in _trace_text:
            bs = max(bs, 0.85)
            da_fengshi = "baoshou"
        elif "v14:middle:" in _trace_text and "low_confidence=True" in _trace_text:
            bs = max(bs, 0.7)
        if (
            abs(bs - hp.baoshou_level) > 1e-9
            or da_fengshi != hp.da_fengshi
        ):
            new_jiegou = "sections" if da_fengshi == "baoshou" else hp.jiegou_mode
            return replace(
                hp,
                baoshou_level=round(min(1.0, max(0.0, bs)), 3),
                da_fengshi=da_fengshi,
                jiegou_mode=new_jiegou,
            )
        return hp

    def qingxi_yueshu_doudi(self, hp: HuidaPan) -> HuidaPan:
        bs = round(min(1.0, max(0.0, float(hp.baoshou_level))), 3)
        lane = hp.lane or _LANE_AGNO_BASIC
        primary = hp.primary_path or lane
        if bs != hp.baoshou_level or lane != hp.lane or primary != hp.primary_path:
            return replace(hp, baoshou_level=bs, lane=lane, primary_path=primary)
        return hp

    def build_feedback_request(
        self,
        *,
        plan: AgnoCollaborationPlan,
        bundle: AgnoMaterialBundle,
        current_round: int,
    ) -> dict[str, Any] | None:
        job_type = getattr(plan, "job_type", "") or "normal_chat"
        if current_round >= max(int(getattr(plan, "max_rounds", 0) or 0), 1):
            return None
        critic = dict(getattr(bundle, "critic_check", {}) or {})
        source_tasks = list(getattr(bundle, "source_tasks", []) or [])
        insufficient = getattr(bundle, "material_sufficiency", "insufficient") != "sufficient"
        if not insufficient and not critic.get("revision_required", False):
            return None

        if job_type != "multi_source_compare":
            if not getattr(plan.xiezuo_pan, "allow_web", False):
                return None
            if getattr(bundle, "web_block", None):
                return None
            return {
                "feedback_request_id": f"fbreq_{getattr(bundle, 'bundle_id', 'default')}",
                "job_id": str(getattr(plan.decision, "task_id", "") or ""),
                "round_index": current_round,
                "reason": "需要补抓网页证据后再回答",
                "evidence_gap": "当前知识证据不足，需补抓网页证据。",
                "query_hint": getattr(plan, "original_user_intent", "") or "",
                "requested_source_task_ids": [],
                "requested_fallback_step_ids": ["default_web_round1"],
                "requested_fallback_steps": [
                    {
                        "step_id": "default_web_round1",
                        "tool_name": "fetch_web",
                        "source_type": "web",
                    }
                ],
                "material_sufficiency_before": getattr(bundle, "material_sufficiency", "insufficient"),
                "original_user_intent": getattr(plan, "original_user_intent", "") or "",
                "status": "requested",
            }

        failed_tasks = [task for task in source_tasks if task.get("status") == "failed"]
        weak_claims = list(critic.get("weak_evidence_claims") or [])
        evidence_gap_bits: list[str] = []
        requested_source_task_ids = [
            task.get("source_task_id", "")
            for task in failed_tasks
            if task.get("source_task_id")
        ]
        if failed_tasks:
            evidence_gap_bits.append("存在来源抓取失败")
        if weak_claims:
            evidence_gap_bits.append("存在弱证据结论")
        requested_fallback_step_ids = []
        for step in list(getattr(plan, "fallback_steps", []) or []):
            if failed_tasks and step.get("source_task_id") in requested_source_task_ids:
                requested_fallback_step_ids.append(step.get("step_id", ""))
        if not requested_fallback_step_ids:
            fb_steps = list(getattr(plan, "fallback_steps", []) or [])[:1]
            requested_fallback_step_ids = [
                step.get("step_id", "") for step in fb_steps if step.get("step_id")
            ]
        if not requested_fallback_step_ids:
            return None
        return {
            "feedback_request_id": f"fbreq_{getattr(bundle, 'bundle_id', 'v17')}",
            "job_id": ((getattr(bundle, "analysis_job", None) or {}) or {}).get("job_id", ""),
            "round_index": current_round,
            "reason": "需要补抓更多对比证据" if insufficient else "需要补强证据后再回答",
            "evidence_gap": "；".join(evidence_gap_bits) or "现有材料不足以形成稳健比较",
            "query_hint": getattr(plan, "original_user_intent", "") or "",
            "requested_source_task_ids": requested_source_task_ids,
            "requested_fallback_step_ids": requested_fallback_step_ids,
            "material_sufficiency_before": getattr(bundle, "material_sufficiency", "insufficient"),
            "original_user_intent": getattr(plan, "original_user_intent", "") or "",
            "status": "requested",
        }


__all__ = ["AnswerJudgmentPhaseMixin", "_LANE_AGNO_BASIC"]
