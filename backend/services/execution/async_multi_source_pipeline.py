from __future__ import annotations

from storage import conversation_store, task_job_store


def run_multi_source_research_task(task_id: str, user_query: str, session_id: str) -> None:
    from services.capabilities.web import web_orchestration_service

    task_job_store.mark_task_running(task_id, stage="multi_source_research")
    material = web_orchestration_service.fetch_web_evidence_block(user_query, max_results=4)
    material = (material or "").strip()
    if not material:
        task_job_store.mark_task_failed(
            task_id,
            error_code="multi_source_research_empty",
            failure_reason="多来源研究未获得可用外部材料。",
            next_action_hint="请改写问题、提供更明确的链接，或稍后重试。",
        )
        return
    summary = material[:600]
    task_job_store.mark_task_succeeded(
        task_id,
        result_summary={
            "status": "success",
            "source_type": "research",
            "summary": summary,
            "text_length": len(material),
        },
    )
    conversation_store.append_turn(
        task_id=task_id,
        session_id=session_id or None,
        user_query=user_query,
        answer=f"后台多来源研究已完成。以下是提取到的摘要：\n\n{summary}",
        task_status="succeeded",
        answer_type="structured_sections",
        channels_used=["web"],
        router_source="async_control_plane",
        user_visible_status="后台完成",
    )
