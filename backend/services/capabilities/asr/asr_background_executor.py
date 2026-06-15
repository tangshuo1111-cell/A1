"""Mid-duration ASR background worker — parallel segment transcribe + draft + stitch."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

from config.settings import settings
from services.capabilities.answer_draft import final_answer_fields_for_task
from services.capabilities.video.parallel_asr_service import run_parallel_segment_asr
from services.capabilities.video.provider_chain import resolve_video_asr_provider_chain
from storage import task_job_store
from tasks.orchestration.turn_stitcher import maybe_attach_task_result


def run_asr_mid_background_task(task_id: str, file_path: str, session_id: str) -> None:
    path = Path(file_path)
    if not path.exists():
        task_job_store.mark_task_failed(
            task_id,
            error_code="file_not_found",
            failure_reason=f"ASR 后台任务文件不存在: {file_path}",
            next_action_hint="确认文件路径后重新提交。",
        )
        return

    task_job_store.mark_task_running(task_id, stage="asr_mid_background", progress=0.15)
    asr_started = time.perf_counter()
    asr_result = run_parallel_segment_asr(
        path,
        session_id=session_id,
        provider_chain=resolve_video_asr_provider_chain(source_type="local_video"),
        deadline_ms=int(getattr(settings, "v16_video_sync_deadline_ms", 20000) or 20000),
        max_workers=int(getattr(settings, "v16_video_parallel_asr_workers", 6) or 6),
    )
    asr_elapsed_ms = int((time.perf_counter() - asr_started) * 1000)

    if not asr_result.ok or not (asr_result.text or "").strip():
        task_job_store.mark_task_failed(
            task_id,
            error_code=(asr_result.error_code or "asr_mid_background_failed")[:200],
            failure_reason=(
                asr_result.failure_reason
                or asr_result.error_code
                or "中段长音频后台 ASR 失败"
            )[:500],
            next_action_hint=asr_result.next_action_hint or "检查 ASR provider、额度与音频质量后重试。",
        )
        return

    text = (asr_result.text or "").strip()
    task_job_store.mark_task_running(task_id, stage="answer_draft", progress=0.85)
    draft_started = time.perf_counter()
    draft_fields = final_answer_fields_for_task(
        lane="general",
        user_query=file_path,
        material=text,
        title=path.name,
    )
    draft_elapsed_ms = int((time.perf_counter() - draft_started) * 1000)
    result_summary = {
        "status": "success",
        "text_source": "asr",
        "title": path.name,
        "text_length": len(text),
        "transcript_text": text,
        "content_hash": hashlib.sha1(text.encode("utf-8")).hexdigest(),
        "asr_provider": asr_result.provider or "",
        "asr_model": asr_result.model or "",
        "asr_ms": asr_elapsed_ms,
        "draft_answer_ms": draft_elapsed_ms,
        "background_total_ms": asr_elapsed_ms + draft_elapsed_ms,
        **draft_fields,
    }
    task_job_store.mark_task_succeeded(
        task_id,
        result_summary=result_summary,
        result_source_id=str(path),
    )
    maybe_attach_task_result(
        session_id=session_id,
        task_id=task_id,
        result_summary=result_summary,
        lane="asr",
    )
