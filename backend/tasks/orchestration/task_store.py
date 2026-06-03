from __future__ import annotations

import uuid
from typing import Any

from storage import task_job_store


def create_task_record(
    *,
    task_type: str,
    source_type: str,
    session_id: str = "",
    request_id: str = "",
    user_query: str = "",
) -> str:
    task_id = str(uuid.uuid4())
    task_job_store.create_task(
        task_id,
        task_type=task_type,
        source_type=source_type,
        session_id=session_id or None,
        request_id=request_id or None,
        user_query=user_query,
    )
    return task_id


def get_task_record(task_id: str) -> dict[str, Any] | None:
    return task_job_store.get_job(task_id)


def set_task_cancelled(task_id: str, *, reason: str = "task cancelled") -> None:
    task_job_store.mark_task_cancelled(task_id, failure_reason=reason)
