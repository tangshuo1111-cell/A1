"""Async document OCR pipeline — P9 第二领域接入 async control plane。"""

from __future__ import annotations

from storage import task_job_store


def run_document_ocr_task(
    task_id: str,
    file_path: str,
    session_id: str,
    *,
    estimated_cost: float = 0.0,
) -> None:
    from services.capabilities.knowledge.pending_ingestion_service import prepare_ocr_source

    task_job_store.mark_task_running(task_id, stage="document_ocr")
    item = prepare_ocr_source(
        file_path,
        session_id=session_id,
        estimated_cost=estimated_cost,
    )
    if item.extract_status == "ok":
        text = (item.text or "").strip()
        from services.capabilities.answer_draft import final_answer_fields_for_task

        draft_fields = final_answer_fields_for_task(
            lane="document",
            user_query=file_path,
            material=text,
            title=(item.title or file_path),
        )
        task_job_store.mark_task_succeeded(
            task_id,
            result_summary={
                "status": "success",
                "source_type": "ocr_document",
                "title": item.title,
                "text_length": len(item.text or ""),
                "parser_name": item.parser_name,
                **draft_fields,
            },
            result_pending_id=item.pending_id,
        )
        return
    task_job_store.mark_task_failed(
        task_id,
        error_code=item.error_code or item.extract_status or "document_ocr_failed",
        failure_reason=f"文档 OCR 失败: {item.error_code or item.extract_status or 'unknown'}",
        next_action_hint="检查 OCR provider 配置、文件格式或页数上限后重试。",
    )
