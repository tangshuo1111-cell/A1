"""台账 G-005「multisource_round」：多来源 tool_plan 轮次执行与 bundle 聚合。

历史文件名 `v17_tool_plan.py` 已废止；`_execute_v17_tool_plan` 等符号名保留以兼容调用与 trace。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from agents.main_agent import AgnoCollaborationPlan
from agents.multisource.schema import now_iso

from .comparison_builder import build_comparison_matrix
from .evidence_checker import build_critic_check
from .schema import AgnoMaterialBundle, CailiaoPan
from .tool_dispatch import _execute_v17_steps


def _execute_v17_tool_plan(
    message: str,
    plan: AgnoCollaborationPlan,
    *,
    prior_bundle: AgnoMaterialBundle | None = None,
    allowed_fallback_steps: list[dict[str, Any]] | None = None,
    current_round: int = 0,
    feedback_gate_result: dict[str, Any] | None = None,
) -> AgnoMaterialBundle:
    """Execute V17 multisource plan and optional fallback round through V16 tools."""
    _ = message
    job = dict(getattr(plan, "analysis_job", None) or {})
    tool_plan = dict(getattr(plan, "tool_plan", None) or job.get("tool_plan") or {})
    source_tasks = [dict(x) for x in job.get("source_tasks", [])]
    allowed = set(tool_plan.get("tools_allowed") or [])
    disabled = set(tool_plan.get("tools_disabled") or [])

    round0_tasks, round0_briefs, round0_steps, round0_failures, round0_calls, temp_materials = _execute_v17_steps(
        steps=list(tool_plan.get("steps") or []),
        source_tasks=source_tasks,
        allowed=allowed,
        disabled=disabled,
        round_label="round_0",
    )
    all_source_tasks = round0_tasks
    all_briefs = list(round0_briefs)
    all_steps = list(round0_steps)
    all_failures = list(round0_failures)
    all_calls = list(round0_calls)
    used_rounds = [0]
    executed_fallback_steps: list[dict[str, Any]] = []
    round_delta: dict[str, Any] | None = None

    if current_round == 1 and prior_bundle is not None:
        fallback_tasks: list[dict[str, Any]] = []
        for step in allowed_fallback_steps or []:
            source_index = int(step.get("source_index", 0) or 0)
            base_task = dict(all_source_tasks[source_index]) if source_index < len(all_source_tasks) else {}
            fallback_tasks.append(
                {
                    **base_task,
                    "source_task_id": f"{base_task.get('source_task_id', job.get('job_id', 'v17'))}_round1",
                    "tool_step_id": step.get("step_id", ""),
                    "tool_name": step.get("tool_name", ""),
                    "status": "queued",
                    "tool_result_status": "",
                    "error_code": "",
                    "failure_reason": "",
                }
            )
        round1_tasks, round1_briefs, round1_steps, round1_failures, round1_calls, round1_temps = _execute_v17_steps(
            steps=list(allowed_fallback_steps or []),
            source_tasks=fallback_tasks,
            allowed=allowed,
            disabled=disabled,
            round_label="round_1",
        )
        if round1_tasks:
            used_rounds = [0, 1]
            all_source_tasks.extend(round1_tasks)
            all_briefs.extend(round1_briefs)
            all_steps.extend(round1_steps)
            all_failures.extend(round1_failures)
            all_calls.extend(round1_calls)
            temp_materials.extend(round1_temps)
            executed_fallback_steps = list(allowed_fallback_steps or [])
            round_delta = {
                "job_id": job.get("job_id", ""),
                "round_0_bundle_id": getattr(prior_bundle, "bundle_id", ""),
                "round_1_bundle_id": "",
                "new_tool_calls": round1_calls,
                "new_source_tasks": round1_tasks,
                "new_source_briefs": round1_briefs,
                "new_chunks_added": [cid for task in round1_tasks for cid in task.get("retrieved_chunk_ids", [])],
                "new_failures_added": round1_failures,
                "material_sufficiency_before": getattr(prior_bundle, "material_sufficiency", "insufficient"),
                "material_sufficiency_after": "sufficient" if round1_briefs else getattr(prior_bundle, "material_sufficiency", "insufficient"),
                "feedback_result": feedback_gate_result or {},
                "final_answer_based_on_round": "round_1" if round1_briefs else "round_0",
            }

    failed = sum(1 for task in all_source_tasks if task.get("status") == "failed")
    succeeded = sum(1 for task in all_source_tasks if task.get("status") == "succeeded")
    status = "completed" if failed == 0 else "partial" if succeeded else "failed"
    comparison_matrix = build_comparison_matrix(job, all_briefs)
    critic_check = build_critic_check(job, comparison_matrix, all_briefs)
    material_sufficiency = "sufficient" if critic_check.get("safe_to_answer") and succeeded >= 2 else "insufficient"
    if failed and succeeded:
        material_sufficiency = "insufficient"
    job.update({"source_tasks": all_source_tasks, "status": status, "updated_at": now_iso()})
    negotiation_trace = {
        "v17_job_id": job.get("job_id", ""),
        "v17_job_type": job.get("job_type", ""),
        "v17_source_count": job.get("source_count", 0),
        "v17_tool_plan_steps_count": len(tool_plan.get("steps") or []),
        "v17_source_tasks_count": len(all_source_tasks),
        "v17_source_briefs_count": len(all_briefs),
        "v17_partial_status": status,
        "v17_failed_source_count": failed,
        "v17_used_source_brief_ids": [brief["source_brief_id"] for brief in all_briefs],
        "v17_tool_steps_summary": all_steps,
        "v17_comparison_status": comparison_matrix.get("status", ""),
        "v17_critic_safe_to_answer": critic_check.get("safe_to_answer", False),
        "v17_used_rounds": used_rounds,
        "v17_executed_fallback_steps": [step.get("step_id", "") for step in executed_fallback_steps],
    }
    job["trace"] = dict(job.get("trace") or {}, **negotiation_trace)
    limitations = list(critic_check.get("limitations") or [])
    if failed:
        limitations.append("存在来源抓取失败，最终回答需保守说明。")
    cailiao_pan = CailiaoPan(
        gou=bool(all_briefs),
        kb_qiangdu=1.0 if all_briefs else 0.0,
        bukong_xinhao="ok" if material_sufficiency == "sufficient" else "ruo" if all_briefs else "que",
        laiyuan_zhu="web",
        use_kb=False,
        use_web=bool(all_briefs),
        que_shenme="none" if material_sufficiency == "sufficient" else "web_yinzheng",
        xia_yi_bu="zhi_da" if material_sufficiency == "sufficient" else "bu_wang",
    )
    used_context = []
    for brief in all_briefs[:4]:
        span: dict[str, Any] = next(iter(brief.get("evidence_spans") or []), {})
        if span.get("text_excerpt"):
            used_context.append(str(span.get("text_excerpt"))[:200])
    bundle = AgnoMaterialBundle(
        knowledge_block=None,
        web_block=None,
        trace=[
            "v17:middle:tool_plan:start",
            *[f"v17:{step['round']}:{step['step_id']}:{step['status']}" for step in all_steps],
            "v17:comparison_matrix:done",
            "v17:critic_check:done",
        ],
        knowledge_adequate=bool(all_briefs),
        material_still_insufficient=material_sufficiency != "sufficient",
        web_judgment_reason="v17_tool_plan",
        kb_evidence_tier="none",
        insufficiency_signal="ok" if material_sufficiency == "sufficient" else "que",
        cailiao_pan=cailiao_pan,
        plan_id=str(getattr(plan.decision, "task_id", "")),
        execution_status="ok" if status == "completed" else status,
        tool_calls=all_calls,
        temporary_materials=temp_materials,
        failures=all_failures,
        material_sufficiency=material_sufficiency,
        analysis_job=job,
        source_tasks=all_source_tasks,
        source_briefs=all_briefs,
        negotiation_trace=negotiation_trace,
        comparison_matrix=comparison_matrix,
        critic_check=critic_check,
        feedback_gate_result=feedback_gate_result,
        round_delta=round_delta,
        used_rounds=used_rounds,
        final_answer_based_on_round="round_1" if used_rounds[-1] == 1 and round_delta and round_delta.get("new_source_briefs") else "round_0",
        used_context=used_context,
        answer_limitations=limitations,
    )
    if round_delta is not None:
        round_delta["round_1_bundle_id"] = bundle.bundle_id
        round_delta["material_sufficiency_after"] = bundle.material_sufficiency
        bundle = replace(bundle, round_delta=round_delta)
    return bundle


__all__ = ["_execute_v17_tool_plan"]
