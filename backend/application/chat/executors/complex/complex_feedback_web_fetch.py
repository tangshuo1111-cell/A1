"""Feedback fallback via web fetch."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable


def run_web_feedback_fetch(
    *,
    message: str,
    plan: Any,
    bundle: Any,
    feedback_gate_result: dict[str, Any],
    fetch_web_evidence_block: Callable[..., str],
) -> tuple[Any, bool]:
    new_web_block = fetch_web_evidence_block(message, max_results=3)
    if not (new_web_block or "").strip():
        failed = replace(
            bundle,
            used_rounds=[0, 1],
            final_answer_based_on_round="round_0",
            round_delta={
                "job_id": str(getattr(plan.decision, "task_id", "") or ""),
                "round_0_bundle_id": getattr(bundle, "bundle_id", ""),
                "round_1_bundle_id": "",
                "new_tool_calls": [{"tool": "fetch_web", "ok": False, "round": "round_1"}],
                "new_source_tasks": [],
                "new_source_briefs": [],
                "new_chunks_added": [],
                "new_failures_added": [{"tool": "fetch_web", "reason": "web_fetch_empty", "recoverable": True, "round": "round_1"}],
                "material_sufficiency_before": getattr(bundle, "material_sufficiency", "insufficient"),
                "material_sufficiency_after": getattr(bundle, "material_sufficiency", "insufficient"),
                "feedback_result": feedback_gate_result,
                "final_answer_based_on_round": "round_0",
            },
            answer_limitations=list(dict.fromkeys(list(getattr(bundle, "answer_limitations", []) or []) + ["补网后仍未获得可用网页证据。"])),
        )
        return failed, False

    updated_failures = list(getattr(bundle, "failures", []) or [])
    updated_tool_calls = list(getattr(bundle, "tool_calls", []) or [])
    updated_tool_calls.append({"tool": "fetch_web", "ok": True, "round": "round_1"})
    updated_critic = dict(getattr(bundle, "critic_check", {}) or {})
    updated_critic["revision_required"] = False
    updated_critic["safe_to_answer"] = True
    updated_limitations = list(dict.fromkeys(list(updated_critic.get("limitations") or []) + ["已通过 round_1 补充网页证据。"]))
    updated_critic["limitations"] = updated_limitations
    updated_envs = list(getattr(bundle, "evidence_envelopes", []) or [])
    if not any(getattr(env, "source_type", "") == "web" for env in updated_envs):
        from agents.middle_agent.schema import EvidenceEnvelope

        updated_envs.append(
            EvidenceEnvelope(
                source_type="web",
                status="success",
                text=new_web_block,
                summary=new_web_block[:200],
                confidence=0.72,
            )
        )
    success = replace(
        bundle,
        web_block=new_web_block,
        material_still_insufficient=False,
        web_judgment_reason="feedback_round_1_fetch_web",
        execution_status="ok",
        material_sufficiency="sufficient",
        critic_check=updated_critic,
        tool_calls=updated_tool_calls,
        failures=updated_failures,
        evidence_envelopes=updated_envs,
        feedback_request=getattr(bundle, "feedback_request", None),
        feedback_gate_result=feedback_gate_result,
        used_rounds=[0, 1],
        final_answer_based_on_round="round_1",
        round_delta={
            "job_id": str(getattr(plan.decision, "task_id", "") or ""),
            "round_0_bundle_id": getattr(bundle, "bundle_id", ""),
            "round_1_bundle_id": getattr(bundle, "bundle_id", ""),
            "new_tool_calls": [{"tool": "fetch_web", "ok": True, "round": "round_1"}],
            "new_source_tasks": [],
            "new_source_briefs": [],
            "new_chunks_added": [],
            "new_failures_added": [],
            "material_sufficiency_before": getattr(bundle, "material_sufficiency", "insufficient"),
            "material_sufficiency_after": "sufficient",
            "feedback_result": feedback_gate_result,
            "final_answer_based_on_round": "round_1",
        },
        answer_limitations=updated_limitations,
    )
    return success, True
