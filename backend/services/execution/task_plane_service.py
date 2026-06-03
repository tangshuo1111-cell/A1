from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from config.feature_flags import async_control_plane_active
from services.execution.async_runtime import ensure_async_workers_started
from storage import task_job_store
from tasks.queue.async_task_queue import AsyncTaskMessage, enqueue_async_task

if TYPE_CHECKING:
    from services.capabilities.contracts import CapabilityFact


class AsyncControlPlaneDisabledError(RuntimeError):
    """Raised when async control plane v2 is disabled."""


def enqueue_web_heavy_fetch_task(
    *,
    url: str,
    session_id: str = "",
    request_id: str = "",
    prefilled_fact: CapabilityFact | None = None,
) -> tuple[str, str]:
    if not async_control_plane_active():
        raise AsyncControlPlaneDisabledError("ENABLE_ASYNC_CONTROL_PLANE_V2 is disabled")
    task_id = str(uuid.uuid4())
    fact_metadata: dict[str, object] = {}
    if prefilled_fact is not None:
        fact_metadata = {
            "capability_probe_elapsed_ms": prefilled_fact.probe_elapsed_ms,
            "capability_dynamic_required": prefilled_fact.dynamic_required,
            "capability_cookie_required": prefilled_fact.cookie_required,
            "capability_quality_level": prefilled_fact.quality_level,
        }
    task_job_store.create_task(
        task_id,
        task_type="web_heavy_fetch",
        source_type="web_url",
        session_id=session_id or None,
        request_id=request_id or None,
        user_query=url,
        metadata={"payload_version": 1, "lane": "web", **fact_metadata},
    )
    backend = enqueue_async_task(
        AsyncTaskMessage(
            task_id=task_id,
            task_type="web_heavy_fetch",
            lane="web",
            source_type="web_url",
            source_ref=url,
            request_id=request_id,
            session_id=session_id,
        )
    )
    task_job_store.update_task_async_metadata(
        task_id,
        metadata={
            "queue_backend": backend,
            "payload_version": 1,
            "lane": "web",
            "task_type": "web_heavy_fetch",
            "enqueued_at_ms": int(__import__("time").time() * 1000),
            "retry_count": 0,
        },
    )
    ensure_async_workers_started()
    return task_id, backend


def enqueue_document_ocr_task(
    *,
    file_path: str,
    session_id: str = "",
    request_id: str = "",
    estimated_cost: float = 0.0,
    prefilled_fact: CapabilityFact | None = None,
) -> tuple[str, str]:
    from services.capabilities.document.ocr_service import enqueue_document_ocr_task as _enqueue

    return _enqueue(
        file_path=file_path,
        session_id=session_id,
        request_id=request_id,
        estimated_cost=estimated_cost,
        prefilled_fact=prefilled_fact,
    )


def enqueue_video_background_task(
    *,
    url: str,
    session_id: str = "",
    request_id: str = "",
    prefilled_fact: CapabilityFact | None = None,
) -> tuple[str, str]:
    task_id = str(uuid.uuid4())
    fact_metadata: dict[str, object] = {}
    if prefilled_fact is not None:
        fact_metadata = {
            "capability_probe_elapsed_ms": prefilled_fact.probe_elapsed_ms,
            "capability_duration_sec": prefilled_fact.duration_sec,
            "capability_quality_level": prefilled_fact.quality_level,
        }
        if prefilled_fact.artifact_ref:
            fact_metadata["artifact_ref"] = prefilled_fact.artifact_ref
    task_job_store.create_task(
        task_id,
        task_type="video_asr_background",
        source_type="web_video",
        session_id=session_id or None,
        request_id=request_id or None,
        user_query=url,
        metadata={"payload_version": 1, "lane": "video", **fact_metadata},
    )
    backend = enqueue_async_task(
        AsyncTaskMessage(
            task_id=task_id,
            task_type="video_asr_background",
            lane="video",
            source_type="web_video",
            source_ref=url,
            request_id=request_id,
            session_id=session_id,
        )
    )
    task_job_store.update_task_async_metadata(
        task_id,
        metadata={
            "queue_backend": backend,
            "payload_version": 1,
            "lane": "video",
            "task_type": "video_asr_background",
            "enqueued_at_ms": int(__import__("time").time() * 1000),
            "retry_count": 0,
        },
    )
    ensure_async_workers_started()
    return task_id, backend


def enqueue_multi_source_research_task(
    *,
    user_query: str,
    session_id: str = "",
    request_id: str = "",
) -> tuple[str, str]:
    task_id = str(uuid.uuid4())
    task_job_store.create_task(
        task_id,
        task_type="multi_source_research",
        source_type="research",
        session_id=session_id or None,
        request_id=request_id or None,
        user_query=user_query,
        metadata={"payload_version": 1, "lane": "general"},
    )
    backend = enqueue_async_task(
        AsyncTaskMessage(
            task_id=task_id,
            task_type="multi_source_research",
            lane="general",
            source_type="research",
            source_ref=user_query,
            request_id=request_id,
            session_id=session_id,
        )
    )
    task_job_store.update_task_async_metadata(
        task_id,
        metadata={
            "queue_backend": backend,
            "payload_version": 1,
            "lane": "general",
            "task_type": "multi_source_research",
            "enqueued_at_ms": int(__import__("time").time() * 1000),
            "retry_count": 0,
        },
    )
    ensure_async_workers_started()
    return task_id, backend
