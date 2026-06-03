"""Document OCR orchestration — sync OCR + async document_ocr task enqueue."""

from __future__ import annotations

import uuid
from typing import Any

from config.feature_flags import async_control_plane_active
from services.execution.async_runtime import ensure_async_workers_started
from storage import task_job_store
from tasks.queue.async_task_queue import AsyncTaskMessage, enqueue_async_task
from tools.document.tool_result import DocumentToolResult


def _ensure_ocr_tools_registered() -> None:
    import tools.ocr.ocr_document  # noqa: F401


def run_ocr_sync(
    file_path: str,
    *,
    estimated_cost: float = 0.0,
    session_id: str = "",
) -> DocumentToolResult:
    _ensure_ocr_tools_registered()
    from tools.ocr import registry

    return registry.call_tool(
        "ocr_document",
        file_path=file_path,
        estimated_cost=estimated_cost,
        session_id=session_id,
    )


def enqueue_document_ocr_task(
    *,
    file_path: str,
    session_id: str = "",
    request_id: str = "",
    estimated_cost: float = 0.0,
    prefilled_fact: Any | None = None,
) -> tuple[str, str]:
    if not async_control_plane_active():
        raise RuntimeError("ENABLE_ASYNC_CONTROL_PLANE_V2 is disabled")
    task_id = str(uuid.uuid4())
    fact_metadata: dict[str, object] = {}
    if prefilled_fact is not None:
        fact_metadata = {
            "capability_probe_elapsed_ms": getattr(prefilled_fact, "probe_elapsed_ms", 0),
            "capability_page_count": getattr(prefilled_fact, "page_count", None),
            "capability_ocr_required": getattr(prefilled_fact, "ocr_required", None),
            "capability_quality_level": getattr(prefilled_fact, "quality_level", ""),
        }
    task_job_store.create_task(
        task_id,
        task_type="document_ocr",
        source_type="document",
        session_id=session_id or None,
        request_id=request_id or None,
        user_query=file_path,
        metadata={
            "payload_version": 1,
            "lane": "document",
            "estimated_cost": estimated_cost,
            **fact_metadata,
        },
    )
    backend = enqueue_async_task(
        AsyncTaskMessage(
            task_id=task_id,
            task_type="document_ocr",
            lane="document",
            source_type="document",
            source_ref=file_path,
            request_id=request_id,
            session_id=session_id,
            metadata={"estimated_cost": estimated_cost},
        )
    )
    task_job_store.update_task_async_metadata(
        task_id,
        metadata={
            "queue_backend": backend,
            "payload_version": 1,
            "lane": "document",
            "task_type": "document_ocr",
            "enqueued_at_ms": int(__import__("time").time() * 1000),
            "retry_count": 0,
        },
    )
    ensure_async_workers_started()
    return task_id, backend
