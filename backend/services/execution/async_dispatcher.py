from __future__ import annotations

from config.feature_flags import async_control_plane_active
from storage import task_job_store
from tasks.queue.async_task_queue import AsyncTaskMessage


def process_async_task(message: AsyncTaskMessage) -> None:
    if message.task_type == "web_heavy_fetch" and not async_control_plane_active():
        task_job_store.mark_task_failed(
            message.task_id,
            error_code="async_control_plane_disabled",
            failure_reason="异步控制平面 v2 未启用，web_heavy_fetch 已拒绝。",
            next_action_hint="启用 ENABLE_ASYNC_CONTROL_PLANE_V2 后重试。",
        )
        return
    if message.task_type == "video_asr_background":
        from services.capabilities.video.background_executor import process_video_background_task
        from tasks.queue.video_task_queue import VideoTaskMessage

        process_video_background_task(
            VideoTaskMessage(
                task_id=message.task_id,
                source_type=message.source_type,
                source_ref=message.source_ref,
                session_id=message.session_id,
            )
        )
        return
    if message.task_type == "asr_mid_background":
        from services.capabilities.asr.asr_background_executor import run_asr_mid_background_task

        run_asr_mid_background_task(
            message.task_id,
            message.source_ref,
            message.session_id,
        )
        return
    if message.task_type == "web_heavy_fetch":
        from services.capabilities.web.async_web_pipeline import run_web_heavy_fetch_task

        run_web_heavy_fetch_task(message.task_id, message.source_ref, message.session_id)
        return
    if message.task_type == "document_ocr":
        if not async_control_plane_active():
            task_job_store.mark_task_failed(
                message.task_id,
                error_code="async_control_plane_disabled",
                failure_reason="异步控制平面 v2 未启用，document_ocr 已拒绝。",
                next_action_hint="启用 ENABLE_ASYNC_CONTROL_PLANE_V2 后重试。",
            )
            return
        from services.capabilities.document.async_document_pipeline import run_document_ocr_task

        estimated_cost = float((message.metadata or {}).get("estimated_cost") or 0.0)
        run_document_ocr_task(
            message.task_id,
            message.source_ref,
            message.session_id,
            estimated_cost=estimated_cost,
        )
        return
    if message.task_type == "multi_source_research":
        from services.execution.async_multi_source_pipeline import run_multi_source_research_task

        run_multi_source_research_task(message.task_id, message.source_ref, message.session_id)
        return
    task_job_store.mark_task_failed(
        message.task_id,
        error_code="unsupported_async_task",
        failure_reason=f"不支持的异步任务类型: {message.task_type}",
        next_action_hint="请检查异步任务编排来源。",
    )
