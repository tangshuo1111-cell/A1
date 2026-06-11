"""Synthesize feedback requests when AnswerAgent builder is absent (Round 2)."""

from __future__ import annotations

from typing import Any


def synthesize_web_feedback_request(*, plan: Any, bundle: Any, current_round: int) -> dict[str, Any] | None:
    if not getattr(plan.xiezuo_pan, "allow_web", False):
        return None
    if getattr(bundle, "web_block", None):
        return None
    return {
        "feedback_request_id": f"fbreq_{getattr(bundle, 'bundle_id', 'default')}",
        "job_id": str(getattr(plan.decision, "task_id", "") or ""),
        "round_index": current_round,
        "reason": "quality_gate 触发补抓网页证据",
        "evidence_gap": "质量门控判定材料不足，需补抓网页证据。",
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


def synthesize_multisource_feedback_request(*, plan: Any, bundle: Any, current_round: int) -> dict[str, Any]:
    fallback_steps = list(getattr(plan, "fallback_steps", ()) or ())
    requested = [
        {
            "step_id": str(step.get("step_id", f"ms_{idx}")),
            "tool_name": str(step.get("tool_name", "")),
            "source_type": str(step.get("source_type", "")),
        }
        for idx, step in enumerate(fallback_steps)
        if isinstance(step, dict) and step.get("tool_name")
    ]
    if not requested:
        requested = [
            {"step_id": "default_web_round1", "tool_name": "fetch_web", "source_type": "web"},
        ]
        if getattr(plan.xiezuo_pan, "allow_kb", False):
            requested.append({"step_id": "default_kb_round1", "tool_name": "retrieve_kb", "source_type": "kb"})
    return {
        "feedback_request_id": f"fbreq_{getattr(bundle, 'bundle_id', 'default')}",
        "job_id": str(getattr(plan.decision, "task_id", "") or ""),
        "round_index": current_round,
        "reason": "quality_gate 触发多来源补材",
        "evidence_gap": "质量门控判定多来源比较材料不足。",
        "query_hint": getattr(plan, "original_user_intent", "") or "",
        "requested_source_task_ids": [],
        "requested_fallback_step_ids": [step["step_id"] for step in requested],
        "requested_fallback_steps": requested,
        "material_sufficiency_before": getattr(bundle, "material_sufficiency", "insufficient"),
        "original_user_intent": getattr(plan, "original_user_intent", "") or "",
        "status": "requested",
    }
