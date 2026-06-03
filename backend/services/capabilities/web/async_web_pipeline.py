from __future__ import annotations

from storage import task_job_store


def run_web_heavy_fetch_task(task_id: str, url: str, session_id: str) -> None:
    from services.capabilities.knowledge.pending_ingestion_service import prepare_web_url_source

    task_job_store.mark_task_running(task_id, stage="web_heavy_fetch")
    item = prepare_web_url_source(
        url,
        session_id=session_id,
        fetch_method="dynamic",
        task_id=task_id,
    )
    if item.extract_status == "ok":
        text = (item.text or "").strip()
        title = (item.title or url).strip()
        from services.capabilities.answer_draft import final_answer_fields_for_task

        draft_fields = final_answer_fields_for_task(
            lane="web",
            user_query=url,
            material=text,
            title=title,
        )
        result_summary = {
            "status": "success",
            "source_type": "web_url",
            "fetch_method": "dynamic",
            "title": item.title,
            "text_length": len(item.text or ""),
            **draft_fields,
        }
        task_job_store.mark_task_succeeded(
            task_id,
            result_summary=result_summary,
            result_pending_id=item.pending_id,
        )
        from tasks.orchestration.turn_stitcher import maybe_attach_task_result

        maybe_attach_task_result(
            session_id=session_id,
            task_id=task_id,
            result_summary=result_summary,
            lane="web",
        )
        return
    task_job_store.mark_task_failed(
        task_id,
        error_code=item.error_code or item.extract_status or "web_heavy_fetch_failed",
        failure_reason=f"网页重抓取失败: {item.error_code or item.extract_status or 'unknown'}",
        next_action_hint="检查网页可访问性、动态抓取依赖或 cookies 配置后重试。",
    )
